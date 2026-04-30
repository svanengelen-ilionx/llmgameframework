from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from random import Random
from typing import Any, Protocol

from llmgames.core.views import GameView, ViewRequest


JsonObject = dict[str, Any]
InputSchema = Mapping[str, Any]


@dataclass(frozen=True)
class Player:
    id: str
    name: str


@dataclass(frozen=True)
class GameInfo:
    name: str
    min_players: int
    max_players: int
    description: str = ""


@dataclass(frozen=True)
class Event:
    type: str
    message: str
    data: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class Message:
    sender_id: str
    text: str
    turn: int
    recipient_ids: frozenset[str] | None = None

    @property
    def recipient_id(self) -> str | None:
        if self.recipient_ids is None or len(self.recipient_ids) != 1:
            return None
        return next(iter(self.recipient_ids))


@dataclass(frozen=True)
class Observation:
    player_id: str
    rules: str
    public: JsonObject = field(default_factory=dict)
    private: JsonObject = field(default_factory=dict)
    messages: list[Message] = field(default_factory=list)


@dataclass(frozen=True)
class PlayerIntent:
    action: str
    input: JsonObject = field(default_factory=dict)
    message: str | None = None
    rationale: str | None = None


@dataclass(frozen=True)
class GameResult:
    is_terminal: bool
    scores: dict[str, int] = field(default_factory=dict)
    winners: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class ActionResult:
    success: bool
    state_patch: JsonObject | None = None
    events: list[Event] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class ActionContext:
    turn: int
    players: Sequence[Player]
    event_log: Sequence[Event]
    rng: Random


CanUse = Callable[[Any, str], bool]
ActionHandler = Callable[[Any, str, JsonObject, ActionContext], ActionResult]


@dataclass(frozen=True)
class ActionDefinition:
    name: str
    description: str
    input_schema: InputSchema
    can_use: CanUse
    handler: ActionHandler


class PlayerController(Protocol):
    def get_intent(
        self,
        observation: Observation,
        available_actions: Sequence[ActionDefinition],
    ) -> PlayerIntent:
        ...


class GameModule(Protocol):
    @property
    def actions(self) -> Mapping[str, ActionDefinition]:
        ...

    def get_info(self) -> GameInfo:
        ...

    def create_initial_state(self, players: Sequence[Player], seed: int | None = None) -> Any:
        ...

    def get_observation(self, state: Any, player_id: str) -> Observation:
        ...

    def get_available_actions(self, state: Any, player_id: str) -> list[ActionDefinition]:
        ...

    def get_turn_order(self, state: Any) -> Sequence[str]:
        ...

    def get_view(self, state: Any, request: ViewRequest) -> GameView:
        ...

    def get_result(self, state: Any) -> GameResult:
        ...

    def is_terminal(self, state: Any) -> bool:
        ...
