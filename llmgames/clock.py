from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class ManualClock:
    def __init__(self, current_time: datetime | None = None) -> None:
        self.current_time = current_time or datetime(2000, 1, 1, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self.current_time

    def advance(self, delta: timedelta) -> datetime:
        self.current_time += delta
        return self.current_time