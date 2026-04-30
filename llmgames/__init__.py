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
from llmgames.core.messaging import group_message, private_message, public_message, visible_messages
from llmgames.core.schemas import empty_schema, target_schema
from llmgames.core.tracing import InMemoryRecorder, JsonlRecorder, TraceEvent, read_jsonl_trace
from llmgames.core.views import GameView, ViewRequest

__all__ = [
	"ActionContext",
	"ActionResult",
	"BaseGameModule",
	"Engine",
	"Event",
	"GameInfo",
	"GameResult",
	"GameView",
	"InMemoryRecorder",
	"JsonlRecorder",
	"Message",
	"Observation",
	"Player",
	"RunConfig",
	"TraceEvent",
	"ViewRequest",
	"action",
	"empty_schema",
	"group_message",
	"private_message",
	"public_message",
	"target_schema",
	"visible_messages",
	"read_jsonl_trace",
]
