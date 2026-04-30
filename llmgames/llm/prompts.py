from __future__ import annotations

import json
from collections.abc import Sequence

from llmgames.core.contracts import ActionDefinition, Message, Observation


def build_player_prompt(
    observation: Observation,
    available_actions: Sequence[ActionDefinition],
    previous_error: str | None = None,
) -> str:
    payload = {
        "player_id": observation.player_id,
        "rules": observation.rules,
        "public_observation": observation.public,
        "private_observation": observation.private,
        "messages": [_message_to_dict(message) for message in observation.messages],
        "available_actions": [
            {
                "name": action.name,
                "description": action.description,
                "input_schema": action.input_schema,
            }
            for action in available_actions
        ],
        "required_response_format": {
            "action": "one available action name",
            "input": "object matching that action's input_schema",
            "message": "optional string",
            "rationale": "optional string",
        },
    }
    if previous_error:
        payload["previous_error"] = previous_error

    return (
        "You are playing a turn-based game. Choose exactly one legal action for your player. "
        "Return only valid JSON with no markdown or commentary.\n\n"
        f"{json.dumps(payload, indent=2, sort_keys=True)}"
    )


def _message_to_dict(message: Message) -> dict[str, object]:
    return {
        "sender_id": message.sender_id,
        "recipient_ids": sorted(message.recipient_ids) if message.recipient_ids is not None else None,
        "text": message.text,
        "turn": message.turn,
    }
