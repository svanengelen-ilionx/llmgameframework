from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate as validate_json_schema
from pydantic import BaseModel, Field

from llmgames.models import (
    Audience,
    GameConfig,
    InteractionRequest,
    Projection,
    RequestSpec,
    RulesContext,
    Submission,
    ValidationIssue,
)
from llmgames.rules import RulesKernel


class SubmitResult(BaseModel):
    accepted: bool
    submission: Submission
    issues: list[ValidationIssue] = Field(default_factory=list)


class GameSession:
    def __init__(
        self,
        kernel: RulesKernel,
        config: GameConfig,
        *,
        seed: int = 0,
        session_id: str = "session_1",
    ) -> None:
        self.kernel = kernel
        self.config = config
        self.seed = seed
        self.session_id = session_id
        self.state: BaseModel | None = None
        self.status = "created"
        self.event_seq = 0
        self._request_seq = 0
        self._submission_seq = 0
        self._requests: list[InteractionRequest] = []
        self._submissions: list[Submission] = []
        self._accepted_by_idempotency: dict[tuple[str, str], Submission] = {}

    @property
    def requests(self) -> list[InteractionRequest]:
        return list(self._requests)

    @property
    def submissions(self) -> list[Submission]:
        return list(self._submissions)

    async def start(self) -> None:
        ctx = self._ctx()
        self.state = self.kernel.initial_state(self.config, ctx)
        if not isinstance(self.state, self.kernel.state_model):
            raise TypeError("kernel.initial_state() returned an invalid state type")
        self.status = "running"
        self._refresh_requests(resolved_keys=set())

    async def projection(self, audience: Audience) -> Projection:
        self._require_started()
        state_projection = self.kernel.project_state(self.state, audience, self._ctx())
        if state_projection.result is not None:
            self.status = "complete"
        return Projection(
            session_id=self.session_id,
            audience=audience,
            status=self.status,
            phase=state_projection.phase,
            visible_state=state_projection.visible_state,
            visible_requests=self._visible_requests(audience),
            visible_messages=state_projection.visible_messages,
            event_cursor=self.event_seq,
            result=state_projection.result,
        )

    async def submit(
        self,
        request_id: str,
        payload: dict[str, Any],
        *,
        actor_id: str | None,
        idempotency_key: str,
        source: str = "human",
    ) -> SubmitResult:
        self._require_started()
        request = self._find_request(request_id)
        submission = self._new_submission(
            request_id=request_id,
            actor_id=actor_id,
            source=source,
            payload=payload,
            idempotency_key=idempotency_key,
            correlation_id=request.correlation_id if request else f"missing:{request_id}",
        )

        if request is None:
            return self._reject(submission, "unknown_request", "No request exists with that id.", ["request_id"])

        idempotency_key_tuple = (request.id, idempotency_key)
        previous = self._accepted_by_idempotency.get(idempotency_key_tuple)
        if previous is not None:
            if previous.payload == payload:
                return SubmitResult(accepted=True, submission=previous, issues=[])
            return self._reject(
                submission,
                "idempotency_conflict",
                "The same idempotency_key was already used with a different payload.",
                ["idempotency_key"],
            )

        if request.status != "pending":
            return self._reject(
                submission,
                "request_not_pending",
                "Submissions are accepted only for pending requests.",
                ["request_id"],
            )

        try:
            validate_json_schema(instance=payload, schema=request.input_schema)
        except JsonSchemaValidationError as exc:
            return self._reject(
                submission,
                "schema_invalid",
                f"Submission payload does not match input_schema: {exc.message}.",
                list(exc.path),
            )

        game_issues = self.kernel.validate_submission(self.state, request, submission, self._ctx())
        error_issues = [issue for issue in game_issues if issue.severity == "error"]
        if error_issues:
            submission.status = "rejected"
            self._submissions.append(submission)
            return SubmitResult(accepted=False, submission=submission, issues=game_issues)

        submission.status = "accepted"
        self._submissions.append(submission)
        self._accepted_by_idempotency[idempotency_key_tuple] = submission
        self._resolve_after_acceptance()
        return SubmitResult(accepted=True, submission=submission, issues=game_issues)

    async def advance(self) -> None:
        self._require_started()
        self._refresh_requests(resolved_keys=set())

    def _resolve_after_acceptance(self) -> None:
        requests = [request for request in self._requests if request.status == "pending"]
        request_ids = {request.id for request in requests}
        submissions = [
            submission
            for submission in self._submissions
            if submission.status == "accepted" and submission.request_id in request_ids
        ]
        transition = self.kernel.resolve(self.state, requests, submissions, self._ctx())
        if not isinstance(transition.new_state, self.kernel.state_model):
            raise TypeError("kernel.resolve() returned an invalid state type")

        self.state = transition.new_state
        for event in transition.events:
            self.event_seq += 1

        resolved_keys = set(transition.resolved_request_keys)
        for request in self._requests:
            if request.status == "pending" and request.spec_key in resolved_keys:
                request.status = "resolved"
                request.resolved_event_seq = self.event_seq

        self._refresh_requests(resolved_keys=resolved_keys)

    def _refresh_requests(self, *, resolved_keys: set[str]) -> None:
        specs = self.kernel.current_requests(self.state, self._ctx())
        seen_keys: set[str] = set()
        for spec in specs:
            if spec.key in seen_keys:
                raise ValueError(f"Duplicate RequestSpec.key={spec.key!r}")
            seen_keys.add(spec.key)

        pending_by_key = {
            request.spec_key: request for request in self._requests if request.status == "pending"
        }
        for spec in specs:
            existing = pending_by_key.get(spec.key)
            if existing is None:
                self._requests.append(self._new_request(spec))
                continue
            if _request_conflicts(existing, spec):
                raise ValueError(f"Pending request spec conflict for key={spec.key!r}")

        current_keys = {spec.key for spec in specs}
        for request in self._requests:
            if request.status == "pending" and request.spec_key not in current_keys:
                if request.spec_key not in resolved_keys:
                    request.status = "cancelled"
                    request.resolved_event_seq = self.event_seq

    def _new_request(self, spec: RequestSpec) -> InteractionRequest:
        self._request_seq += 1
        return InteractionRequest(
            id=f"req_{self._request_seq}",
            session_id=self.session_id,
            spec_key=spec.key,
            kind=spec.kind,
            actor_id=spec.actor_id,
            mode=spec.mode,
            input_schema=spec.input_schema,
            legal_options=spec.legal_options,
            metadata=spec.metadata,
            status="pending",
            correlation_id=f"corr_{self._request_seq}",
            created_event_seq=self.event_seq,
        )

    def _new_submission(
        self,
        *,
        request_id: str,
        actor_id: str | None,
        source: str,
        payload: dict[str, Any],
        idempotency_key: str,
        correlation_id: str,
    ) -> Submission:
        self._submission_seq += 1
        return Submission(
            id=f"sub_{self._submission_seq}",
            request_id=request_id,
            actor_id=actor_id,
            source=source,
            payload=payload,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            submitted_at=datetime.now(timezone.utc),
        )

    def _visible_requests(self, audience: Audience) -> list[InteractionRequest]:
        pending = [request for request in self._requests if request.status == "pending"]
        if audience.kind in {"public", "moderator", "debug"}:
            return [request for request in pending if request.actor_id is None]
        if audience.kind in {"player", "llm"}:
            return [
                request
                for request in pending
                if request.actor_id is None or request.actor_id == audience.player_id
            ]
        return []

    def _find_request(self, request_id: str) -> InteractionRequest | None:
        return next((request for request in self._requests if request.id == request_id), None)

    def _ctx(self) -> RulesContext:
        return RulesContext(config=self.config, current_event_seq=self.event_seq)

    def _require_started(self) -> None:
        if self.state is None:
            raise RuntimeError("GameSession.start() must be called before using the session.")

    def _reject(
        self,
        submission: Submission,
        code: str,
        message: str,
        path: list[str | int],
    ) -> SubmitResult:
        submission.status = "rejected"
        self._submissions.append(submission)
        return SubmitResult(
            accepted=False,
            submission=submission,
            issues=[ValidationIssue(code=code, message=message, path=path)],
        )


def _request_conflicts(request: InteractionRequest, spec: RequestSpec) -> bool:
    return any(
        [
            request.kind != spec.kind,
            request.actor_id != spec.actor_id,
            request.mode != spec.mode,
            request.input_schema != spec.input_schema,
        ]
    )
