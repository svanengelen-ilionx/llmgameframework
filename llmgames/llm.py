from __future__ import annotations

from typing import Any, Protocol

import httpx

from pydantic import BaseModel, Field

from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_fixed

from llmgames.models import Audience, InteractionRequest, LegalOptions, Message, Projection, ValidationIssue


class PromptContext(BaseModel):
    session_id: str
    audience: Audience
    request_id: str
    request_spec_key: str
    request_kind: str
    actor_id: str | None
    visible_state: dict[str, Any]
    visible_messages: list[Message] = Field(default_factory=list)
    input_schema: dict[str, Any]
    legal_options: LegalOptions | None = None
    request_metadata: dict[str, Any] = Field(default_factory=dict)


class LLMSubmission(BaseModel):
    payload: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMProviderError(Exception):
    def __init__(self, issue: ValidationIssue) -> None:
        super().__init__(issue.message)
        self.issue = issue


class LLMProvider(Protocol):
    async def complete(self, context: PromptContext) -> LLMSubmission:
        ...


def build_prompt_context(projection: Projection, request: InteractionRequest) -> PromptContext:
    if request not in projection.visible_requests:
        raise ValueError("Request must be visible in the projection used to build prompt context.")
    return PromptContext(
        session_id=projection.session_id,
        audience=projection.audience,
        request_id=request.id,
        request_spec_key=request.spec_key,
        request_kind=request.kind,
        actor_id=request.actor_id,
        visible_state=projection.visible_state,
        visible_messages=projection.visible_messages,
        input_schema=request.input_schema,
        legal_options=request.legal_options,
        request_metadata=request.metadata,
    )


class HTTPJSONLLMProvider:
    def __init__(
        self,
        endpoint_url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
        retry_attempts: int = 3,
        retry_wait_seconds: float = 0.2,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.headers = headers or {}
        self.retry_attempts = retry_attempts
        self.retry_wait_seconds = retry_wait_seconds
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None

    async def complete(self, context: PromptContext) -> LLMSubmission:
        try:
            response = await self._post_with_retries(context)
        except httpx.HTTPError as exc:
            raise LLMProviderError(
                ValidationIssue(
                    code="llm_provider_error",
                    message=f"LLM provider request failed: {exc}.",
                    hint="Check provider availability, credentials, endpoint URL, and retry policy.",
                )
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMProviderError(
                ValidationIssue(
                    code="llm_response_invalid",
                    message="LLM provider response was not valid JSON.",
                    hint="Return a JSON object with a 'payload' object and optional 'metadata' object.",
                )
            ) from exc
        return _parse_llm_submission_response(data)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _post_with_retries(self, context: PromptContext) -> httpx.Response:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.retry_attempts),
            wait=wait_fixed(self.retry_wait_seconds),
            retry=retry_if_exception_type(httpx.HTTPError),
            reraise=True,
        ):
            with attempt:
                response = await self._client.post(
                    self.endpoint_url,
                    headers=self.headers,
                    json={"context": context.model_dump(mode="json")},
                )
                response.raise_for_status()
                return response
        raise RuntimeError("unreachable")


def _parse_llm_submission_response(data: Any) -> LLMSubmission:
    if not isinstance(data, dict):
        raise LLMProviderError(
            ValidationIssue(
                code="llm_response_invalid",
                message="LLM provider response must be a JSON object.",
                hint="Return {'payload': {...}, 'metadata': {...}}.",
            )
        )
    payload = data.get("payload")
    if not isinstance(payload, dict):
        raise LLMProviderError(
            ValidationIssue(
                code="llm_response_invalid",
                message="LLM provider response must include a 'payload' object.",
                path=["payload"],
                hint="Wrap the proposed game submission as {'payload': {...}}.",
            )
        )
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        raise LLMProviderError(
            ValidationIssue(
                code="llm_response_invalid",
                message="LLM provider response field 'metadata' must be an object when present.",
                path=["metadata"],
            )
        )
    return LLMSubmission(payload=payload, metadata=metadata)
