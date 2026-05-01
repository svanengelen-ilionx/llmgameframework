from typing import Any

from llmgames.models import Projection
from llmgames.replay import (
	ComparableTrace,
	ReplayResult,
	ScriptedSubmission,
	SessionSummary,
	replay_session,
	run_scripted_session,
)
from llmgames.validation import KernelIssue, validate_kernel


def assert_projection_private(
	projection: Projection,
	*,
	forbidden_values: list[Any],
	context: str = "projection privacy",
) -> None:
	scanned = {
		"visible_state": projection.visible_state,
		"visible_messages": [message.model_dump(mode="json") for message in projection.visible_messages],
	}
	leaked = [value for value in forbidden_values if _contains_value(scanned, value)]
	if leaked:
		raise AssertionError(f"{context} leaked forbidden value {leaked[0]!r}")


def _contains_value(container: Any, value: Any) -> bool:
	if container == value:
		return True
	if isinstance(container, dict):
		return any(_contains_value(item, value) for item in container.values())
	if isinstance(container, list):
		return any(_contains_value(item, value) for item in container)
	return False

__all__ = [
	"ComparableTrace",
	"KernelIssue",
	"ReplayResult",
	"ScriptedSubmission",
	"SessionSummary",
	"assert_projection_private",
	"replay_session",
	"run_scripted_session",
	"validate_kernel",
]
