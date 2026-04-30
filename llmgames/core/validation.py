from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class ValidationError(ValueError):
    pass


def validate_input(schema: Mapping[str, Any], value: object) -> None:
    if schema.get("type") != "object":
        raise ValidationError("Only object input schemas are supported")
    if not isinstance(value, dict):
        raise ValidationError("Input must be an object")

    required = set(schema.get("required", []))
    missing = required.difference(value)
    if missing:
        raise ValidationError(f"Missing required input fields: {', '.join(sorted(missing))}")

    properties = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        extra = set(value).difference(properties)
        if extra:
            raise ValidationError(f"Unexpected input fields: {', '.join(sorted(extra))}")

    for key, field_schema in properties.items():
        if key not in value:
            continue
        _validate_field(key, field_schema, value[key])


def _validate_field(name: str, schema: Mapping[str, Any], value: object) -> None:
    expected_type = schema.get("type")
    if expected_type == "string" and not isinstance(value, str):
        raise ValidationError(f"Field '{name}' must be a string")
    if expected_type == "integer" and not isinstance(value, int):
        raise ValidationError(f"Field '{name}' must be an integer")
    if expected_type == "boolean" and not isinstance(value, bool):
        raise ValidationError(f"Field '{name}' must be a boolean")
    if "enum" in schema and value not in schema["enum"]:
        allowed = ", ".join(str(item) for item in schema["enum"])
        raise ValidationError(f"Field '{name}' must be one of: {allowed}")
    min_length = schema.get("minLength")
    if isinstance(value, str) and min_length is not None and len(value) < min_length:
        raise ValidationError(f"Field '{name}' is shorter than {min_length}")
    max_length = schema.get("maxLength")
    if isinstance(value, str) and max_length is not None and len(value) > max_length:
        raise ValidationError(f"Field '{name}' is longer than {max_length}")
