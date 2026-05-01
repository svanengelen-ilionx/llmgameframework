from pydantic import BaseModel, ConfigDict, Field

from llmgames import (
    Audience,
    GameConfig,
    GameResult,
    InteractionRequest,
    RequestSpec,
    RulesContext,
    StateProjection,
    Submission,
    TransitionResult,
    ValidationIssue,
)
from llmgames.testing import validate_kernel


class TinyState(BaseModel):
    value: int = 0


class PrivateState(BaseModel):
    hidden: dict[str, str] = Field(default_factory=lambda: {"alice": "steal"})

    model_config = ConfigDict(json_schema_extra={"private_paths": ["hidden"]})


class EmptyPrivateState(BaseModel):
    hidden: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(json_schema_extra={"private_paths": ["hidden"]})


class DuplicateRequestKernel:
    game_id = "duplicate_request"
    state_model = TinyState

    def initial_state(self, config: GameConfig, ctx: RulesContext) -> TinyState:
        return TinyState()

    def current_requests(self, state: TinyState, ctx: RulesContext) -> list[RequestSpec]:
        return [
            RequestSpec(key="act:alice", kind="act", actor_id="alice", input_schema={"type": "object"}),
            RequestSpec(key="act:alice", kind="act", actor_id="alice", input_schema={"type": "object"}),
        ]

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
        return StateProjection(visible_state={"value": state.value})


class MutatingResolveKernel(DuplicateRequestKernel):
    game_id = "mutating_resolve"

    def current_requests(self, state: TinyState, ctx: RulesContext) -> list[RequestSpec]:
        return [
            RequestSpec(
                key="act:alice",
                kind="act",
                actor_id="alice",
                input_schema={"type": "object"},
                legal_options={"kind": "custom", "examples": [{}]},
            )
        ]

    def resolve(
        self,
        state: TinyState,
        requests: list[InteractionRequest],
        submissions: list[Submission],
        ctx: RulesContext,
    ) -> TransitionResult:
        state.value = 1
        return TransitionResult(new_state=state, resolved_request_keys=[requests[0].spec_key])


class LeakyProjectionKernel(DuplicateRequestKernel):
    game_id = "leaky_projection"
    state_model = PrivateState

    def initial_state(self, config: GameConfig, ctx: RulesContext) -> PrivateState:
        return PrivateState()

    def current_requests(self, state: PrivateState, ctx: RulesContext) -> list[RequestSpec]:
        return []

    def project_state(self, state: PrivateState, audience: Audience, ctx: RulesContext) -> StateProjection:
        return StateProjection(visible_state={"hidden": state.hidden})


class PlayerOnlyLeakyProjectionKernel(LeakyProjectionKernel):
    game_id = "player_only_leaky_projection"

    def project_state(self, state: PrivateState, audience: Audience, ctx: RulesContext) -> StateProjection:
        if audience.kind == "player":
            return StateProjection(visible_state={"nested": {"hidden": state.hidden}})
        return StateProjection(visible_state={"safe": True})


class LLMOnlyLeakyProjectionKernel(LeakyProjectionKernel):
    game_id = "llm_only_leaky_projection"

    def project_state(self, state: PrivateState, audience: Audience, ctx: RulesContext) -> StateProjection:
        if audience.kind == "llm":
            return StateProjection(visible_state={"nested": {"hidden": state.hidden}})
        return StateProjection(visible_state={"safe": True})


class TerminalRevealProjectionKernel(LeakyProjectionKernel):
    game_id = "terminal_reveal_projection"

    def project_state(self, state: PrivateState, audience: Audience, ctx: RulesContext) -> StateProjection:
        return StateProjection(
            visible_state={"hidden": state.hidden},
            result=GameResult(status="win", winner_ids=["alice"]),
        )


class EmptyPrivateProjectionKernel(LeakyProjectionKernel):
    game_id = "empty_private_projection"
    state_model = EmptyPrivateState

    def initial_state(self, config: GameConfig, ctx: RulesContext) -> EmptyPrivateState:
        return EmptyPrivateState()

    def current_requests(self, state: EmptyPrivateState, ctx: RulesContext) -> list[RequestSpec]:
        return []

    def project_state(self, state: EmptyPrivateState, audience: Audience, ctx: RulesContext) -> StateProjection:
        return StateProjection(visible_state={"hidden": state.hidden})


def test_duplicate_request_keys_are_diagnostic() -> None:
    issues = validate_kernel(DuplicateRequestKernel())

    assert any(issue.method == "current_requests" and "duplicate" in issue.message for issue in issues)


def test_resolve_mutation_is_diagnostic() -> None:
    issues = validate_kernel(MutatingResolveKernel())

    assert any(issue.method == "resolve" and "mutated" in issue.message for issue in issues)


def test_private_path_projection_leak_is_diagnostic() -> None:
    issues = validate_kernel(LeakyProjectionKernel())

    assert any(
        issue.method == "project_state"
        and "audience='public'" in issue.message
        and "private path 'hidden'" in issue.message
        and "projection path 'visible_state.hidden'" in issue.message
        for issue in issues
    )


def test_player_private_path_projection_leak_names_player_audience() -> None:
    issues = validate_kernel(PlayerOnlyLeakyProjectionKernel())

    assert any(
        issue.method == "project_state"
        and "audience='player:alice'" in issue.message
        and "projection path 'visible_state.nested.hidden'" in issue.message
        for issue in issues
    )


def test_llm_private_path_projection_leak_names_llm_audience() -> None:
    issues = validate_kernel(LLMOnlyLeakyProjectionKernel())

    assert any(
        issue.method == "project_state"
        and "audience='llm:alice'" in issue.message
        and "projection path 'visible_state.nested.hidden'" in issue.message
        for issue in issues
    )


def test_terminal_projection_may_reveal_private_path() -> None:
    issues = validate_kernel(TerminalRevealProjectionKernel())

    assert issues == []


def test_empty_private_path_is_not_reported_as_leak() -> None:
    issues = validate_kernel(EmptyPrivateProjectionKernel())

    assert issues == []
