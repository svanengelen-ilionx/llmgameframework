from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ViewRequest:
    name: str = "public"
    player_id: str | None = None


@dataclass(frozen=True)
class GameView:
    name: str
    visibility: str = "public"
    data: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "visibility": self.visibility,
            "data": self.data,
        }
