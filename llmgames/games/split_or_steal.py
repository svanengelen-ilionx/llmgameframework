from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from llmgames import (
    Audience,
    GameConfig,
    GameEventSpec,
    GameResult,
    InteractionRequest,
    LegalOptions,
    RequestSpec,
    RulesContext,
    StateProjection,
    Submission,
    TransitionResult,
    ValidationIssue,
)

Choice = Literal["split", "steal"]


class SplitOrStealState(BaseModel):
    round_number: int = 1
    submitted_player_ids: list[str] = Field(default_factory=list)
    choices: dict[str, Choice] = Field(default_factory=dict)
    revealed: bool = False

    model_config = ConfigDict(json_schema_extra={"private_paths": ["choices"]})


class SplitOrStealKernel:
    game_id = "split_or_steal"
    state_model = SplitOrStealState

    def initial_state(self, config: GameConfig, ctx: RulesContext) -> SplitOrStealState:
        return SplitOrStealState()

    def current_requests(self, state: SplitOrStealState, ctx: RulesContext) -> list[RequestSpec]:
        if state.revealed:
            return []
        return [
            RequestSpec(
                key=f"split_choice:{player.id}:round_{state.round_number}",
                kind="split_choice",
                actor_id=player.id,
                mode="barrier",
                input_schema={
                    "type": "object",
                    "properties": {"choice": {"type": "string", "enum": ["split", "steal"]}},
                    "required": ["choice"],
                    "additionalProperties": False,
                },
                legal_options=LegalOptions(
                    kind="choice",
                    examples=[{"choice": "split"}, {"choice": "steal"}],
                ),
            )
            for player in ctx.config.players
        ]

    def validate_submission(
        self,
        state: SplitOrStealState,
        request: InteractionRequest,
        submission: Submission,
        ctx: RulesContext,
    ) -> list[ValidationIssue]:
        if request.actor_id is not None and submission.actor_id != request.actor_id:
            return [
                ValidationIssue(
                    code="wrong_actor",
                    message="Only the requested player may submit this choice.",
                    path=["actor_id"],
                )
            ]
        if submission.actor_id in state.submitted_player_ids:
            return [
                ValidationIssue(
                    code="choice_already_submitted",
                    message="This player has already submitted a choice for the current round.",
                    path=["actor_id"],
                )
            ]
        if submission.payload.get("choice") not in {"split", "steal"}:
            return [
                ValidationIssue(
                    code="invalid_choice",
                    message="Choice must be either split or steal.",
                    path=["payload", "choice"],
                )
            ]
        return []

    def resolve(
        self,
        state: SplitOrStealState,
        requests: list[InteractionRequest],
        submissions: list[Submission],
        ctx: RulesContext,
    ) -> TransitionResult:
        new_state = state.model_copy(deep=True)
        submitted_actor_ids = [submission.actor_id for submission in submissions if submission.actor_id]
        for actor_id in submitted_actor_ids:
            if actor_id not in new_state.submitted_player_ids:
                new_state.submitted_player_ids.append(actor_id)

        if len(set(submitted_actor_ids)) < len(ctx.config.players):
            return TransitionResult(
                new_state=new_state,
                events=[GameEventSpec(kind="choice_submitted", payload={"submitted": sorted(new_state.submitted_player_ids)})],
            )

        new_state.choices = {
            submission.actor_id: submission.payload["choice"]
            for submission in submissions
            if submission.actor_id is not None
        }
        new_state.revealed = True
        return TransitionResult(
            new_state=new_state,
            events=[GameEventSpec(kind="choices_revealed", payload={"choices": new_state.choices})],
            resolved_request_keys=[request.spec_key for request in requests],
        )

    def project_state(
        self, state: SplitOrStealState, audience: Audience, ctx: RulesContext
    ) -> StateProjection:
        visible_state = {
            "round_number": state.round_number,
            "submitted_player_ids": sorted(state.submitted_player_ids),
            "revealed": state.revealed,
        }
        result = None
        if state.revealed:
            visible_state["choices"] = state.choices
            payoffs = _payoffs(state.choices)
            visible_state["payoffs"] = payoffs
            winner_ids = [player_id for player_id, payoff in payoffs.items() if payoff == max(payoffs.values())]
            result = GameResult(
                status="draw" if len(winner_ids) == len(ctx.config.players) else "win",
                winner_ids=winner_ids,
                reason="choices_revealed",
                metadata={"payoffs": payoffs},
            )
        return StateProjection(
            phase="complete" if state.revealed else "choosing",
            visible_state=visible_state,
            result=result,
        )


def _payoffs(choices: dict[str, Choice]) -> dict[str, int]:
    splitters = [player_id for player_id, choice in choices.items() if choice == "split"]
    stealers = [player_id for player_id, choice in choices.items() if choice == "steal"]
    if len(splitters) == 2:
        return {player_id: 50 for player_id in choices}
    if len(stealers) == 2:
        return {player_id: 0 for player_id in choices}
    return {player_id: (100 if player_id in stealers else 0) for player_id in choices}