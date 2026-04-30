from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from llmgames.core.contracts import ActionDefinition, Observation, PlayerIntent
from llmgames.llm.parsing import LLMResponseError, parse_player_intent
from llmgames.llm.prompts import build_player_prompt
from llmgames.llm.provider import LLMProvider


class LLMControllerError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMControllerConfig:
    max_retries: int = 2
    fallback_action_order: tuple[str, ...] = ("ready", "end_turn")


class LLMController:
    def __init__(self, provider: LLMProvider, config: LLMControllerConfig | None = None) -> None:
        self.provider = provider
        self.config = config or LLMControllerConfig()

    def get_intent(
        self,
        observation: Observation,
        available_actions: Sequence[ActionDefinition],
    ) -> PlayerIntent:
        previous_error: str | None = None
        for _attempt in range(self.config.max_retries + 1):
            prompt = build_player_prompt(observation, available_actions, previous_error)
            raw_response = self.provider.complete(prompt)
            try:
                return parse_player_intent(raw_response, available_actions)
            except LLMResponseError as error:
                previous_error = str(error)

        fallback = self._fallback_intent(available_actions)
        if fallback is not None:
            return fallback
        raise LLMControllerError(previous_error or "LLM did not produce a valid player intent")

    def _fallback_intent(self, available_actions: Sequence[ActionDefinition]) -> PlayerIntent | None:
        by_name = {action.name: action for action in available_actions}
        for action_name in self.config.fallback_action_order:
            action = by_name.get(action_name)
            if action and _allows_empty_input(action):
                return PlayerIntent(action=action.name, input={})
        for action in available_actions:
            if _allows_empty_input(action):
                return PlayerIntent(action=action.name, input={})
        return None


def _allows_empty_input(action: ActionDefinition) -> bool:
    return not action.input_schema.get("required")
