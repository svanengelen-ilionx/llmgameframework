from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
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
from llmgames.core.validation import ValidationError, validate_input


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


@dataclass(frozen=True)
class RunSummary:
    result: GameResult
    state: Any
    events: list[Event]


class Engine:
    def __init__(self, game: GameModule, config: RunConfig) -> None:
        self.game = game
        self.config = config
        self.event_logger = EventLogger()
        self.state: Any | None = None
        self.turn = 0
        self.action_count = 0

    def run(self) -> RunSummary:
        self._validate_config()
        self.state = self.game.create_initial_state(self.config.players, self.config.seed)

        while not self.game.is_terminal(self.state):
            if self.turn >= self.config.max_turns:
                raise LimitExceededError(f"Maximum turns exceeded: {self.config.max_turns}")

            for player in self.config.players:
                if self.game.is_terminal(self.state):
                    break
                self._run_player_turn(player)

            self.turn += 1

        return RunSummary(
            result=self.game.get_result(self.state),
            state=self.state,
            events=list(self.event_logger.events),
        )

    def _run_player_turn(self, player: Player) -> None:
        if self.action_count >= self.config.max_actions:
            raise LimitExceededError(f"Maximum actions exceeded: {self.config.max_actions}")

        available_actions = self.game.get_available_actions(self.state, player.id)
        if not available_actions:
            return

        observation = self.game.get_observation(self.state, player.id)
        controller = self.config.controllers[player.id]
        intent = controller.get_intent(observation, available_actions)

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
        )
        result = action.handler(self.state, player.id, intent.input, context)
        self._apply_result(result, player.id, action.name)
        self.action_count += 1

    def _apply_result(self, result: ActionResult, player_id: str, action_name: str) -> None:
        if not result.success:
            detail = result.error or "action handler returned failure"
            raise InvalidIntentError(f"Action '{action_name}' failed for player {player_id}: {detail}")

        if result.state_patch:
            self._apply_state_patch(result.state_patch)
        self.event_logger.extend(result.events)

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
