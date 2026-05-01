import pytest

from llmgames import AssistedSeatController, GameConfig, GameSession, Player, approval_option
from llmgames.games import TicTacToeKernel
from llmgames.responders import FakeLLMProvider


def test_approval_option_marks_approval_primitive() -> None:
    option = approval_option("approve", label="Approve", suggestion_id="assist_1")

    assert option.value == "approve"
    assert option.metadata == {"primitive": "approval", "action": "approve", "suggestion_id": "assist_1"}


@pytest.mark.asyncio
async def test_assisted_suggestion_does_not_submit_until_approved() -> None:
    session = GameSession(TicTacToeKernel(), _config())
    await session.start()
    controller = AssistedSeatController(FakeLLMProvider({"place_mark:alice": {"row": 0, "col": 0}}))

    suggestion = await controller.suggest_for_request(session, session.requests[0])

    assert suggestion.payload == {"row": 0, "col": 0}
    assert session.submissions == []
    assert session.requests[0].status == "pending"
    assert [event.kind for event in session.events] == ["assist.requested", "assist.suggested"]


@pytest.mark.asyncio
async def test_human_can_approve_assisted_suggestion_through_normal_submission_path() -> None:
    session = GameSession(TicTacToeKernel(), _config())
    await session.start()
    controller = AssistedSeatController(FakeLLMProvider({"place_mark:alice": {"row": 0, "col": 0}}))
    suggestion = await controller.suggest_for_request(session, session.requests[0])

    result = await controller.approve_suggestion(session, suggestion, idempotency_key="approve-1")

    assert result.accepted is True
    assert result.submission.source == "human"
    assert result.submission.payload == suggestion.payload
    assert session.requests[0].status == "resolved"
    assert session.events[-1].kind == "assist.approved"


@pytest.mark.asyncio
async def test_human_can_edit_assisted_suggestion_before_submission() -> None:
    session = GameSession(TicTacToeKernel(), _config())
    await session.start()
    controller = AssistedSeatController(FakeLLMProvider({"place_mark:alice": {"row": 0, "col": 0}}))
    suggestion = await controller.suggest_for_request(session, session.requests[0])

    result = await controller.edit_suggestion(session, suggestion, {"row": 1, "col": 1}, idempotency_key="edit-1")

    assert result.accepted is True
    assert result.submission.source == "human"
    assert result.submission.payload == {"row": 1, "col": 1}
    assert session.events[-1].kind == "assist.edited"


@pytest.mark.asyncio
async def test_human_can_reject_assisted_suggestion_without_submission() -> None:
    session = GameSession(TicTacToeKernel(), _config())
    await session.start()
    controller = AssistedSeatController(FakeLLMProvider({"place_mark:alice": {"row": 0, "col": 0}}))
    suggestion = await controller.suggest_for_request(session, session.requests[0])

    controller.reject_suggestion(session, suggestion, reason="bad move")

    assert session.submissions == []
    assert session.requests[0].status == "pending"
    assert session.events[-1].kind == "assist.rejected"
    assert session.events[-1].payload == {"suggestion_id": suggestion.id, "reason": "bad move"}


def _config() -> GameConfig:
    return GameConfig(players=[Player(id="alice", name="Alice"), Player(id="bob", name="Bob")])