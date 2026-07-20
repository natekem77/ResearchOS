"""Tests for the provider-agnostic Mundi AI platform."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.ai_providers import AIProviderError
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

    def test_provider_key_survives_service_reconstruction_and_uses_secret_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            saved = service.conversations.upsert_provider_config(
                {
                    "provider": "openai",
                    "display_name": "OpenAI",
                    "endpoint": "https://api.openai.com/v1",
                    "default_model": "gpt-5-mini",
                    "api_key": "sk-durable-secret",
                    "is_preferred": True,
                },
                "user:pi-owner",
            )
            reloaded = AIService(self._settings(tmpdir))
            configs = reloaded.conversations.list_provider_configs("user:pi-owner")
            raw = reloaded.conversations.provider_config_with_secret(
                saved["provider_config_id"],
                "user:pi-owner",
            )

        self.assertEqual(len(configs), 1)
        self.assertTrue(configs[0]["api_key_configured"])
        self.assertTrue(configs[0]["has_api_key"])
        self.assertNotIn("sk-durable-secret", str(configs))
        self.assertEqual(raw["api_key_secret"], "sk-durable-secret")
        self.assertTrue(str(raw["api_key_secret_ref"]).startswith("ai-secret:"))

    def test_provider_save_is_idempotent_and_preserves_blank_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            first = service.conversations.upsert_provider_config(
                {
                    "provider": "openai",
                    "display_name": "OpenAI",
                    "endpoint": "https://api.openai.com/v1",
                    "default_model": "gpt-5-mini",
                    "api_key": "secret-one",
                }
            )
            second = service.conversations.upsert_provider_config(
                {
                    "provider": "openai",
                    "display_name": "OpenAI",
                    "endpoint": "https://api.openai.com/v1",
                    "default_model": "gpt-5-mini",
                }
            )
            configs = service.conversations.list_provider_configs()
            stored = service.conversations.provider_config_with_secret(
                first["provider_config_id"]
            )

        self.assertEqual(first["provider_config_id"], second["provider_config_id"])
        self.assertEqual(len(configs), 1)
        self.assertTrue(second["api_key_configured"])
        self.assertNotIn("secret-one", str(second))
        self.assertEqual(stored["api_key_secret"], "secret-one")

    def test_masked_placeholder_update_preserves_saved_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            first = service.conversations.upsert_provider_config(
                {
                    "provider": "openai",
                    "display_name": "OpenAI",
                    "endpoint": "https://api.openai.com/v1",
                    "default_model": "gpt-5-mini",
                    "api_key": "sk-original",
                },
                "user:pi-owner",
            )
            service.conversations.upsert_provider_config(
                {
                    "provider_config_id": first["provider_config_id"],
                    "provider": "openai",
                    "display_name": "OpenAI",
                    "endpoint": "https://api.openai.com/v1",
                    "default_model": "gpt-5-mini",
                    "api_key": "••••••••",
                },
                "user:pi-owner",
            )
            stored = service.conversations.provider_config_with_secret(
                first["provider_config_id"],
                "user:pi-owner",
            )

        self.assertEqual(stored["api_key_secret"], "sk-original")

    def test_provider_secret_replacement_and_removal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            saved = service.conversations.upsert_provider_config(
                {
                    "provider": "openai",
                    "display_name": "OpenAI",
                    "endpoint": "https://api.openai.com/v1",
                    "default_model": "gpt-5-mini",
                    "api_key": "secret-one",
                }
            )
            replaced = service.conversations.upsert_provider_config(
                {
                    "provider_config_id": saved["provider_config_id"],
                    "provider": "openai",
                    "display_name": "OpenAI",
                    "endpoint": "https://api.openai.com/v1",
                    "default_model": "gpt-5-mini",
                    "api_key": "secret-two",
                }
            )
            stored_after_replace = service.conversations.provider_config_with_secret(
                saved["provider_config_id"]
            )
            removed = service.conversations.upsert_provider_config(
                {
                    "provider_config_id": saved["provider_config_id"],
                    "provider": "openai",
                    "display_name": "OpenAI",
                    "endpoint": "https://api.openai.com/v1",
                    "default_model": "gpt-5-mini",
                    "remove_api_key": True,
                }
            )
            stored_after_remove = service.conversations.provider_config_with_secret(
                saved["provider_config_id"]
            )

        self.assertTrue(replaced["api_key_configured"])
        self.assertEqual(stored_after_replace["api_key_secret"], "secret-two")
        self.assertFalse(removed["api_key_configured"])
        self.assertIsNone(stored_after_remove["api_key_secret"])

    def test_duplicate_provider_configs_are_repaired(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            with service.conversations._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO ai_provider_configs
                        (provider_config_id, provider, display_name, endpoint, default_model, api_key_secret, is_preferred)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "ai-provider:old",
                        "openai",
                        "openai",
                        "https://api.openai.com/v1",
                        "gpt-4o-mini",
                        None,
                        0,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO ai_provider_configs
                        (provider_config_id, provider, display_name, endpoint, default_model, api_key_secret, is_preferred)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "ai-provider:new",
                        "openai",
                        "OpenAI",
                        "https://api.openai.com/v1",
                        "gpt-5-mini",
                        "secret",
                        1,
                    ),
                )
            configs = service.conversations.list_provider_configs()

        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0]["provider_config_id"], "ai-provider:new")
        self.assertTrue(configs[0]["api_key_configured"])
        self.assertTrue(configs[0]["is_preferred"])

    def test_duplicate_cleanup_selects_provider_with_valid_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            with service.conversations._connect() as connection:
                service.conversations._store_secret(connection, "ai-provider:keyed", "sk-valid")
                connection.execute(
                    """
                    INSERT INTO ai_provider_configs
                        (provider_config_id, user_id, provider, display_name, endpoint, default_model, api_key_secret, is_preferred)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "ai-provider:stale",
                        "user:pi-owner",
                        "openai",
                        "openai",
                        "https://api.openai.com/v1",
                        "gpt-4o-mini",
                        None,
                        1,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO ai_provider_configs
                        (provider_config_id, user_id, provider, display_name, endpoint, default_model, api_key_secret, is_preferred)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "ai-provider:keyed",
                        "user:pi-owner",
                        "openai",
                        "OpenAI",
                        "https://api.openai.com/v1",
                        "gpt-5-mini",
                        "ai-secret:keyed",
                        0,
                    ),
                )
            configs = service.conversations.list_provider_configs("user:pi-owner")
            raw = service.conversations.provider_config_with_secret(
                configs[0]["provider_config_id"],
                "user:pi-owner",
            )

        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0]["provider_config_id"], "ai-provider:keyed")
        self.assertTrue(configs[0]["is_preferred"])
        self.assertEqual(raw["api_key_secret"], "sk-valid")

    def test_set_default_marks_exactly_one_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            openai = service.conversations.upsert_provider_config(
                {
                    "provider": "openai",
                    "display_name": "OpenAI",
                    "endpoint": "https://api.openai.com/v1",
                    "default_model": "gpt-5-mini",
                }
            )
            ollama = service.conversations.upsert_provider_config(
                {
                    "provider": "ollama",
                    "display_name": "Ollama",
                    "endpoint": "http://localhost:11434/v1",
                    "default_model": "llama3",
                }
            )
            service.conversations.set_preferred_provider_config(
                openai["provider_config_id"]
            )
            service.conversations.set_preferred_provider_config(
                ollama["provider_config_id"]
            )
            configs = service.conversations.list_provider_configs()

        preferred = [item for item in configs if item["is_preferred"]]
        self.assertEqual(len(preferred), 1)
        self.assertEqual(preferred[0]["provider"], "ollama")

    def test_provider_connection_test_uses_stored_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            saved = service.conversations.upsert_provider_config(
                {
                    "provider": "openai",
                    "display_name": "OpenAI",
                    "endpoint": "https://api.openai.com/v1",
                    "default_model": "gpt-5-mini",
                    "api_key": "stored-secret",
                }
            )
            with patch(
                "app.ai_providers.OpenAICompatibleProvider.chat",
                autospec=True,
                return_value="ok",
            ) as chat:
                response = service.test_provider_connection(
                    {
                        "provider_config_id": saved["provider_config_id"],
                        "provider": "openai",
                        "display_name": "OpenAI",
                        "endpoint": "https://api.openai.com/v1",
                        "default_model": "gpt-5-mini",
                    },
                    "user:pi-owner",
                )
                provider_instance = chat.call_args.args[0] if chat.call_args.args else None

        self.assertTrue(response["ok"])
        self.assertEqual(response["message"], "Connection successful.")
        self.assertEqual(chat.call_count, 1)
        self.assertEqual(provider_instance.api_key, "stored-secret")

    def test_saved_provider_connection_ignores_request_field_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            saved = service.conversations.upsert_provider_config(
                {
                    "provider": "openai",
                    "display_name": "OpenAI",
                    "endpoint": "https://api.openai.com/v1",
                    "default_model": "gpt-5-mini",
                    "api_key": "persisted-secret",
                    "is_preferred": True,
                },
                "user:pi-owner",
            )
            with patch(
                "app.ai_providers.OpenAICompatibleProvider.chat",
                autospec=True,
                return_value="ok",
            ) as chat:
                response = service.test_provider_connection(
                    {
                        "provider_config_id": saved["provider_config_id"],
                        "provider": "openai",
                        "endpoint": "https://api.openai.com/v1",
                        "default_model": "gpt-5-mini",
                        "api_key": "typed-but-unsaved-secret",
                        "test_mode": "saved_provider",
                    },
                    "user:pi-owner",
                )
                provider_instance = chat.call_args.args[0] if chat.call_args.args else None

        self.assertTrue(response["ok"])
        self.assertEqual(provider_instance.api_key, "persisted-secret")

    def test_unsaved_key_connection_requires_explicit_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            with patch(
                "app.ai_providers.OpenAICompatibleProvider.chat",
                autospec=True,
                return_value="ok",
            ) as chat:
                response = service.test_provider_connection(
                    {
                        "provider": "openai",
                        "endpoint": "https://api.openai.com/v1",
                        "default_model": "gpt-5-mini",
                        "api_key": "typed-secret",
                        "test_mode": "unsaved_key",
                    },
                    "user:pi-owner",
                )
                provider_instance = chat.call_args.args[0] if chat.call_args.args else None

        self.assertTrue(response["ok"])
        self.assertEqual(provider_instance.api_key, "typed-secret")

    def test_saved_provider_test_and_ask_mundi_resolve_same_provider_and_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            saved = service.conversations.upsert_provider_config(
                {
                    "provider": "openai",
                    "display_name": "OpenAI",
                    "endpoint": "https://api.openai.com/v1",
                    "default_model": "gpt-5-mini",
                    "api_key": "shared-secret",
                    "is_preferred": True,
                },
                "user:pi-owner",
            )
            saved_resolution = service.conversations.resolve_active_provider(
                "user:pi-owner",
                saved["provider_config_id"],
                flow="test_assertion",
            )
            ask_resolution = service.conversations.resolve_active_provider(
                "user:pi-owner",
                flow="test_assertion",
            )

        self.assertEqual(saved_resolution["provider_config_id"], ask_resolution["provider_config_id"])
        self.assertEqual(saved_resolution["api_key_secret_ref"], ask_resolution["api_key_secret_ref"])
        self.assertEqual(saved_resolution["api_key_secret"], "shared-secret")

    def test_save_fails_when_existing_secret_reference_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            saved = service.conversations.upsert_provider_config(
                {
                    "provider": "openai",
                    "display_name": "OpenAI",
                    "endpoint": "https://api.openai.com/v1",
                    "default_model": "gpt-5-mini",
                    "api_key": "soon-missing",
                },
                "user:pi-owner",
            )
            raw = service.conversations.provider_config_with_secret(
                saved["provider_config_id"],
                "user:pi-owner",
            )
            with service.conversations._connect() as connection:
                connection.execute(
                    "DELETE FROM ai_provider_secrets WHERE secret_ref = ?",
                    (raw["api_key_secret_ref"],),
                )

            with self.assertRaisesRegex(ValueError, "secret could not be saved"):
                service.conversations.upsert_provider_config(
                    {
                        "provider_config_id": saved["provider_config_id"],
                        "provider": "openai",
                        "display_name": "OpenAI",
                        "endpoint": "https://api.openai.com/v1",
                        "default_model": "gpt-5-mini",
                    },
                    "user:pi-owner",
                )

    def test_provider_connection_error_redacts_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            saved = service.conversations.upsert_provider_config(
                {
                    "provider": "openai",
                    "display_name": "OpenAI",
                    "endpoint": "https://api.openai.com/v1",
                    "default_model": "gpt-5-mini",
                    "api_key": "sk-secret",
                }
            )
            with patch(
                "app.ai_providers.OpenAICompatibleProvider.chat",
                side_effect=AIProviderError("AI provider returned HTTP 401: sk-secret"),
            ):
                response = service.test_provider_connection(
                    {
                        "provider_config_id": saved["provider_config_id"],
                        "provider": "openai",
                        "display_name": "OpenAI",
                        "endpoint": "https://api.openai.com/v1",
                        "default_model": "gpt-5-mini",
                    },
                    "user:pi-owner",
                )

        self.assertFalse(response["ok"])
        self.assertEqual(response["message"], "Invalid API key.")
        self.assertNotIn("sk-secret", str(response))

    def test_ask_mundi_uses_stored_default_provider_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            saved = service.conversations.upsert_provider_config(
                {
                    "provider": "openai",
                    "display_name": "OpenAI",
                    "endpoint": "https://api.openai.com/v1",
                    "default_model": "gpt-5-mini",
                    "api_key": "sk-ask-mundi",
                    "is_preferred": True,
                },
                "user:pi-owner",
            )
            with patch(
                "app.ai_providers.OpenAICompatibleProvider.chat",
                autospec=True,
                return_value="Scientific answer",
            ) as chat:
                result = service.ask_mundi(
                    actor_user_id="user:pi-owner",
                    message="Why is BMP4 added near day 7?",
                )
                provider_instance = chat.call_args.args[0] if chat.call_args.args else None

        self.assertEqual(result["chosen_skill"], "scientific_assistant")
        self.assertEqual(result["provider"], "openai")
        self.assertEqual(provider_instance.api_key, "sk-ask-mundi")
        self.assertEqual(
            result["conversation"]["provider_config_id"],
            saved["provider_config_id"],
        )

    def test_ask_mundi_401_is_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            service.conversations.upsert_provider_config(
                {
                    "provider": "openai",
                    "display_name": "OpenAI",
                    "endpoint": "https://api.openai.com/v1",
                    "default_model": "gpt-5-mini",
                    "api_key": "sk-secret-ending-4w8A",
                    "is_preferred": True,
                },
                "user:pi-owner",
            )
            with patch(
                "app.ai_providers.OpenAICompatibleProvider.chat",
                side_effect=AIProviderError(
                    'AI provider returned HTTP 401: {"error":{"message":"Incorrect API key provided: sk-secret-ending-4w8A","type":"invalid_request_error","code":"invalid_api_key"}}'
                ),
            ):
                result = service.ask_mundi(
                    actor_user_id="user:pi-owner",
                    message="Why is BMP4 added near day 7?",
                )

        text = str(result)
        self.assertIn("OpenAI authentication failed", result["assistant_message"]["content"])
        self.assertNotIn("sk-secret-ending-4w8A", text)
        self.assertNotIn("invalid_api_key", text)

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

    def test_ask_mundi_routes_navigation_science_and_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))

            self.assertEqual(
                service.route_intent("How do I create a subgroup?")["skill_id"],
                "teach_mundi",
            )
            self.assertEqual(
                service.route_intent("Why is BMP4 added near day 7?")["skill_id"],
                "scientific_assistant",
            )
            self.assertEqual(
                service.route_intent("Which of my protocols mention BMP4?")["skill_id"],
                "mundi_data_assistant",
            )

    def test_ask_mundi_conversation_persists_without_api_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            result = service.ask_mundi(
                actor_user_id="user:pi-owner",
                message="How do I create a protocol subgroup?",
            )
            conversation_id = result["conversation"]["conversation_id"]
            reloaded = AIService(self._settings(tmpdir))
            conversation = reloaded.conversations.get_conversation(
                "user:pi-owner",
                conversation_id,
            )

        self.assertEqual(result["chosen_skill"], "teach_mundi")
        self.assertEqual([item["role"] for item in conversation["messages"]], ["user", "assistant"])
        self.assertNotIn("api_key", str(conversation).lower())
        self.assertNotIn("secret", str(conversation).lower())

    def test_navigation_preferences_validate_five_unique_destinations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AIService(self._settings(tmpdir))
            available = ["home", "experiments", "protocols", "ask_mundi", "settings", "search"]
            saved = service.conversations.save_navigation_preferences(
                "user:pi-owner",
                ["home", "experiments", "protocols", "ask_mundi", "settings"],
                available,
            )
            with self.assertRaises(ValueError):
                service.conversations.save_navigation_preferences(
                    "user:pi-owner",
                    ["home", "home", "protocols", "ask_mundi", "settings"],
                    available,
                )
            with self.assertRaises(ValueError):
                service.conversations.save_navigation_preferences(
                    "user:pi-owner",
                    ["home", "experiments", "protocols", "ask_mundi", "bad"],
                    available,
                )

        self.assertEqual(
            saved["destination_ids"],
            ["home", "experiments", "protocols", "ask_mundi", "settings"],
        )

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
