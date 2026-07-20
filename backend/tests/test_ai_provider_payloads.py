"""Regression tests for provider/model-specific AI request payloads."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from app.ai_providers import OpenAICompatibleProvider, build_provider_request, model_capabilities


class _FakeResponse:
    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps({"output_text": "ok"}).encode("utf-8")


class AIProviderPayloadTests(unittest.TestCase):
    def test_openai_gpt5_mini_uses_responses_without_temperature(self) -> None:
        endpoint, payload, capabilities = build_provider_request(
            provider_name="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-5-mini",
            message="Reply with exactly: ok",
        )

        self.assertEqual(endpoint, "https://api.openai.com/v1/responses")
        self.assertEqual(payload, {"model": "gpt-5-mini", "input": "Reply with exactly: ok"})
        self.assertFalse(capabilities.supports_temperature)
        self.assertNotIn("temperature", payload)
        self.assertNotIn("top_p", payload)
        self.assertNotIn("frequency_penalty", payload)
        self.assertNotIn("presence_penalty", payload)
        self.assertNotIn("max_tokens", payload)

    def test_openai_gpt5_omits_unsupported_sampling_parameters(self) -> None:
        _endpoint, payload, capabilities = build_provider_request(
            provider_name="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-5",
            message="Reply with exactly: ok",
            temperature=0.2,
            top_p=0.9,
        )

        self.assertEqual(capabilities.api_style, "openai_responses")
        self.assertNotIn("temperature", payload)
        self.assertNotIn("top_p", payload)

    def test_openai_gpt5_chat_call_sends_minimal_responses_payload(self) -> None:
        captured = {}

        def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
            captured["url"] = request.full_url
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return _FakeResponse()

        provider = OpenAICompatibleProvider(
            base_url="https://api.openai.com/v1",
            model="gpt-5-mini",
            api_key="secret",
            provider_name="openai",
        )
        with patch("app.ai_providers.urlopen", side_effect=fake_urlopen):
            result = provider.chat("Reply with exactly: ok")

        self.assertEqual(result, "ok")
        self.assertEqual(captured["url"], "https://api.openai.com/v1/responses")
        self.assertEqual(
            captured["payload"],
            {"model": "gpt-5-mini", "input": "Reply with exactly: ok"},
        )

    def test_claude_builder_omits_openai_only_parameters(self) -> None:
        endpoint, payload, capabilities = build_provider_request(
            provider_name="claude",
            base_url="https://api.anthropic.com/v1",
            model="claude-sonnet-test",
            message="ok",
        )

        self.assertEqual(endpoint, "https://api.anthropic.com/v1/messages")
        self.assertEqual(capabilities.api_style, "anthropic_messages")
        self.assertNotIn("frequency_penalty", payload)
        self.assertNotIn("presence_penalty", payload)

    def test_gemini_builder_omits_openai_only_parameters(self) -> None:
        endpoint, payload, capabilities = build_provider_request(
            provider_name="gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            model="gemini-test",
            message="ok",
        )

        self.assertEqual(
            endpoint,
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent",
        )
        self.assertEqual(capabilities.api_style, "gemini_generate")
        self.assertNotIn("frequency_penalty", payload)
        self.assertNotIn("presence_penalty", payload)
        self.assertNotIn("max_tokens", payload)

    def test_openrouter_builder_uses_chat_without_unspecified_parameters(self) -> None:
        endpoint, payload, capabilities = build_provider_request(
            provider_name="openrouter",
            base_url="https://openrouter.ai/api/v1",
            model="openai/gpt-5-mini",
            message="ok",
        )

        self.assertEqual(endpoint, "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(capabilities.api_style, "openai_chat")
        self.assertIn("temperature", payload)
        self.assertNotIn("top_p", payload)
        self.assertNotIn("frequency_penalty", payload)
        self.assertNotIn("presence_penalty", payload)

    def test_ollama_builder_uses_chat_without_unspecified_parameters(self) -> None:
        endpoint, payload, capabilities = build_provider_request(
            provider_name="ollama",
            base_url="http://localhost:11434/v1",
            model="llama3",
            message="ok",
        )

        self.assertEqual(endpoint, "http://localhost:11434/v1/chat/completions")
        self.assertEqual(capabilities.api_style, "openai_chat")
        self.assertTrue(capabilities.supports_temperature)
        self.assertNotIn("top_p", payload)
        self.assertNotIn("frequency_penalty", payload)
        self.assertNotIn("presence_penalty", payload)

    def test_capability_table_identifies_gpt5_temperature_limit(self) -> None:
        self.assertFalse(model_capabilities("openai", "gpt-5-mini").supports_temperature)
        self.assertFalse(model_capabilities("openai", "gpt-5").supports_temperature)
        self.assertTrue(model_capabilities("openai", "gpt-4o-mini").supports_temperature)


if __name__ == "__main__":
    unittest.main()
