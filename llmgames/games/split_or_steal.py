from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from llmgames.core.contracts import (
    ActionContext,
    ActionDefinition,
    ActionResult,
    Event,
    GameInfo,
    GameResult,
    Message,
    Observation,
    Player,
)


Choice = Literal["split", "steal"]
Phase = Literal["conversation", "choice", "end"]


@dataclass
class SplitOrStealState:
    players: list[Player]
    phase: Phase = "conversation"
    messages: list[Message] = field(default_factory=list)
    ready_players: set[str] = field(default_factory=set)
    choices: dict[str, Choice] = field(default_factory=dict)
    scores: dict[str, int] = field(default_factory=dict)
    max_messages: int = 6


class SplitOrSteal:
    rules = (
        "Talk first, then each player chooses split or steal. "
        "If both split, both score 50. If one steals while the other splits, "
        "the stealer scores 100 and the splitter scores 0. If both steal, both score 0."
    )

    def __init__(self, max_messages: int = 6) -> None:
        self.max_messages = max_messages
        self._actions = {
            "send_message": ActionDefinition(
                name="send_message",
                description="Send a public message during the conversation phase.",
                input_schema={
                    "type": "object",
                    "properties": {"text": {"type": "string", "minLength": 1, "maxLength": 500}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
                can_use=self._can_talk,
                handler=self._send_message,
            ),
            "ready": ActionDefinition(
                name="ready",
                description="Mark yourself ready to move from conversation to choice.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                can_use=self._can_talk,
                handler=self._ready,
            ),
            "end_turn": ActionDefinition(
                name="end_turn",
                description="Pass without sending a message.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                can_use=self._can_talk,
                handler=self._end_turn,
            ),
            "choose_split": ActionDefinition(
                name="choose_split",
                description="Choose to split the prize.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                can_use=self._can_choose,
                handler=self._choose_split,
            ),
            "choose_steal": ActionDefinition(
                name="choose_steal",
                description="Choose to steal the prize.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                can_use=self._can_choose,
                handler=self._choose_steal,
            ),
        }

    @property
    def actions(self) -> Mapping[str, ActionDefinition]:
        return self._actions

    def get_info(self) -> GameInfo:
        return GameInfo(
            name="Split or Steal",
            min_players=2,
            max_players=2,
            description="A two-player trust game with conversation and simultaneous-style choices.",
        )

    def create_initial_state(
        self,
        players: Sequence[Player],
        seed: int | None = None,
    ) -> SplitOrStealState:
        return SplitOrStealState(
            players=list(players),
            scores={player.id: 0 for player in players},
            max_messages=self.max_messages,
        )

    def get_observation(self, state: SplitOrStealState, player_id: str) -> Observation:
        return Observation(
            player_id=player_id,
            rules=self.rules,
            public={
                "phase": state.phase,
                "players": [player.id for player in state.players],
                "ready_players": sorted(state.ready_players),
                "message_count": len(state.messages),
                "max_messages": state.max_messages,
                "choices_submitted": sorted(state.choices),
            },
            private={"your_choice": state.choices.get(player_id)},
            messages=list(state.messages),
        )

    def get_available_actions(self, state: SplitOrStealState, player_id: str) -> list[ActionDefinition]:
        return [action for action in self.actions.values() if action.can_use(state, player_id)]

    def get_result(self, state: SplitOrStealState) -> GameResult:
        if not self.is_terminal(state):
            return GameResult(is_terminal=False, scores=dict(state.scores), reason="Game is still running")

        high_score = max(state.scores.values(), default=0)
        winners = [player_id for player_id, score in state.scores.items() if score == high_score]
        if high_score == 0 and len(winners) == len(state.players):
            winners = []
        return GameResult(
            is_terminal=True,
            scores=dict(state.scores),
            winners=winners,
            reason="Both players chose; scores resolved",
        )

    def is_terminal(self, state: SplitOrStealState) -> bool:
        return state.phase == "end"

    def _can_talk(self, state: SplitOrStealState, player_id: str) -> bool:
        return state.phase == "conversation"

    def _can_choose(self, state: SplitOrStealState, player_id: str) -> bool:
        return state.phase == "choice" and player_id not in state.choices

    def _send_message(
        self,
        state: SplitOrStealState,
        player_id: str,
        input_value: dict[str, object],
        context: ActionContext,
    ) -> ActionResult:
        message = Message(
            sender_id=player_id,
            recipient_id=None,
            text=str(input_value["text"]),
            turn=context.turn,
        )
        state.messages.append(message)
        events = [Event("message_sent", f"{player_id} sent a message", {"player_id": player_id})]
        if len(state.messages) >= state.max_messages:
            state.phase = "choice"
            events.append(Event("choice_phase_started", "Message limit reached"))
        return ActionResult(success=True, events=events, messages=[message])

    def _ready(
        self,
        state: SplitOrStealState,
        player_id: str,
        input_value: dict[str, object],
        context: ActionContext,
    ) -> ActionResult:
        state.ready_players.add(player_id)
        events = [Event("player_ready", f"{player_id} is ready", {"player_id": player_id})]
        if state.ready_players == {player.id for player in state.players}:
            state.phase = "choice"
            events.append(Event("choice_phase_started", "All players are ready"))
        return ActionResult(success=True, events=events)

    def _end_turn(
        self,
        state: SplitOrStealState,
        player_id: str,
        input_value: dict[str, object],
        context: ActionContext,
    ) -> ActionResult:
        return ActionResult(
            success=True,
            events=[Event("turn_ended", f"{player_id} ended their turn", {"player_id": player_id})],
        )

    def _choose_split(
        self,
        state: SplitOrStealState,
        player_id: str,
        input_value: dict[str, object],
        context: ActionContext,
    ) -> ActionResult:
        return self._choose(state, player_id, "split")

    def _choose_steal(
        self,
        state: SplitOrStealState,
        player_id: str,
        input_value: dict[str, object],
        context: ActionContext,
    ) -> ActionResult:
        return self._choose(state, player_id, "steal")

    def _choose(self, state: SplitOrStealState, player_id: str, choice: Choice) -> ActionResult:
        state.choices[player_id] = choice
        events = [Event("choice_submitted", f"{player_id} submitted a choice", {"player_id": player_id})]
        if len(state.choices) == len(state.players):
            self._resolve(state)
            events.append(Event("game_resolved", "Both choices submitted", {"scores": dict(state.scores)}))
        return ActionResult(success=True, events=events)

    def _resolve(self, state: SplitOrStealState) -> None:
        first, second = [player.id for player in state.players]
        first_choice = state.choices[first]
        second_choice = state.choices[second]

        if first_choice == "split" and second_choice == "split":
            state.scores[first] = 50
            state.scores[second] = 50
        elif first_choice == "steal" and second_choice == "split":
            state.scores[first] = 100
            state.scores[second] = 0
        elif first_choice == "split" and second_choice == "steal":
            state.scores[first] = 0
            state.scores[second] = 100
        else:
            state.scores[first] = 0
            state.scores[second] = 0

        state.phase = "end"
