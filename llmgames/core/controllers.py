from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Sequence

from llmgames.core.contracts import ActionDefinition, Observation, PlayerIntent


class ScriptedController:
    def __init__(self, intents: Iterable[PlayerIntent]) -> None:
        self._intents = deque(intents)

    def get_intent(
        self,
        observation: Observation,
        available_actions: Sequence[ActionDefinition],
    ) -> PlayerIntent:
        if not self._intents:
            action_names = ", ".join(action.name for action in available_actions) or "none"
            raise RuntimeError(
                f"No scripted intent left for {observation.player_id}; available actions: {action_names}"
            )
        return self._intents.popleft()


def intent(action: str, **input_values: object) -> PlayerIntent:
    return PlayerIntent(action=action, input=dict(input_values))
