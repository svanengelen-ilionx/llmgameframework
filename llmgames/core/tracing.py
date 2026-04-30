from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class TraceEvent:
    seq: int
    type: str
    payload: dict[str, object]
    visibility: str = "public"
    timestamp: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "seq": self.seq,
            "type": self.type,
            "payload": to_jsonable(self.payload),
            "visibility": self.visibility,
            "timestamp": self.timestamp,
        }


class Recorder(Protocol):
    def record(self, event: TraceEvent) -> None:
        ...


class InMemoryRecorder:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def record(self, event: TraceEvent) -> None:
        self.events.append(event)


class JsonlRecorder:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: TraceEvent) -> None:
        with self.path.open("a", encoding="utf-8") as trace_file:
            trace_file.write(json.dumps(event.to_payload(), sort_keys=True) + "\n")


class CompositeRecorder:
    def __init__(self, recorders: Sequence[Recorder]) -> None:
        self.recorders = list(recorders)

    def record(self, event: TraceEvent) -> None:
        for recorder in self.recorders:
            recorder.record(event)


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def read_jsonl_trace(path: str | Path) -> list[dict[str, object]]:
    trace_path = Path(path)
    if not trace_path.exists():
        return []
    return [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line]


def to_jsonable(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [to_jsonable(item) for item in value]
    if isinstance(value, set | frozenset):
        return sorted(to_jsonable(item) for item in value)
    if hasattr(value, "to_payload"):
        return to_jsonable(value.to_payload())  # type: ignore[attr-defined]
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_jsonable(getattr(value, field.name)) for field in fields(value)}
    return str(value)
