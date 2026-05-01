from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

RequestMode: TypeAlias = Literal["single", "barrier", "timer"]
RequestStatus: TypeAlias = Literal["pending", "resolved", "cancelled", "expired"]
SubmissionSource: TypeAlias = Literal[
    "human", "llm", "scripted", "timer", "system", "moderator", "replay"
]
SubmissionStatus: TypeAlias = Literal["received", "accepted", "rejected"]
IssueSeverity: TypeAlias = Literal["error", "warning"]
AudienceKind: TypeAlias = Literal["public", "player", "llm", "moderator", "debug"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Player(ContractModel):
    id: str
    name: str


class GameConfig(ContractModel):
    players: list[Player]
    settings: dict[str, Any] = Field(default_factory=dict)


class Audience(ContractModel):
    kind: AudienceKind
    player_id: str | None = None

    @classmethod
    def public(cls) -> "Audience":
        return cls(kind="public")

    @classmethod
    def player(cls, player_id: str) -> "Audience":
        return cls(kind="player", player_id=player_id)

    @classmethod
    def llm(cls, player_id: str) -> "Audience":
        return cls(kind="llm", player_id=player_id)

    @classmethod
    def moderator(cls) -> "Audience":
        return cls(kind="moderator")

    @classmethod
    def debug(cls) -> "Audience":
        return cls(kind="debug")


class RulesContext(ContractModel):
    config: GameConfig
    current_event_seq: int = 0
    current_time: datetime | None = None


class LegalOption(ContractModel):
    value: Any
    label: str | None = None
    payload: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def card_option(
    value: Any,
    *,
    label: str | None = None,
    payload: dict[str, Any] | None = None,
    slot: int | None = None,
    card_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> LegalOption:
    option_metadata = {**(metadata or {}), "primitive": "card"}
    if slot is not None:
        option_metadata["slot"] = slot
    if card_id is not None:
        option_metadata["card_id"] = card_id
    return LegalOption(value=value, label=label, payload=payload, metadata=option_metadata)


def hint_option(
    value: Any,
    *,
    label: str | None = None,
    payload: dict[str, Any] | None = None,
    target_id: str | None = None,
    clue_type: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> LegalOption:
    option_metadata = {**(metadata or {}), "primitive": "hint"}
    if target_id is not None:
        option_metadata["target_id"] = target_id
    if clue_type is not None:
        option_metadata["clue_type"] = clue_type
    return LegalOption(value=value, label=label, payload=payload, metadata=option_metadata)


def approval_option(
    action: str,
    *,
    label: str | None = None,
    payload: dict[str, Any] | None = None,
    suggestion_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> LegalOption:
    option_metadata = {**(metadata or {}), "primitive": "approval", "action": action}
    if suggestion_id is not None:
        option_metadata["suggestion_id"] = suggestion_id
    return LegalOption(value=action, label=label, payload=payload, metadata=option_metadata)


class LegalOptions(ContractModel):
    kind: str
    options: list[LegalOption] = Field(default_factory=list)
    examples: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RequestSpec(ContractModel):
    key: str
    kind: str
    actor_id: str | None = None
    mode: RequestMode = "single"
    input_schema: dict[str, Any]
    legal_options: LegalOptions | None = None
    deadline_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InteractionRequest(ContractModel):
    id: str
    session_id: str
    spec_key: str
    kind: str
    actor_id: str | None = None
    mode: RequestMode
    input_schema: dict[str, Any]
    legal_options: LegalOptions | None = None
    deadline_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: RequestStatus
    correlation_id: str
    created_event_seq: int
    resolved_event_seq: int | None = None


class Submission(ContractModel):
    id: str
    request_id: str
    actor_id: str | None
    source: SubmissionSource
    payload: dict[str, Any]
    idempotency_key: str
    correlation_id: str
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: SubmissionStatus = "received"


class ValidationIssue(ContractModel):
    code: str
    message: str
    path: list[str | int] = Field(default_factory=list)
    hint: str | None = None
    severity: IssueSeverity = "error"


class Message(ContractModel):
    kind: str = "info"
    text: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GameResult(ContractModel):
    status: Literal["ongoing", "win", "draw", "cancelled"]
    winner_ids: list[str] = Field(default_factory=list)
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StateProjection(ContractModel):
    phase: str | None = None
    visible_state: dict[str, Any]
    visible_messages: list[Message] = Field(default_factory=list)
    result: GameResult | None = None


class Projection(ContractModel):
    session_id: str
    audience: Audience
    status: str
    phase: str | None = None
    visible_state: dict[str, Any]
    visible_requests: list[InteractionRequest]
    visible_messages: list[Message] = Field(default_factory=list)
    event_cursor: int
    result: GameResult | None = None


class GameEventSpec(ContractModel):
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    visibility: Literal["public", "player", "debug"] = "public"


class TransitionResult(ContractModel):
    new_state: BaseModel
    events: list[GameEventSpec] = Field(default_factory=list)
    resolved_request_keys: list[str] = Field(default_factory=list)
    rejected_submissions: list[ValidationIssue] = Field(default_factory=list)
