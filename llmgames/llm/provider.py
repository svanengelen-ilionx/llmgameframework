from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Protocol


class LLMProvider(Protocol):
    def complete(self, prompt: str) -> str:
        ...


@dataclass(frozen=True)
class LLMProviderEvent:
    type: str
    provider: str
    player_id: str | None = None
    model: str | None = None
    elapsed_seconds: float | None = None
    error_type: str | None = None
    message: str | None = None


LLMProviderEventHandler = Callable[[LLMProviderEvent], None]


class ProgressLLMProvider:
    def __init__(
        self,
        provider: LLMProvider,
        on_event: LLMProviderEventHandler,
        *,
        provider_name: str | None = None,
        player_id: str | None = None,
        model: str | None = None,
    ) -> None:
        self.provider = provider
        self.on_event = on_event
        self.provider_name = provider_name or type(provider).__name__
        self.player_id = player_id
        self.model = model or _provider_model(provider)

    def complete(self, prompt: str) -> str:
        start = monotonic()
        self._emit("model_request_started")
        try:
            response = self.provider.complete(prompt)
        except Exception as error:
            self._emit(
                "model_request_failed",
                elapsed_seconds=monotonic() - start,
                error_type=type(error).__name__,
                message=str(error),
            )
            raise
        self._emit("model_response_received", elapsed_seconds=monotonic() - start)
        return response

    def _emit(
        self,
        event_type: str,
        *,
        elapsed_seconds: float | None = None,
        error_type: str | None = None,
        message: str | None = None,
    ) -> None:
        self.on_event(
            LLMProviderEvent(
                type=event_type,
                provider=self.provider_name,
                player_id=self.player_id,
                model=self.model,
                elapsed_seconds=elapsed_seconds,
                error_type=error_type,
                message=message,
            )
        )


def _provider_model(provider: LLMProvider) -> str | None:
    config = getattr(provider, "config", None)
    model = getattr(config, "model", None)
    return model if isinstance(model, str) else None
