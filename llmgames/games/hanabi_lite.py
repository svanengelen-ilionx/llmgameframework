from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from llmgames import (
    Audience,
    GameConfig,
    GameEventSpec,
    GameResult,
    InteractionRequest,
    LegalOption,
    LegalOptions,
    RequestSpec,
    RulesContext,
    StateProjection,
    Submission,
    TransitionResult,
    ValidationIssue,
    card_option,
    hint_option,
)

Color = Literal["red", "blue"]


class HanabiCard(BaseModel):
    id: str
    color: Color
    rank: int


class HanabiLiteState(BaseModel):
    hands: dict[str, list[HanabiCard]]
    deck: list[HanabiCard] = Field(default_factory=list)
    played: dict[str, int] = Field(default_factory=lambda: {"red": 0, "blue": 0})
    discard: list[HanabiCard] = Field(default_factory=list)
    clues: dict[str, dict[int, list[dict[str, Any]]]] = Field(default_factory=dict)
    clue_tokens: int = 3
    current_player_index: int = 0
    turn: int = 1

    model_config = ConfigDict(
        json_schema_extra={
            "private_paths_by_audience": {
                "public": ["deck.*", "hands.*.*"],
                "player": ["deck.*", "hands.{audience.player_id}.*"],
                "llm": ["deck.*", "hands.{audience.player_id}.*"],
            }
        }
    )


class HanabiLiteKernel:
    game_id = "hanabi_lite"
    state_model = HanabiLiteState

    def initial_state(self, config: GameConfig, ctx: RulesContext) -> HanabiLiteState:
        player_ids = [player.id for player in config.players]
        deck = _starter_deck()
        hands = {player_id: [deck.pop(0), deck.pop(0)] for player_id in player_ids}
        return HanabiLiteState(
            hands=hands,
            deck=deck,
            clues={player_id: {} for player_id in player_ids},
        )

    def current_requests(self, state: HanabiLiteState, ctx: RulesContext) -> list[RequestSpec]:
        if _is_complete(state) or _all_hands_empty(state):
            return []
        player = ctx.config.players[state.current_player_index]
        return [
            RequestSpec(
                key=f"hanabi_action:{player.id}:turn_{state.turn}",
                kind="hanabi_action",
                actor_id=player.id,
                input_schema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["clue", "play", "discard"]},
                        "target_id": {"type": "string"},
                        "clue_type": {"type": "string", "enum": ["color", "rank"]},
                        "value": {"type": ["string", "integer"]},
                        "slot": {"type": "integer", "minimum": 0},
                    },
                    "required": ["action"],
                    "additionalProperties": False,
                },
                legal_options=_legal_options(state, player.id, ctx),
            )
        ]

    def validate_submission(
        self,
        state: HanabiLiteState,
        request: InteractionRequest,
        submission: Submission,
        ctx: RulesContext,
    ) -> list[ValidationIssue]:
        if request.actor_id is not None and submission.actor_id != request.actor_id:
            return [_issue("wrong_actor", "Only the active player may submit this Hanabi action.", ["actor_id"])]
        action = submission.payload.get("action")
        if action == "clue":
            return _validate_clue(state, submission.payload, request.actor_id, ctx)
        if action in {"play", "discard"}:
            return _validate_slot_action(state, submission.payload, request.actor_id)
        return [_issue("invalid_action", "Action must be clue, play, or discard.", ["payload", "action"])]

    def resolve(
        self,
        state: HanabiLiteState,
        requests: list[InteractionRequest],
        submissions: list[Submission],
        ctx: RulesContext,
    ) -> TransitionResult:
        if not requests or not submissions:
            return TransitionResult(new_state=state)
        request = requests[-1]
        submission = submissions[-1]
        actor_id = request.actor_id
        if actor_id is None:
            return TransitionResult(new_state=state)

        new_state = state.model_copy(deep=True)
        payload = submission.payload
        events: list[GameEventSpec] = []
        if payload["action"] == "clue":
            target_id = payload["target_id"]
            clue_type = payload["clue_type"]
            clue_value = payload["value"]
            new_state.clue_tokens -= 1
            matches = _matching_slots(new_state.hands[target_id], clue_type, clue_value)
            target_clues = new_state.clues.setdefault(target_id, {})
            for slot in matches:
                target_clues.setdefault(slot, []).append({"type": clue_type, "value": clue_value})
            events.append(
                GameEventSpec(
                    kind="clue_given",
                    payload={
                        "from": actor_id,
                        "to": target_id,
                        "clue_type": clue_type,
                        "value": clue_value,
                        "slots": matches,
                    },
                )
            )
        else:
            slot = payload["slot"]
            card = new_state.hands[actor_id].pop(slot)
            _shift_clues_after_removed_slot(new_state.clues.setdefault(actor_id, {}), slot)
            if payload["action"] == "play" and card.rank == new_state.played[card.color] + 1:
                new_state.played[card.color] = card.rank
                if card.rank == 3:
                    new_state.clue_tokens = min(3, new_state.clue_tokens + 1)
                events.append(
                    GameEventSpec(
                        kind="card_played",
                        payload={"player_id": actor_id, "card": _public_card(card)},
                    )
                )
            else:
                new_state.discard.append(card)
                events.append(
                    GameEventSpec(
                        kind="card_discarded" if payload["action"] == "discard" else "card_misplayed",
                        payload={"player_id": actor_id, "card": _public_card(card)},
                    )
                )
            if new_state.deck:
                new_state.hands[actor_id].append(new_state.deck.pop(0))

        new_state.turn += 1
        new_state.current_player_index = (new_state.current_player_index + 1) % len(ctx.config.players)
        return TransitionResult(new_state=new_state, events=events, resolved_request_keys=[request.spec_key])

    def project_state(self, state: HanabiLiteState, audience: Audience, ctx: RulesContext) -> StateProjection:
        result = None
        if _is_complete(state):
            result = GameResult(
                status="win",
                winner_ids=[player.id for player in ctx.config.players],
                reason="fireworks_complete",
            )
        elif _all_hands_empty(state):
            result = GameResult(status="draw", reason="no_cards_remaining")

        visible_state: dict[str, Any] = {
            "current_player_id": ctx.config.players[state.current_player_index].id,
            "turn": state.turn,
            "clue_tokens": state.clue_tokens,
            "played": state.played,
            "discard": [_public_card(card) for card in state.discard],
            "deck_count": len(state.deck),
        }
        if audience.kind in {"player", "llm"} and audience.player_id is not None:
            visible_state["own_hand"] = _own_hand_projection(state, audience.player_id)
            visible_state["other_hands"] = {
                player_id: [_public_card(card) for card in hand]
                for player_id, hand in state.hands.items()
                if player_id != audience.player_id
            }
        else:
            visible_state["hand_sizes"] = {player_id: len(hand) for player_id, hand in state.hands.items()}

        return StateProjection(phase="complete" if result else "playing", visible_state=visible_state, result=result)


def _starter_deck() -> list[HanabiCard]:
    return [
        HanabiCard(id="r1a", color="red", rank=1),
        HanabiCard(id="b1a", color="blue", rank=1),
        HanabiCard(id="r2a", color="red", rank=2),
        HanabiCard(id="b2a", color="blue", rank=2),
        HanabiCard(id="r3a", color="red", rank=3),
        HanabiCard(id="b3a", color="blue", rank=3),
    ]


def _legal_options(state: HanabiLiteState, actor_id: str, ctx: RulesContext) -> LegalOptions:
    options: list[LegalOption] = []
    if state.clue_tokens > 0:
        for player in ctx.config.players:
            if player.id == actor_id or not state.hands[player.id]:
                continue
            card = state.hands[player.id][0]
            options.append(
                hint_option(
                    value=f"clue:{player.id}:color:{card.color}",
                    label=f"Tell {player.name} about {card.color} cards",
                    payload={"action": "clue", "target_id": player.id, "clue_type": "color", "value": card.color},
                    target_id=player.id,
                    clue_type="color",
                )
            )
            break
    if state.hands.get(actor_id):
        options.append(card_option(value="play:0", label="Play slot 0", payload={"action": "play", "slot": 0}, slot=0))
        options.append(
            card_option(
                value="discard:0",
                label="Discard slot 0",
                payload={"action": "discard", "slot": 0},
                slot=0,
            )
        )
    return LegalOptions(
        kind="hanabi_action",
        options=options,
        examples=[option.payload for option in options if option.payload is not None],
    )


def _validate_clue(
    state: HanabiLiteState,
    payload: dict[str, Any],
    actor_id: str | None,
    ctx: RulesContext,
) -> list[ValidationIssue]:
    if state.clue_tokens <= 0:
        return [_issue("no_clue_tokens", "A clue requires an available clue token.", ["payload", "action"])]
    target_id = payload.get("target_id")
    player_ids = {player.id for player in ctx.config.players}
    if target_id not in player_ids or target_id == actor_id:
        return [_issue("invalid_clue_target", "A clue must target another player.", ["payload", "target_id"])]
    clue_type = payload.get("clue_type")
    clue_value = payload.get("value")
    if clue_type not in {"color", "rank"}:
        return [_issue("invalid_clue_type", "Clue type must be color or rank.", ["payload", "clue_type"])]
    if clue_type == "color" and not isinstance(clue_value, str):
        return [_issue("invalid_clue_value", "A color clue value must be a color string.", ["payload", "value"])]
    if clue_type == "rank" and not isinstance(clue_value, int):
        return [_issue("invalid_clue_value", "A rank clue value must be an integer rank.", ["payload", "value"])]
    if not _matching_slots(state.hands[target_id], clue_type, clue_value):
        return [_issue("empty_clue", "A clue must identify at least one card in the target hand.", ["payload", "value"])]
    return []


def _validate_slot_action(
    state: HanabiLiteState,
    payload: dict[str, Any],
    actor_id: str | None,
) -> list[ValidationIssue]:
    if actor_id is None:
        return [_issue("missing_actor", "A card action requires an actor.", ["actor_id"])]
    slot = payload.get("slot")
    if not isinstance(slot, int) or not (0 <= slot < len(state.hands.get(actor_id, []))):
        return [_issue("invalid_slot", "Slot must refer to a card in the actor's hand.", ["payload", "slot"])]
    return []


def _matching_slots(hand: list[HanabiCard], clue_type: str, clue_value: Any) -> list[int]:
    if clue_type == "color":
        return [index for index, card in enumerate(hand) if card.color == clue_value]
    if clue_type == "rank":
        return [index for index, card in enumerate(hand) if card.rank == clue_value]
    return []


def _own_hand_projection(state: HanabiLiteState, player_id: str) -> list[dict[str, Any]]:
    return [
        {"slot": slot, "clues": state.clues.get(player_id, {}).get(slot, [])}
        for slot, _card in enumerate(state.hands.get(player_id, []))
    ]


def _public_card(card: HanabiCard) -> dict[str, Any]:
    return {"color": card.color, "rank": card.rank}


def _shift_clues_after_removed_slot(clues: dict[int, list[dict[str, Any]]], removed_slot: int) -> None:
    shifted = {
        (slot - 1 if slot > removed_slot else slot): value
        for slot, value in clues.items()
        if slot != removed_slot
    }
    clues.clear()
    clues.update(shifted)


def _is_complete(state: HanabiLiteState) -> bool:
    return all(rank >= 3 for rank in state.played.values())


def _all_hands_empty(state: HanabiLiteState) -> bool:
    return not state.deck and all(not hand for hand in state.hands.values())


def _issue(code: str, message: str, path: list[str | int]) -> ValidationIssue:
    return ValidationIssue(code=code, message=message, path=path)