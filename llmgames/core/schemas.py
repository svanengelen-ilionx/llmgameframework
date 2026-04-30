from __future__ import annotations

from llmgames.core.contracts import InputSchema


def empty_schema() -> InputSchema:
    return {"type": "object", "properties": {}, "additionalProperties": False}


def target_schema(field_name: str = "target_id", *, description: str = "Target player id") -> InputSchema:
    return {
        "type": "object",
        "properties": {field_name: {"type": "string", "description": description}},
        "required": [field_name],
        "additionalProperties": False,
    }
