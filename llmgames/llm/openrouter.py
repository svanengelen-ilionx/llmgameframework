from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OpenRouterError(RuntimeError):
    pass


@dataclass(frozen=True)
class OpenRouterConfig:
    model: str
    api_key: str | None = None
    base_url: str = "https://openrouter.ai/api/v1"
    temperature: float = 0.8
    max_tokens: int = 2048
    http_referer: str | None = None
    app_title: str | None = "llmgames"
    timeout_seconds: float = 60.0


class OpenRouterProvider:
    def __init__(self, config: OpenRouterConfig) -> None:
        self.config = config

    @classmethod
    def from_env(cls, model: str | None = None) -> OpenRouterProvider:
        configured_model = model or os.environ.get("OPENROUTER_MODEL")
        if not configured_model:
            raise OpenRouterError("OPENROUTER_MODEL is required when no model is passed")
        return cls(
            OpenRouterConfig(
                model=configured_model,
                api_key=os.environ.get("OPENROUTER_API_KEY"),
                http_referer=os.environ.get("OPENROUTER_HTTP_REFERER"),
                app_title=os.environ.get("OPENROUTER_APP_TITLE", "llmgames"),
            )
        )

    def complete(self, prompt: str) -> str:
        api_key = self.config.api_key or os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise OpenRouterError("OPENROUTER_API_KEY is required")

        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Return only valid JSON for the player's next game action.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        request = Request(
            url=f"{self.config.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(api_key),
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise OpenRouterError(f"OpenRouter request failed with HTTP {error.code}: {detail}") from error
        except URLError as error:
            raise OpenRouterError(f"OpenRouter request failed: {error.reason}") from error
        except json.JSONDecodeError as error:
            raise OpenRouterError("OpenRouter returned invalid JSON") from error

        return _extract_content(response_payload)

    def _headers(self, api_key: str) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if self.config.http_referer:
            headers["HTTP-Referer"] = self.config.http_referer
        if self.config.app_title:
            headers["X-Title"] = self.config.app_title
        return headers


def _extract_content(payload: object) -> str:
    if not isinstance(payload, dict):
        raise OpenRouterError("OpenRouter response must be an object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise OpenRouterError("OpenRouter response did not include choices")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise OpenRouterError("OpenRouter choice must be an object")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise OpenRouterError("OpenRouter choice did not include a message")
    content = message.get("content")
    if not isinstance(content, str) or not content:
        raise OpenRouterError("OpenRouter message did not include text content")
    return content
