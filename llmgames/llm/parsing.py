from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from llmgames.core.contracts import ActionDefinition, PlayerIntent
from llmgames.core.validation import ValidationError, validate_input


class LLMResponseError(ValueError):
    pass


def parse_player_intent(raw_response: str, available_actions: Sequence[ActionDefinition]) -> PlayerIntent:
    payload = _load_json_object(raw_response)

    action_name = payload.get("action")
    if not isinstance(action_name, str) or not action_name:
        raise LLMResponseError("Response field 'action' must be a non-empty string")

    actions_by_name = {action.name: action for action in available_actions}
    action = actions_by_name.get(action_name)
    if action is None:
        allowed = ", ".join(sorted(actions_by_name)) or "none"
        raise LLMResponseError(f"Unknown or unavailable action '{action_name}'. Allowed actions: {allowed}")

    input_value = payload.get("input", {})
    if not isinstance(input_value, dict):
        raise LLMResponseError("Response field 'input' must be an object")
    try:
        validate_input(action.input_schema, input_value)
    except ValidationError as error:
        raise LLMResponseError(str(error)) from error

    message = payload.get("message")
    if message is not None and not isinstance(message, str):
        raise LLMResponseError("Response field 'message' must be a string when present")

    rationale = payload.get("rationale")
    if rationale is not None and not isinstance(rationale, str):
        raise LLMResponseError("Response field 'rationale' must be a string when present")

    return PlayerIntent(action=action_name, input=input_value, message=message, rationale=rationale)


def _load_json_object(raw_response: str) -> Mapping[str, Any]:
    text = raw_response.strip()
    if text.startswith("```"):
        text = _strip_code_fence(text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise LLMResponseError(f"Response is not valid JSON: {error.msg}") from error
    if not isinstance(payload, dict):
        raise LLMResponseError("Response must be a JSON object")
    return payload


def _strip_code_fence(text: str) -> str:
    lines = text.splitlines()
    if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text
