from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from llmgames.core.contracts import ActionDefinition, InputSchema


AlwaysAvailable = Callable[[Any, str], bool]


@dataclass(frozen=True)
class ActionSpec:
    name: str
    description: str
    input_schema: InputSchema
    can_use: str | AlwaysAvailable | None = None


def action(
    name: str | None = None,
    *,
    description: str,
    input_schema: InputSchema | None = None,
    can_use: str | AlwaysAvailable | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    schema = input_schema or {"type": "object", "properties": {}, "additionalProperties": False}

    def decorate(handler: Callable[..., Any]) -> Callable[..., Any]:
        handler._llmgames_action = ActionSpec(  # type: ignore[attr-defined]
            name=name or handler.__name__,
            description=description,
            input_schema=schema,
            can_use=can_use,
        )
        return handler

    return decorate


class BaseGameModule:
    @property
    def actions(self) -> Mapping[str, ActionDefinition]:
        if not hasattr(self, "_actions"):
            self._actions = self._build_actions()
        return self._actions

    def get_available_actions(self, state: Any, player_id: str) -> list[ActionDefinition]:
        return [action for action in self.actions.values() if action.can_use(state, player_id)]

    def get_turn_order(self, state: Any) -> Sequence[str]:
        players = getattr(state, "players", None)
        if players is None:
            return []
        return [player.id for player in players]

    def _build_actions(self) -> dict[str, ActionDefinition]:
        actions: dict[str, ActionDefinition] = {}
        for handler_name, spec in self._iter_action_specs():
            handler = getattr(self, handler_name)
            actions[spec.name] = ActionDefinition(
                name=spec.name,
                description=spec.description,
                input_schema=spec.input_schema,
                can_use=self._resolve_can_use(spec.can_use),
                handler=handler,
            )
        return actions

    def _iter_action_specs(self) -> list[tuple[str, ActionSpec]]:
        specs: list[tuple[str, ActionSpec]] = []
        for cls in reversed(type(self).mro()):
            for name, value in cls.__dict__.items():
                spec = getattr(value, "_llmgames_action", None)
                if isinstance(spec, ActionSpec):
                    specs.append((name, spec))
        return specs

    def _resolve_can_use(self, can_use: str | AlwaysAvailable | None) -> AlwaysAvailable:
        if can_use is None:
            return _always_available
        if isinstance(can_use, str):
            return getattr(self, can_use)
        return can_use


def _always_available(state: Any, player_id: str) -> bool:
    return True
