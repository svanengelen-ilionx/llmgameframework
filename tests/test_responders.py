import pytest

from llmgames import Audience, GameConfig, GameSession, Player
from llmgames.games import SplitOrStealKernel, TicTacToeKernel
from llmgames.llm import LLMSubmission, build_prompt_context
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


def _config() -> GameConfig:
    return GameConfig(players=[Player(id="alice", name="Alice"), Player(id="bob", name="Bob")])