from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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
    order_set_option,
)

OrderAction = Literal["hold", "move"]

ZONES = ["north", "center", "south"]


class ComplexOrdersState(BaseModel):
    turn_number: int = 1
    positions: dict[str, str] = Field(default_factory=dict)
    submitted_player_ids: list[str] = Field(default_factory=list)
    resolved: bool = False
    resolution_log: list[dict] = Field(default_factory=list)


class ComplexOrdersKernel:
    game_id = "complex_orders"
    state_model = ComplexOrdersState

    def initial_state(self, config: GameConfig, ctx: RulesContext) -> ComplexOrdersState:
        return ComplexOrdersState(
            positions={_unit_id(player.id): ZONES[index % len(ZONES)] for index, player in enumerate(config.players)}
        )

    def current_requests(self, state: ComplexOrdersState, ctx: RulesContext) -> list[RequestSpec]:
        if state.resolved:
            return []
        return [
            RequestSpec(
                key=f"order_set:{player.id}:turn_{state.turn_number}",
                kind="order_set",
                actor_id=player.id,
                mode="barrier",
                input_schema=_order_set_schema(player.id),
                legal_options=LegalOptions(
                    kind="order_set",
                    options=[
                        order_set_option(
                            "hold",
                            label="Hold position",
                            payload={"orders": [{"unit_id": _unit_id(player.id), "action": "hold"}]},
                            order_count=1,
                            subject_ids=[_unit_id(player.id)],
                        )
                    ],
                    examples=[{"orders": [{"unit_id": _unit_id(player.id), "action": "hold"}]}],
                    metadata={"turn_number": state.turn_number},
                ),
            )
            for player in ctx.config.players
        ]

    def validate_submission(
        self,
        state: ComplexOrdersState,
        request: InteractionRequest,
        submission: Submission,
        ctx: RulesContext,
    ) -> list[ValidationIssue]:
        if request.actor_id is not None and submission.actor_id != request.actor_id:
            return [
                ValidationIssue(
                    code="wrong_actor",
                    message="Only the requested player may submit this order set.",
                    path=["actor_id"],
                )
            ]
        if submission.actor_id in state.submitted_player_ids:
            return [
                ValidationIssue(
                    code="order_set_already_submitted",
                    message="This player has already submitted a final order set for the current turn.",
                    path=["actor_id"],
                    hint="Draft/final revision support is not part of this reference game yet.",
                )
            ]

        orders = submission.payload.get("orders", [])
        if len(orders) != 1:
            return [
                ValidationIssue(
                    code="invalid_order_count",
                    message="This spike expects exactly one order per player.",
                    path=["payload", "orders"],
                )
            ]
        order = orders[0]
        expected_unit_id = _unit_id(submission.actor_id or "")
        if order.get("unit_id") != expected_unit_id:
            return [
                ValidationIssue(
                    code="invalid_unit",
                    message="Order set must reference the submitting player's unit.",
                    path=["payload", "orders", 0, "unit_id"],
                    hint="Use the unit_id from legal_options metadata.",
                )
            ]
        if order.get("action") == "move" and order.get("target") not in ZONES:
            return [
                ValidationIssue(
                    code="invalid_target",
                    message="Move orders must target a known zone.",
                    path=["payload", "orders", 0, "target"],
                )
            ]
        return []

    def resolve(
        self,
        state: ComplexOrdersState,
        requests: list[InteractionRequest],
        submissions: list[Submission],
        ctx: RulesContext,
    ) -> TransitionResult:
        new_state = state.model_copy(deep=True)
        for submission in submissions:
            if submission.actor_id is not None and submission.actor_id not in new_state.submitted_player_ids:
                new_state.submitted_player_ids.append(submission.actor_id)

        if len(set(new_state.submitted_player_ids)) < len(ctx.config.players):
            return TransitionResult(
                new_state=new_state,
                events=[
                    GameEventSpec(
                        kind="order_set_submitted",
                        payload={"submitted": sorted(new_state.submitted_player_ids)},
                    )
                ],
            )

        outcomes = _resolve_batch(state.positions, submissions)
        new_state.positions = {outcome["unit_id"]: outcome["to"] for outcome in outcomes}
        new_state.resolved = True
        new_state.resolution_log = outcomes
        return TransitionResult(
            new_state=new_state,
            events=[
                GameEventSpec(
                    kind="order_batch_resolved",
                    payload={
                        "turn_number": state.turn_number,
                        "order_count": len(outcomes),
                        "outcomes": outcomes,
                    },
                )
            ],
            resolved_request_keys=[request.spec_key for request in requests],
        )

    def project_state(self, state: ComplexOrdersState, audience: Audience, ctx: RulesContext) -> StateProjection:
        visible_state = {
            "turn_number": state.turn_number,
            "positions": state.positions,
            "submitted_player_ids": sorted(state.submitted_player_ids),
            "resolved": state.resolved,
        }
        result = None
        if state.resolved:
            visible_state["resolution_log"] = state.resolution_log
            result = GameResult(status="draw", reason="order_batch_resolved")
        return StateProjection(
            phase="complete" if state.resolved else "ordering",
            visible_state=visible_state,
            result=result,
        )


def _order_set_schema(player_id: str) -> dict:
    return {
        "type": "object",
        "properties": {
            "orders": {
                "type": "array",
                "minItems": 1,
                "maxItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "unit_id": {"type": "string", "enum": [_unit_id(player_id)]},
                        "action": {"type": "string", "enum": ["hold", "move"]},
                        "target": {"type": "string", "enum": ZONES},
                    },
                    "required": ["unit_id", "action"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["orders"],
        "additionalProperties": False,
    }


def _resolve_batch(positions: dict[str, str], submissions: list[Submission]) -> list[dict]:
    intents = []
    for submission in sorted(submissions, key=lambda item: item.actor_id or ""):
        order = submission.payload["orders"][0]
        unit_id = order["unit_id"]
        origin = positions[unit_id]
        target = order.get("target", origin) if order["action"] == "move" else origin
        intents.append({"actor_id": submission.actor_id, "unit_id": unit_id, "action": order["action"], "from": origin, "target": target})

    target_counts = {intent["target"]: 0 for intent in intents}
    for intent in intents:
        target_counts[intent["target"]] += 1

    outcomes = []
    for intent in intents:
        success = intent["action"] == "hold" or target_counts[intent["target"]] == 1
        outcomes.append(
            {
                **intent,
                "to": intent["target"] if success else intent["from"],
                "status": "succeeded" if success else "blocked",
            }
        )
    return outcomes


def _unit_id(player_id: str) -> str:
    return f"{player_id}:unit_1"