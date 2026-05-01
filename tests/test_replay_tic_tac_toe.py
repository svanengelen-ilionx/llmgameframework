import pytest

from llmgames import GameConfig, Player
from llmgames.games import TicTacToeKernel
from llmgames.testing import replay_session, run_scripted_session


@pytest.mark.asyncio
async def test_tic_tac_toe_scripted_session_replays_identically() -> None:
    summary = await run_scripted_session(TicTacToeKernel(), _config(), _winning_script(), seed=42)

    replayed = await replay_session(
        TicTacToeKernel(),
        summary.config,
        summary.seed,
        summary.accepted_submissions,
        expected_trace=summary.comparable_trace,
    )

    assert replayed.matched is True
    assert replayed.first_difference is None
    assert replayed.comparable_trace == summary.comparable_trace


@pytest.mark.asyncio
async def test_tic_tac_toe_replay_reports_first_difference() -> None:
    summary = await run_scripted_session(TicTacToeKernel(), _config(), _winning_script(), seed=42)
    changed_trace = summary.comparable_trace.model_copy(deep=True)
    changed_trace.event_cursor = 999

    replayed = await replay_session(
        TicTacToeKernel(),
        summary.config,
        summary.seed,
        summary.accepted_submissions,
        expected_trace=changed_trace,
    )

    assert replayed.matched is False
    assert replayed.first_difference == "event_cursor"


@pytest.mark.asyncio
async def test_tic_tac_toe_replay_ignores_submission_timestamps() -> None:
    summary = await run_scripted_session(TicTacToeKernel(), _config(), _winning_script(), seed=42)

    assert all("submitted_at" not in item for item in summary.comparable_trace.accepted_submissions)


def _winning_script() -> list[dict]:
    return [
        {"actor_id": "alice", "payload": {"row": 0, "col": 0}, "idempotency_key": "move-1"},
        {"actor_id": "bob", "payload": {"row": 1, "col": 0}, "idempotency_key": "move-2"},
        {"actor_id": "alice", "payload": {"row": 0, "col": 1}, "idempotency_key": "move-3"},
        {"actor_id": "bob", "payload": {"row": 1, "col": 1}, "idempotency_key": "move-4"},
        {"actor_id": "alice", "payload": {"row": 0, "col": 2}, "idempotency_key": "move-5"},
    ]


def _config() -> GameConfig:
    return GameConfig(players=[Player(id="alice", name="Alice"), Player(id="bob", name="Bob")])