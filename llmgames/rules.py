from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from llmgames.models import (
    Audience,
    GameConfig,
    InteractionRequest,
    RequestSpec,
    RulesContext,
    StateProjection,
    Submission,
    TransitionResult,
    ValidationIssue,
)


class RulesKernel(Protocol):
    game_id: str
    state_model: type[BaseModel]

    def initial_state(self, config: GameConfig, ctx: RulesContext) -> BaseModel:
        ...

    def current_requests(self, state: BaseModel, ctx: RulesContext) -> list[RequestSpec]:
        ...

    def validate_submission(
        self,
        state: BaseModel,
        request: InteractionRequest,
        submission: Submission,
        ctx: RulesContext,
    ) -> list[ValidationIssue]:
        ...

    def resolve(
        self,
        state: BaseModel,
        requests: list[InteractionRequest],
        submissions: list[Submission],
        ctx: RulesContext,
    ) -> TransitionResult:
        ...

    def project_state(
        self, state: BaseModel, audience: Audience, ctx: RulesContext
    ) -> StateProjection:
        ...
