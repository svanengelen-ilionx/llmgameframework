import pytest

from llmgames import Audience, GameConfig, GameSession, Player
from llmgames.games import TicTacToeKernel


@pytest.mark.asyncio
async def test_tic_tac_toe_session_advances_requests() -> None:
    session = GameSession(TicTacToeKernel(), _config())

    await session.start()
    projection = await session.projection(Audience.public())

    assert projection.status == "running"
    assert projection.visible_requests[0].id == "req_1"
    assert projection.visible_requests[0].spec_key == "place_mark:alice"

    first = await session.submit(
        "req_1",
        {"row": 0, "col": 0},
        actor_id="alice",
        idempotency_key="alice-1",
    )

    assert first.accepted is True
    assert first.submission.id == "sub_1"
    assert first.submission.status == "accepted"

    next_projection = await session.projection(Audience.public())
    assert next_projection.visible_state["board"][0][0] == "X"
    assert next_projection.visible_requests[0].id == "req_2"
    assert next_projection.visible_requests[0].spec_key == "place_mark:bob"
    assert [request.status for request in session.requests] == ["resolved", "pending"]


@pytest.mark.asyncio
async def test_tic_tac_toe_rejects_resolved_request_submission() -> None:
    session = GameSession(TicTacToeKernel(), _config())
    await session.start()
    await session.submit(
        "req_1",
        {"row": 0, "col": 0},
        actor_id="alice",
        idempotency_key="alice-1",
    )

    result = await session.submit(
        "req_1",
        {"row": 1, "col": 1},
        actor_id="alice",
        idempotency_key="alice-2",
    )

    assert result.accepted is False
    assert result.submission.status == "rejected"
    assert result.issues[0].code == "request_not_pending"


@pytest.mark.asyncio
async def test_tic_tac_toe_idempotency_reuses_accepted_submission() -> None:
    session = GameSession(TicTacToeKernel(), _config())
    await session.start()

    first = await session.submit(
        "req_1",
        {"row": 0, "col": 0},
        actor_id="alice",
        idempotency_key="alice-1",
    )
    second = await session.submit(
        "req_1",
        {"row": 0, "col": 0},
        actor_id="alice",
        idempotency_key="alice-1",
    )

    assert second.accepted is True
    assert second.submission == first.submission
    assert [submission.id for submission in session.submissions] == ["sub_1"]


@pytest.mark.asyncio
async def test_tic_tac_toe_idempotency_rejects_changed_payload() -> None:
    session = GameSession(TicTacToeKernel(), _config())
    await session.start()

    await session.submit(
        "req_1",
        {"row": 0, "col": 0},
        actor_id="alice",
        idempotency_key="alice-1",
    )
    result = await session.submit(
        "req_1",
        {"row": 0, "col": 1},
        actor_id="alice",
        idempotency_key="alice-1",
    )

    assert result.accepted is False
    assert result.issues[0].code == "idempotency_conflict"


@pytest.mark.asyncio
async def test_tic_tac_toe_rejects_invalid_payload_shape() -> None:
    session = GameSession(TicTacToeKernel(), _config())
    await session.start()

    result = await session.submit(
        "req_1",
        {"row": 0},
        actor_id="alice",
        idempotency_key="alice-1",
    )

    assert result.accepted is False
    assert result.submission.status == "rejected"
    assert result.issues[0].code == "schema_invalid"
    assert session.requests[0].status == "pending"


@pytest.mark.asyncio
async def test_player_projection_shows_only_players_pending_request() -> None:
    session = GameSession(TicTacToeKernel(), _config())
    await session.start()

    alice_projection = await session.projection(Audience.player("alice"))
    bob_projection = await session.projection(Audience.player("bob"))

    assert len(alice_projection.visible_requests) == 1
    assert bob_projection.visible_requests == []


@pytest.mark.asyncio
async def test_tic_tac_toe_session_plays_to_terminal_win() -> None:
    session = GameSession(TicTacToeKernel(), _config())
    await session.start()

    moves = [
        ("alice", {"row": 0, "col": 0}),
        ("bob", {"row": 1, "col": 0}),
        ("alice", {"row": 0, "col": 1}),
        ("bob", {"row": 1, "col": 1}),
        ("alice", {"row": 0, "col": 2}),
    ]
    for index, (actor_id, payload) in enumerate(moves, start=1):
        pending_request = [request for request in session.requests if request.status == "pending"][0]
        result = await session.submit(
            pending_request.id,
            payload,
            actor_id=actor_id,
            idempotency_key=f"move-{index}",
        )
        assert result.accepted is True

    projection = await session.projection(Audience.public())

    assert projection.status == "complete"
    assert projection.phase == "complete"
    assert projection.result is not None
    assert projection.result.status == "win"
    assert projection.result.winner_ids == ["alice"]
    assert projection.visible_requests == []
    assert projection.event_cursor == 5


def _config() -> GameConfig:
    return GameConfig(players=[Player(id="alice", name="Alice"), Player(id="bob", name="Bob")])
