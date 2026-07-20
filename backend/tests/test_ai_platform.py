"""Tests for the provider-agnostic Mundi AI platform."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.ai.models import AIMessage, AIRequest
from app.ai.provider_manager import AIService
from app.config import Settings


class AIPlatformTests(unittest.TestCase):
    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def test_provider_registry_lists_supported_provider_families(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            provider_ids = {item["provider_id"] for item in service.catalog()["providers"]}

        self.assertIn("openai", provider_ids)
        self.assertIn("anthropic", provider_ids)
        self.assertIn("gemini", provider_ids)
        self.assertIn("openrouter", provider_ids)
        self.assertIn("ollama", provider_ids)
        self.assertIn("custom-openai-compatible", provider_ids)

    def test_provider_settings_persist_and_preferred_switches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            openai = service.conversations.upsert_provider_config(
                {
                    "provider": "openai",
                    "display_name": "OpenAI",
                    "endpoint": "https://api.openai.com/v1",
                    "default_model": "gpt-test",
                    "api_key": "secret",
                    "is_preferred": True,
                }
            )
            claude = service.conversations.upsert_provider_config(
                {
                    "provider": "anthropic",
                    "display_name": "Claude",
                    "endpoint": "https://api.anthropic.com",
                    "default_model": "claude-test",
                    "api_key": "secret",
                    "is_preferred": True,
                }
            )
            reloaded = AIService(self._settings(tmpdir))
            configs = reloaded.conversations.list_provider_configs()

        self.assertTrue(openai["api_key_configured"])
        self.assertTrue(claude["api_key_configured"])
        preferred = [item for item in configs if item["is_preferred"]]
        self.assertEqual(len(preferred), 1)
        self.assertEqual(preferred[0]["provider"], "anthropic")

    def test_prompt_tool_and_skill_registration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            prompts = {item["prompt_id"] for item in service.catalog()["prompts"]}
            tools = {item["tool_id"] for item in service.catalog()["tools"]}
            skills = {item["skill_id"] for item in service.catalog()["skills"]}

        self.assertIn("extract_protocol", prompts)
        self.assertIn("mundi_help", prompts)
        self.assertIn("search_protocols", tools)
        self.assertIn("teach_mundi", skills)
        self.assertIn("scientific_assistant", skills)

    def test_teach_mundi_uses_app_help_without_ai_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            result = service.run_skill(
                actor_user_id="user:pi-owner",
                skill_id="teach_mundi",
                inputs={"question": "How do I create a subgroup?"},
            )

        self.assertEqual(result["provider"], "mundi-help-rules")
        self.assertIn("New Subgroup", result["response"])
        self.assertTrue(result["conversation_id"])

    def test_conversation_persists_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            result = service.run_skill(
                actor_user_id="user:pi-owner",
                skill_id="teach_mundi",
                inputs={"question": "How do I upload a protocol?"},
            )
            reloaded = AIService(self._settings(tmpdir))
            conversation = reloaded.conversations.get_conversation(
                "user:pi-owner",
                result["conversation_id"],
            )

        self.assertEqual(conversation["skill_id"], "teach_mundi")
        self.assertEqual([message["role"] for message in conversation["messages"]], ["user", "assistant"])
        self.assertNotIn("secret", str(conversation["messages"]).lower())

    def test_permission_enforcement_blocks_modify_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            service.permissions.assert_allowed("user:pi-owner", ["protocol.view"])
            with self.assertRaises(PermissionError):
                service.permissions.assert_allowed("user:pi-owner", ["protocol.modify"])

    def test_json_mode_validates_provider_output(self) -> None:
        class FakeService(AIService):
            def generate(self, request: AIRequest):  # type: ignore[override]
                return super().generate(request)

        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            with self.assertRaises(Exception):
                service.generate(
                    AIRequest(
                        messages=[AIMessage("user", "Return JSON")],
                        output_mode="json",
                    )
                )


if __name__ == "__main__":
    unittest.main()
