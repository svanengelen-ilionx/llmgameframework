import pytest
from pydantic import BaseModel

from llmgames import (
    Audience,
    GameConfig,
    GameSession,
    InteractionRequest,
    LegalOptions,
    Player,
    RequestSpec,
    RulesContext,
    StateProjection,
    Submission,
    TransitionResult,
    ValidationIssue,
)


class TinyState(BaseModel):
    active: bool = True


class ConflictKernel:
    game_id = "conflict"
    state_model = TinyState

    def __init__(self, *, changed_field: str) -> None:
        self.changed_field = changed_field
        self.changed = False

    def initial_state(self, config: GameConfig, ctx: RulesContext) -> TinyState:
        return TinyState()

    def current_requests(self, state: TinyState, ctx: RulesContext) -> list[RequestSpec]:
        kwargs = {
            "key": "act:alice",
            "kind": "act",
            "actor_id": "alice",
            "mode": "single",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            "legal_options": LegalOptions(kind="custom", examples=[{}]),
        }
        if self.changed:
            if self.changed_field == "kind":
                kwargs["kind"] = "other"
            elif self.changed_field == "actor_id":
                kwargs["actor_id"] = "bob"
            elif self.changed_field == "mode":
                kwargs["mode"] = "barrier"
            elif self.changed_field == "input_schema":
                kwargs["input_schema"] = {"type": "object", "required": ["value"]}
        return [RequestSpec(**kwargs)]

    def validate_submission(
        self,
        state: TinyState,
        request: InteractionRequest,
        submission: Submission,
        ctx: RulesContext,
    ) -> list[ValidationIssue]:
        return []

    def resolve(
        self,
        state: TinyState,
        requests: list[InteractionRequest],
        submissions: list[Submission],
        ctx: RulesContext,
    ) -> TransitionResult:
        return TransitionResult(new_state=state)

    def project_state(self, state: TinyState, audience: Audience, ctx: RulesContext) -> StateProjection:
        return StateProjection(visible_state={"active": state.active})


class DisappearingRequestKernel(ConflictKernel):
    game_id = "disappearing_request"

    def __init__(self) -> None:
        super().__init__(changed_field="kind")

    def current_requests(self, state: TinyState, ctx: RulesContext) -> list[RequestSpec]:
        if not state.active:
            return []
        return [
            RequestSpec(
                key="act:alice",
                kind="act",
                actor_id="alice",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                legal_options=LegalOptions(kind="custom", examples=[{}]),
            )
        ]

    def resolve(
        self,
        state: TinyState,
        requests: list[InteractionRequest],
        submissions: list[Submission],
        ctx: RulesContext,
    ) -> TransitionResult:
        return TransitionResult(new_state=TinyState(active=False))


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_field", ["kind", "actor_id", "mode", "input_schema"])
async def test_pending_request_spec_conflicts_raise_clear_error(changed_field: str) -> None:
    kernel = ConflictKernel(changed_field=changed_field)
    session = GameSession(kernel, _config())
    await session.start()

    kernel.changed = True

    with pytest.raises(ValueError, match="Pending request spec conflict"):
        await session.advance()


@pytest.mark.asyncio
async def test_disappearing_pending_request_is_cancelled_and_rejects_submission() -> None:
    session = GameSession(DisappearingRequestKernel(), _config())
    await session.start()

    result = await session.submit("req_1", {}, actor_id="alice", idempotency_key="first")
    retry = await session.submit("req_1", {}, actor_id="alice", idempotency_key="second")

    assert result.accepted is True
    assert session.requests[0].status == "cancelled"
    assert retry.accepted is False
    assert retry.issues[0].code == "request_not_pending"


def _config() -> GameConfig:
    return GameConfig(players=[Player(id="alice", name="Alice"), Player(id="bob", name="Bob")])