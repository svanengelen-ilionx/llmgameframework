from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from llmgames.models import Audience, InteractionRequest, LegalOptions, Message, Projection


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
