from __future__ import annotations

from typing import Any

from llmgames.llm import LLMProvider, LLMSubmission, PromptContext, build_prompt_context
from llmgames.models import Audience, InteractionRequest
from llmgames.runtime import GameSession, SubmitResult


class FakeLLMProvider:
    def __init__(self, responses: dict[str, dict[str, Any] | LLMSubmission]) -> None:
        self.responses = responses
        self.contexts: list[PromptContext] = []

    async def complete(self, context: PromptContext) -> LLMSubmission:
        self.contexts.append(context)
        response = self.responses.get(context.request_spec_key)
        if response is None:
            response = self.responses.get(context.actor_id or "")
        if response is None:
            response = _first_legal_payload(context)
        if isinstance(response, LLMSubmission):
            return response
        return LLMSubmission(payload=response)


class LLMResponder:
    def __init__(self, provider: LLMProvider, *, idempotency_prefix: str = "llm") -> None:
        self.provider = provider
        self.idempotency_prefix = idempotency_prefix
        self._sequence = 0

    async def submit_for_request(
        self,
        session: GameSession,
        request: InteractionRequest,
    ) -> SubmitResult:
        audience = Audience.llm(request.actor_id) if request.actor_id is not None else Audience.public()
        projection = await session.projection(audience)
        visible_request = _find_visible_request(projection.visible_requests, request.id)
        context = build_prompt_context(projection, visible_request)
        llm_submission = await self.provider.complete(context)
        self._sequence += 1
        return await session.submit(
            visible_request.id,
            llm_submission.payload,
            actor_id=visible_request.actor_id,
            idempotency_key=f"{self.idempotency_prefix}:{visible_request.spec_key}:{self._sequence}",
            source="llm",
        )


def _find_visible_request(requests: list[InteractionRequest], request_id: str) -> InteractionRequest:
    for request in requests:
        if request.id == request_id:
            return request
    raise ValueError(f"Request id={request_id!r} is not visible to the LLM audience.")


def _first_legal_payload(context: PromptContext) -> dict[str, Any]:
    if context.legal_options is None:
        raise ValueError("FakeLLMProvider needs an explicit response when legal_options are absent.")
    if context.legal_options.examples:
        return context.legal_options.examples[0]
    if context.legal_options.options:
        option = context.legal_options.options[0]
        if option.payload is not None:
            return option.payload
        if isinstance(option.value, dict):
            return option.value
        return {"value": option.value}
    raise ValueError("FakeLLMProvider could not infer a legal payload from legal_options.")