from __future__ import annotations

from pydantic import BaseModel, Field

from llmgames.llm import LLMProvider, LLMProviderError, build_prompt_context
from llmgames.models import Audience, InteractionRequest
from llmgames.runtime import GameSession, SubmitResult


class SeatCapabilities(BaseModel):
    actor_id: str
    llm_assist: bool = False
    human_approval_required: bool = True
    metadata: dict = Field(default_factory=dict)


class AssistedSuggestion(BaseModel):
    id: str
    request_id: str
    request_spec_key: str
    actor_id: str | None
    payload: dict
    metadata: dict = Field(default_factory=dict)


class AssistedSeatController:
    def __init__(self, provider: LLMProvider, *, suggestion_prefix: str = "assist") -> None:
        self.provider = provider
        self.suggestion_prefix = suggestion_prefix
        self._sequence = 0

    async def suggest_for_request(self, session: GameSession, request: InteractionRequest) -> AssistedSuggestion:
        audience = Audience.llm(request.actor_id) if request.actor_id is not None else Audience.public()
        projection = await session.projection(audience)
        visible_request = _find_visible_request(projection.visible_requests, request.id)
        context = build_prompt_context(projection, visible_request)
        event_payload = _event_payload(visible_request)
        session.record_event("assist.requested", event_payload)
        try:
            llm_submission = await self.provider.complete(context)
        except LLMProviderError as exc:
            session.record_event("assist.failed", {**event_payload, "issue": exc.issue.model_dump(mode="json")})
            raise

        self._sequence += 1
        suggestion = AssistedSuggestion(
            id=f"{self.suggestion_prefix}_{self._sequence}",
            request_id=visible_request.id,
            request_spec_key=visible_request.spec_key,
            actor_id=visible_request.actor_id,
            payload=llm_submission.payload,
            metadata=llm_submission.metadata,
        )
        session.record_event(
            "assist.suggested",
            {**event_payload, "suggestion": suggestion.model_dump(mode="json")},
        )
        return suggestion

    async def approve_suggestion(
        self,
        session: GameSession,
        suggestion: AssistedSuggestion,
        *,
        idempotency_key: str,
    ) -> SubmitResult:
        result = await session.submit(
            suggestion.request_id,
            suggestion.payload,
            actor_id=suggestion.actor_id,
            idempotency_key=idempotency_key,
            source="human",
        )
        session.record_event(
            "assist.approved",
            {"suggestion_id": suggestion.id, "submission_id": result.submission.id, "accepted": result.accepted},
        )
        return result

    async def edit_suggestion(
        self,
        session: GameSession,
        suggestion: AssistedSuggestion,
        payload: dict,
        *,
        idempotency_key: str,
    ) -> SubmitResult:
        result = await session.submit(
            suggestion.request_id,
            payload,
            actor_id=suggestion.actor_id,
            idempotency_key=idempotency_key,
            source="human",
        )
        session.record_event(
            "assist.edited",
            {"suggestion_id": suggestion.id, "submission_id": result.submission.id, "accepted": result.accepted},
        )
        return result

    def reject_suggestion(self, session: GameSession, suggestion: AssistedSuggestion, *, reason: str | None = None) -> None:
        session.record_event("assist.rejected", {"suggestion_id": suggestion.id, "reason": reason})


def _find_visible_request(requests: list[InteractionRequest], request_id: str) -> InteractionRequest:
    for request in requests:
        if request.id == request_id:
            return request
    raise ValueError(f"Request id={request_id!r} is not visible to the assisted seat audience.")


def _event_payload(request: InteractionRequest) -> dict:
    return {
        "request_id": request.id,
        "request_spec_key": request.spec_key,
        "actor_id": request.actor_id,
        "correlation_id": request.correlation_id,
    }