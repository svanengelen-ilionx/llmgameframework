from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from llmgames.models import Audience, GameConfig, Projection, Submission
from llmgames.rules import RulesKernel
from llmgames.runtime import GameSession


class ScriptedSubmission(BaseModel):
    payload: dict[str, Any]
    actor_id: str | None = None
    idempotency_key: str
    request_spec_key: str | None = None
    source: str = "scripted"


class ComparableTrace(BaseModel):
    requests: list[dict[str, Any]] = Field(default_factory=list)
    accepted_submissions: list[dict[str, Any]] = Field(default_factory=list)
    final_state: dict[str, Any]
    final_projections: dict[str, dict[str, Any]] = Field(default_factory=dict)
    event_cursor: int


class SessionSummary(BaseModel):
    config: GameConfig
    seed: int
    accepted_submissions: list[Submission]
    comparable_trace: ComparableTrace


class ReplayResult(BaseModel):
    matched: bool
    comparable_trace: ComparableTrace
    expected_trace: ComparableTrace | None = None
    first_difference: str | None = None


async def run_scripted_session(
    kernel: RulesKernel,
    config: GameConfig,
    script: list[ScriptedSubmission | dict[str, Any]],
    *,
    seed: int = 0,
) -> SessionSummary:
    session = GameSession(kernel, config, seed=seed)
    await session.start()

    for item in script:
        scripted = _coerce_scripted_submission(item)
        request = _select_request(session, scripted)
        result = await session.submit(
            request.id,
            scripted.payload,
            actor_id=scripted.actor_id,
            idempotency_key=scripted.idempotency_key,
            source=scripted.source,
        )
        if not result.accepted:
            issue_text = "; ".join(issue.message for issue in result.issues)
            raise ValueError(f"Scripted submission was rejected: {issue_text}")

    return SessionSummary(
        config=config,
        seed=seed,
        accepted_submissions=[
            submission for submission in session.submissions if submission.status == "accepted"
        ],
        comparable_trace=await comparable_trace(session),
    )


async def replay_session(
    kernel: RulesKernel,
    config: GameConfig,
    seed: int,
    submissions: list[Submission],
    *,
    expected_trace: ComparableTrace | None = None,
) -> ReplayResult:
    session = GameSession(kernel, config, seed=seed)
    await session.start()

    for submission in submissions:
        request = _select_request_for_submission(session, submission)
        result = await session.submit(
            request.id,
            submission.payload,
            actor_id=submission.actor_id,
            idempotency_key=submission.idempotency_key,
            source="replay",
        )
        if not result.accepted:
            issue_text = "; ".join(issue.message for issue in result.issues)
            raise ValueError(f"Replay submission was rejected: {issue_text}")

    trace = await comparable_trace(session)
    first_difference = None
    if expected_trace is not None:
        first_difference = _first_difference(expected_trace, trace)
    return ReplayResult(
        matched=first_difference is None,
        comparable_trace=trace,
        expected_trace=expected_trace,
        first_difference=first_difference,
    )


async def comparable_trace(session: GameSession) -> ComparableTrace:
    projections = await _final_projections(session)
    return ComparableTrace(
        requests=[
            {
                "id": request.id,
                "spec_key": request.spec_key,
                "kind": request.kind,
                "actor_id": request.actor_id,
                "mode": request.mode,
                "status": request.status,
                "created_event_seq": request.created_event_seq,
                "resolved_event_seq": request.resolved_event_seq,
            }
            for request in session.requests
        ],
        accepted_submissions=[
            {
                "id": submission.id,
                "request_id": submission.request_id,
                "actor_id": submission.actor_id,
                "payload": submission.payload,
                "idempotency_key": submission.idempotency_key,
                "status": submission.status,
            }
            for submission in session.submissions
            if submission.status == "accepted"
        ],
        final_state=session.state.model_dump(mode="json") if session.state is not None else {},
        final_projections=projections,
        event_cursor=session.event_seq,
    )


def _coerce_scripted_submission(item: ScriptedSubmission | dict[str, Any]) -> ScriptedSubmission:
    if isinstance(item, ScriptedSubmission):
        return item
    return ScriptedSubmission.model_validate(item)


def _select_request(session: GameSession, scripted: ScriptedSubmission):
    pending = [request for request in session.requests if request.status == "pending"]
    if scripted.request_spec_key is not None:
        matches = [request for request in pending if request.spec_key == scripted.request_spec_key]
    elif scripted.actor_id is not None:
        matches = [
            request for request in pending if request.actor_id in {None, scripted.actor_id}
        ]
    else:
        matches = pending
    if len(matches) != 1:
        raise ValueError(
            f"Scripted submission matched {len(matches)} pending requests; provide request_spec_key."
        )
    return matches[0]


def _select_request_for_submission(session: GameSession, submission: Submission):
    pending = [request for request in session.requests if request.status == "pending"]
    matches = [
        request for request in pending if request.actor_id in {None, submission.actor_id}
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Replay submission matched {len(matches)} pending requests for actor_id={submission.actor_id!r}."
        )
    return matches[0]


async def _final_projections(session: GameSession) -> dict[str, dict[str, Any]]:
    audiences = [Audience.public(), *(Audience.player(player.id) for player in session.config.players)]
    projections: dict[str, dict[str, Any]] = {}
    for audience in audiences:
        projection = await session.projection(audience)
        projections[_audience_key(projection)] = _projection_dump(projection)
    return projections


def _audience_key(projection: Projection) -> str:
    audience = projection.audience
    if audience.player_id is None:
        return audience.kind
    return f"{audience.kind}:{audience.player_id}"


def _projection_dump(projection: Projection) -> dict[str, Any]:
    data = projection.model_dump(mode="json")
    for request in data["visible_requests"]:
        request.pop("correlation_id", None)
    return data


def _first_difference(expected: ComparableTrace, actual: ComparableTrace) -> str | None:
    expected_data = expected.model_dump(mode="json")
    actual_data = actual.model_dump(mode="json")
    for key in expected_data:
        if expected_data[key] != actual_data.get(key):
            return key
    extra_keys = set(actual_data) - set(expected_data)
    if extra_keys:
        return sorted(extra_keys)[0]
    return None
