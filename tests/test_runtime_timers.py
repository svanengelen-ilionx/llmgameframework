from datetime import datetime, timedelta, timezone

import pytest
from pydantic import BaseModel

from llmgames import (
    Audience,
    GameConfig,
    GameSession,
    InteractionRequest,
    ManualClock,
    Player,
    RequestSpec,
    RulesContext,
    StateProjection,
    Submission,
    TransitionResult,
    ValidationIssue,
)
from llmgames.storage import restore_session, snapshot_session


class TimerState(BaseModel):
    phase: str = "waiting"
    deadline_at: datetime


class TimerKernel:
    game_id = "timer_test"
    state_model = TimerState

    def initial_state(self, config: GameConfig, ctx: RulesContext) -> TimerState:
        assert ctx.current_time is not None
        return TimerState(deadline_at=ctx.current_time + timedelta(seconds=5))

    def current_requests(self, state: TimerState, ctx: RulesContext) -> list[RequestSpec]:
        if state.phase != "waiting":
            return []
        return [
            RequestSpec(
                key="timer:alice",
                kind="timer_action",
                actor_id="alice",
                mode="timer",
                input_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
                deadline_at=state.deadline_at,
                legal_options={"kind": "custom", "examples": [{"ok": True}]},
            )
        ]

    def validate_submission(
        self,
        state: TimerState,
        request: InteractionRequest,
        submission: Submission,
        ctx: RulesContext,
    ) -> list[ValidationIssue]:
        return []

    def resolve(
        self,
        state: TimerState,
        requests: list[InteractionRequest],
        submissions: list[Submission],
        ctx: RulesContext,
    ) -> TransitionResult:
        new_state = state.model_copy(deep=True)
        new_state.phase = "done"
        return TransitionResult(new_state=new_state, resolved_request_keys=[requests[-1].spec_key])

    def project_state(self, state: TimerState, audience: Audience, ctx: RulesContext) -> StateProjection:
        return StateProjection(phase=state.phase, visible_state={"phase": state.phase})


@pytest.mark.asyncio
async def test_manual_clock_expires_pending_timer_request() -> None:
    clock = ManualClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
    session = GameSession(TimerKernel(), _config(), clock=clock)
    await session.start()

    clock.advance(timedelta(seconds=5))
    await session.advance()

    assert session.requests[0].status == "expired"
    assert session.requests[0].resolved_event_seq == 1
    assert [request.status for request in session.requests] == ["expired"]
    assert session.events[0].kind == "request.expired"
    assert session.events[0].payload["request_spec_key"] == "timer:alice"


@pytest.mark.asyncio
async def test_submission_after_deadline_is_rejected_as_not_pending() -> None:
    clock = ManualClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
    session = GameSession(TimerKernel(), _config(), clock=clock)
    await session.start()

    clock.advance(timedelta(seconds=6))
    result = await session.submit("req_1", {"ok": True}, actor_id="alice", idempotency_key="late")

    assert result.accepted is False
    assert result.issues[0].code == "request_not_pending"
    assert session.requests[0].status == "expired"


@pytest.mark.asyncio
async def test_snapshot_restore_uses_injected_clock_for_deadlines() -> None:
    original_clock = ManualClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
    restored_clock = ManualClock(datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=5))
    session = GameSession(TimerKernel(), _config(), clock=original_clock)
    await session.start()

    restored = restore_session(TimerKernel(), snapshot_session(session), clock=restored_clock)
    await restored.advance()

    assert restored.requests[0].status == "expired"
    assert restored.events[0].payload["expired_at"] == restored_clock.now().isoformat()


def _config() -> GameConfig:
    return GameConfig(players=[Player(id="alice", name="Alice"), Player(id="bob", name="Bob")])