import unittest
from urllib.error import URLError
from unittest.mock import patch

from llmgames.llm import (
    LLMProviderEvent,
    OpenRouterConfig,
    OpenRouterProvider,
    OpenRouterTimeoutError,
    ProgressLLMProvider,
)


class TimeoutResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        raise TimeoutError("read timed out")


class StaticProvider:
    config = type("Config", (), {"model": "static-model"})()

    def __init__(self, response: str = "ok", error: Exception | None = None) -> None:
        self.response = response
        self.error = error

    def complete(self, prompt: str) -> str:
        if self.error:
            raise self.error
        return self.response


class LLMProviderTests(unittest.TestCase):
    def test_openrouter_read_timeout_is_structured(self) -> None:
        provider = OpenRouterProvider(
            OpenRouterConfig(model="slow-model", api_key="key", timeout_seconds=1.5)
        )

        with patch("llmgames.llm.openrouter.urlopen", return_value=TimeoutResponse()):
            with self.assertRaises(OpenRouterTimeoutError) as raised:
                provider.complete("prompt")

        self.assertEqual(raised.exception.provider, "openrouter")
        self.assertEqual(raised.exception.model, "slow-model")
        self.assertEqual(raised.exception.timeout_seconds, 1.5)
        self.assertIn("slow-model", str(raised.exception))

    def test_openrouter_url_error_timeout_is_structured(self) -> None:
        provider = OpenRouterProvider(
            OpenRouterConfig(model="slow-model", api_key="key", timeout_seconds=2)
        )

        with patch("llmgames.llm.openrouter.urlopen", side_effect=URLError(TimeoutError("timed out"))):
            with self.assertRaises(OpenRouterTimeoutError):
                provider.complete("prompt")

    def test_progress_provider_emits_success_events(self) -> None:
        events: list[LLMProviderEvent] = []
        provider = ProgressLLMProvider(
            StaticProvider("done"),
            events.append,
            provider_name="fake",
            player_id="alpha",
        )

        response = provider.complete("prompt")

        self.assertEqual(response, "done")
        self.assertEqual([event.type for event in events], ["model_request_started", "model_response_received"])
        self.assertEqual(events[0].provider, "fake")
        self.assertEqual(events[0].player_id, "alpha")
        self.assertEqual(events[0].model, "static-model")
        self.assertIsNotNone(events[1].elapsed_seconds)

    def test_progress_provider_emits_failure_event(self) -> None:
        events: list[LLMProviderEvent] = []
        provider = ProgressLLMProvider(
            StaticProvider(error=RuntimeError("boom")),
            events.append,
            provider_name="fake",
        )

        with self.assertRaisesRegex(RuntimeError, "boom"):
            provider.complete("prompt")

        self.assertEqual([event.type for event in events], ["model_request_started", "model_request_failed"])
        self.assertEqual(events[1].error_type, "RuntimeError")
        self.assertEqual(events[1].message, "boom")
        self.assertIsNotNone(events[1].elapsed_seconds)


if __name__ == "__main__":
    unittest.main()
