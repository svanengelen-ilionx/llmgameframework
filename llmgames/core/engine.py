from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from random import Random
from typing import Any

from llmgames.core.contracts import (
    ActionContext,
    ActionResult,
    Event,
    GameModule,
    GameResult,
    Player,
    PlayerController,
)
from llmgames.core.events import EventLogger
from llmgames.core.tracing import CompositeRecorder, InMemoryRecorder, Recorder, TraceEvent, utc_timestamp
from llmgames.core.validation import ValidationError, validate_input
from llmgames.core.views import ViewRequest


class EngineError(RuntimeError):
    pass


class InvalidIntentError(EngineError):
    pass


class LimitExceededError(EngineError):
    pass


@dataclass(frozen=True)
class RunConfig:
    players: list[Player]
    controllers: Mapping[str, PlayerController]
    seed: int | None = None
    max_turns: int = 100
    max_actions: int = 500
    on_event: Callable[[Event], None] | None = None
    recorder: Recorder | None = None
    trace_views: tuple[ViewRequest, ...] = (ViewRequest("public"),)
    trace_intents: bool = True


@dataclass(frozen=True)
class RunSummary:
    result: GameResult
    state: Any
    events: list[Event]
    trace_events: list[TraceEvent]


class Engine:
    def __init__(self, game: GameModule, config: RunConfig) -> None:
        self.game = game
        self.config = config
        self.event_logger = EventLogger()
        self.state: Any | None = None
        self.turn = 0
        self.action_count = 0
        self.rng = Random(config.seed)
        self.trace_seq = 0
        self.trace_recorder = InMemoryRecorder()
        self.recorder: Recorder = (
            CompositeRecorder([self.trace_recorder, config.recorder]) if config.recorder else self.trace_recorder
        )

    def run(self) -> RunSummary:
        try:
            self._validate_config()
            info = self.game.get_info()
            self._trace(
                "run_started",
                {
                    "game": info.name,
                    "players": [{"id": player.id, "name": player.name} for player in self.config.players],
                    "seed": self.config.seed,
                },
            )
            self.state = self.game.create_initial_state(self.config.players, self.config.seed)
            self._trace_views()

            while not self.game.is_terminal(self.state):
                if self.turn >= self.config.max_turns:
                    raise LimitExceededError(f"Maximum turns exceeded: {self.config.max_turns}")

                turn_order = list(self.game.get_turn_order(self.state))
                self._trace("turn_started", {"turn": self.turn, "turn_order": turn_order})
                for player_id in turn_order:
                    if self.game.is_terminal(self.state):
                        break
                    player = self._get_player(player_id)
                    self._run_player_turn(player)

                self.turn += 1

            result = self.game.get_result(self.state)
            self._trace("run_finished", {"result": result})
            return RunSummary(
                result=result,
                state=self.state,
                events=list(self.event_logger.events),
                trace_events=list(self.trace_recorder.events),
            )
        except Exception as error:
            self._trace("run_failed", {"error_type": type(error).__name__, "message": str(error)}, visibility="debug")
            raise

    def _run_player_turn(self, player: Player) -> None:
        if self.action_count >= self.config.max_actions:
            raise LimitExceededError(f"Maximum actions exceeded: {self.config.max_actions}")

        available_actions = self.game.get_available_actions(self.state, player.id)
        if not available_actions:
            self._trace("player_turn_skipped", {"turn": self.turn, "player_id": player.id, "reason": "no_actions"})
            return

        self._trace("player_turn_started", {"turn": self.turn, "player_id": player.id})
        self._trace(
            "available_actions_created",
            {"player_id": player.id, "actions": [action.name for action in available_actions]},
        )
        observation = self.game.get_observation(self.state, player.id)
        controller = self.config.controllers[player.id]
        intent = controller.get_intent(observation, available_actions)
        if self.config.trace_intents:
            self._trace(
                "intent_received",
                {"player_id": player.id, "action": intent.action, "input": intent.input, "message": intent.message},
                visibility="debug",
            )

        action = self.game.actions.get(intent.action)
        if action is None:
            raise InvalidIntentError(f"Unknown action '{intent.action}' from player {player.id}")
        if action not in available_actions or not action.can_use(self.state, player.id):
            raise InvalidIntentError(f"Action '{intent.action}' is not available to player {player.id}")
        try:
            validate_input(action.input_schema, intent.input)
        except ValidationError as error:
            raise InvalidIntentError(f"Invalid input for action '{intent.action}': {error}") from error

        context = ActionContext(
            turn=self.turn,
            players=self.config.players,
            event_log=self.event_logger.events,
            rng=self.rng,
        )
        result = action.handler(self.state, player.id, intent.input, context)
        self._apply_result(result, player.id, action.name)
        self.action_count += 1
        self._trace(
            "action_applied",
            {"player_id": player.id, "action": action.name, "success": result.success},
        )
        self._trace_views()

    def _apply_result(self, result: ActionResult, player_id: str, action_name: str) -> None:
        if not result.success:
            detail = result.error or "action handler returned failure"
            raise InvalidIntentError(f"Action '{action_name}' failed for player {player_id}: {detail}")

        if result.state_patch:
            self._apply_state_patch(result.state_patch)
        self.event_logger.extend(result.events)
        if self.config.on_event:
            for event in result.events:
                self.config.on_event(event)
        for event in result.events:
            self._trace("domain_event", {"event": event})

    def _apply_state_patch(self, patch: dict[str, object]) -> None:
        if isinstance(self.state, dict):
            self.state.update(patch)
            return
        for key, value in patch.items():
            if not hasattr(self.state, key):
                raise EngineError(f"State has no field '{key}'")
            setattr(self.state, key, value)

    def _validate_config(self) -> None:
        info = self.game.get_info()
        player_count = len(self.config.players)
        if player_count < info.min_players or player_count > info.max_players:
            raise EngineError(
                f"{info.name} needs {info.min_players}-{info.max_players} players; got {player_count}"
            )
        player_ids = {player.id for player in self.config.players}
        missing = player_ids.difference(self.config.controllers)
        if missing:
            raise EngineError(f"Missing controllers for players: {', '.join(sorted(missing))}")

    def _get_player(self, player_id: str) -> Player:
        for player in self.config.players:
            if player.id == player_id:
                return player
        raise EngineError(f"Turn order included unknown player: {player_id}")

    def _trace(self, event_type: str, payload: dict[str, object], visibility: str = "public") -> None:
        self.trace_seq += 1
        self.recorder.record(
            TraceEvent(
                seq=self.trace_seq,
                type=event_type,
                payload=payload,
                visibility=visibility,
                timestamp=utc_timestamp(),
            )
        )

    def _trace_views(self) -> None:
        if self.state is None:
            return
        for request in self.config.trace_views:
            view = self.game.get_view(self.state, request)
            self._trace(
                "view_emitted",
                {"request": request, "view": view},
                visibility=view.visibility,
            )
