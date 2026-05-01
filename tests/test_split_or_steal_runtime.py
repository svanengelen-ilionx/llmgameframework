import pytest

from llmgames import Audience, GameConfig, GameSession, Player
from llmgames.games import SplitOrStealKernel
from llmgames.testing import assert_projection_private, replay_session, run_scripted_session


@pytest.mark.asyncio
async def test_split_or_steal_starts_with_simultaneous_player_requests() -> None:
    session = GameSession(SplitOrStealKernel(), _config())

    await session.start()

    assert [(request.spec_key, request.mode, request.status) for request in session.requests] == [
        ("split_choice:alice:round_1", "barrier", "pending"),
        ("split_choice:bob:round_1", "barrier", "pending"),
    ]
    assert [request.spec_key for request in (await session.projection(Audience.player("alice"))).visible_requests] == [
        "split_choice:alice:round_1"
    ]
    assert [request.spec_key for request in (await session.projection(Audience.player("bob"))).visible_requests] == [
        "split_choice:bob:round_1"
    ]
    assert (await session.projection(Audience.public())).visible_requests == []


@pytest.mark.asyncio
async def test_split_or_steal_partial_barrier_submission_stays_private() -> None:
    session = GameSession(SplitOrStealKernel(), _config())
    await session.start()

    result = await session.submit(
        "req_1",
        {"choice": "steal"},
        actor_id="alice",
        idempotency_key="alice-choice",
    )
    public_projection = await session.projection(Audience.public())

    assert result.accepted is True
    assert [(request.spec_key, request.status) for request in session.requests] == [
        ("split_choice:alice:round_1", "pending"),
        ("split_choice:bob:round_1", "pending"),
    ]
    assert public_projection.phase == "choosing"
    assert public_projection.visible_state["submitted_player_ids"] == ["alice"]
    assert "choices" not in public_projection.visible_state
    assert_projection_private(
        public_projection,
        forbidden_values=["steal", "split"],
        context="unrevealed Split or Steal choices",
    )


@pytest.mark.asyncio
async def test_split_or_steal_resolves_after_both_submissions() -> None:
    session = GameSession(SplitOrStealKernel(), _config())
    await session.start()

    first = await session.submit(
        "req_1",
        {"choice": "split"},
        actor_id="alice",
        idempotency_key="alice-choice",
    )
    second = await session.submit(
        "req_2",
        {"choice": "steal"},
        actor_id="bob",
        idempotency_key="bob-choice",
    )
    projection = await session.projection(Audience.public())

    assert first.accepted is True
    assert second.accepted is True
    assert [request.status for request in session.requests] == ["resolved", "resolved"]
    assert projection.status == "complete"
    assert projection.phase == "complete"
    assert projection.result is not None
    assert projection.result.status == "win"
    assert projection.result.winner_ids == ["bob"]
    assert projection.visible_state["choices"] == {"alice": "split", "bob": "steal"}
    assert projection.visible_state["payoffs"] == {"alice": 0, "bob": 100}


@pytest.mark.asyncio
async def test_split_or_steal_rejects_duplicate_choice_before_reveal() -> None:
    session = GameSession(SplitOrStealKernel(), _config())
    await session.start()

    await session.submit(
        "req_1",
        {"choice": "split"},
        actor_id="alice",
        idempotency_key="alice-choice",
    )
    duplicate = await session.submit(
        "req_1",
        {"choice": "steal"},
        actor_id="alice",
        idempotency_key="alice-choice-2",
    )

    assert duplicate.accepted is False
    assert duplicate.issues[0].code == "choice_already_submitted"


@pytest.mark.asyncio
async def test_split_or_steal_scripted_session_replays_identically() -> None:
    summary = await run_scripted_session(SplitOrStealKernel(), _config(), _script(), seed=42)

    replayed = await replay_session(
        SplitOrStealKernel(),
        summary.config,
        summary.seed,
        summary.accepted_submissions,
        expected_trace=summary.comparable_trace,
    )

    assert replayed.matched is True


def _script() -> list[dict]:
    return [
        {"actor_id": "alice", "payload": {"choice": "split"}, "idempotency_key": "alice-choice"},
        {"actor_id": "bob", "payload": {"choice": "steal"}, "idempotency_key": "bob-choice"},
    ]


def _config() -> GameConfig:
    return GameConfig(players=[Player(id="alice", name="Alice"), Player(id="bob", name="Bob")])