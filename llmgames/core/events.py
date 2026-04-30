from __future__ import annotations

from llmgames.core.contracts import Event


class EventLogger:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def record(self, event: Event) -> None:
        self.events.append(event)

    def extend(self, events: list[Event]) -> None:
        self.events.extend(events)
