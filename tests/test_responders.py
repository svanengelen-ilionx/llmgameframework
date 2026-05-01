import pytest
import httpx

from llmgames import Audience, GameConfig, GameSession, Player, ValidationIssue
from llmgames.games import SplitOrStealKernel, TicTacToeKernel
from llmgames.llm import HTTPJSONLLMProvider, LLMProviderError, LLMSubmission, build_prompt_context
from llmgames.responders import FakeLLMProvider, LLMResponder


@pytest.mark.asyncio
async def test_fake_llm_responder_submits_through_session_pipeline() -> None:
    session = GameSession(TicTacToeKernel(), _config())
    await session.start()
    provider = FakeLLMProvider({"place_mark:alice": {"row": 0, "col": 0}})
    responder = LLMResponder(provider)

    result = await responder.submit_for_request(session, session.requests[0])

    assert result.accepted is True
    assert result.submission.source == "llm"
    assert result.submission.actor_id == "alice"
    assert result.submission.payload == {"row": 0, "col": 0}
    assert session.requests[0].status == "resolved"
    assert [event.kind for event in session.events] == [
        "llm.requested",
        "llm.completed",
        "mark_placed",
        "llm.submitted",
    ]
    assert session.events[0].payload["correlation_id"] == "corr_1"


@pytest.mark.asyncio
async def test_fake_llm_provider_can_use_first_legal_example() -> None:
    session = GameSession(SplitOrStealKernel(), _config())
    await session.start()
    provider = FakeLLMProvider({})
    responder = LLMResponder(provider)

    result = await responder.submit_for_request(session, session.requests[0])

    assert result.accepted is True
    assert result.submission.source == "llm"
    assert result.submission.payload == {"choice": "split"}


@pytest.mark.asyncio
async def test_invalid_llm_payload_uses_normal_rejection_path() -> None:
    session = GameSession(TicTacToeKernel(), _config())
    await session.start()
    provider = FakeLLMProvider({"place_mark:alice": LLMSubmission(payload={"row": 0})})
    responder = LLMResponder(provider)

    result = await responder.submit_for_request(session, session.requests[0])

    assert result.accepted is False
    assert result.submission.source == "llm"
    assert result.submission.status == "rejected"
    assert result.issues[0].code == "schema_invalid"
    assert session.requests[0].status == "pending"


@pytest.mark.asyncio
async def test_prompt_context_uses_projection_not_truth_state() -> None:
    session = GameSession(SplitOrStealKernel(), _config())
    await session.start()
    await session.submit(
        "req_1",
        {"choice": "steal"},
        actor_id="alice",
        idempotency_key="alice-choice",
    )
    bob_request = [request for request in session.requests if request.actor_id == "bob"][0]
    projection = await session.projection(Audience.llm("bob"))

    context = build_prompt_context(projection, projection.visible_requests[0])

    assert projection.visible_requests[0].id == bob_request.id
    assert context.visible_state == {
        "round_number": 1,
        "submitted_player_ids": ["alice"],
        "revealed": False,
    }
    assert "choices" not in context.visible_state
    assert "steal" not in str(context.visible_state)


@pytest.mark.asyncio
async def test_prompt_context_requires_visible_request() -> None:
    session = GameSession(SplitOrStealKernel(), _config())
    await session.start()
    alice_request = [request for request in session.requests if request.actor_id == "alice"][0]
    bob_projection = await session.projection(Audience.llm("bob"))

    with pytest.raises(ValueError, match="Request must be visible"):
        build_prompt_context(bob_projection, alice_request)


@pytest.mark.asyncio
async def test_http_json_provider_retries_and_returns_structured_submission() -> None:
    attempts = 0
    seen_contexts = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        body = request.read()
        if attempts == 1:
            return httpx.Response(503, json={"error": "busy"})
        seen_contexts.append(body)
        return httpx.Response(200, json={"payload": {"row": 0, "col": 0}, "metadata": {"model": "fake"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = HTTPJSONLLMProvider(
        "https://provider.example/complete",
        client=client,
        retry_attempts=2,
        retry_wait_seconds=0,
    )
    session = GameSession(TicTacToeKernel(), _config())
    await session.start()
    projection = await session.projection(Audience.llm("alice"))
    context = build_prompt_context(projection, projection.visible_requests[0])

    submission = await provider.complete(context)

    assert attempts == 2
    assert submission == LLMSubmission(payload={"row": 0, "col": 0}, metadata={"model": "fake"})
    assert b'"visible_state"' in seen_contexts[0]
    await client.aclose()


@pytest.mark.asyncio
async def test_http_json_provider_reports_invalid_response_diagnostics() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"message": "missing payload"}))
    )
    provider = HTTPJSONLLMProvider("https://provider.example/complete", client=client, retry_wait_seconds=0)
    session = GameSession(TicTacToeKernel(), _config())
    await session.start()
    projection = await session.projection(Audience.llm("alice"))
    context = build_prompt_context(projection, projection.visible_requests[0])

    with pytest.raises(LLMProviderError) as exc_info:
        await provider.complete(context)

    assert exc_info.value.issue.code == "llm_response_invalid"
    assert exc_info.value.issue.path == ["payload"]
    await client.aclose()


@pytest.mark.asyncio
async def test_responder_records_failed_provider_event() -> None:
    class BrokenProvider:
        async def complete(self, context):
            raise LLMProviderError(ValidationIssue(code="llm_provider_error", message="Nope."))

    session = GameSession(TicTacToeKernel(), _config())
    await session.start()
    responder = LLMResponder(BrokenProvider())

    with pytest.raises(LLMProviderError):
        await responder.submit_for_request(session, session.requests[0])

    assert [event.kind for event in session.events] == ["llm.requested", "llm.failed"]
    assert session.events[1].payload["issue"]["code"] == "llm_provider_error"


def _config() -> GameConfig:
    return GameConfig(players=[Player(id="alice", name="Alice"), Player(id="bob", name="Bob")])
