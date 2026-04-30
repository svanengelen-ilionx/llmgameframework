"""Small framework for turn-based games played by controllers."""

from llmgames.core.authoring import BaseGameModule, action
from llmgames.core.contracts import (
	ActionContext,
	ActionResult,
	Event,
	GameInfo,
	GameResult,
	Message,
	Observation,
	Player,
)
from llmgames.core.engine import Engine, RunConfig

__all__ = [
	"ActionContext",
	"ActionResult",
	"BaseGameModule",
	"Engine",
	"Event",
	"GameInfo",
	"GameResult",
	"Message",
	"Observation",
	"Player",
	"RunConfig",
	"action",
]
