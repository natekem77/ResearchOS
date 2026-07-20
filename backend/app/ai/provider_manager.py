"""Provider manager and AIService facade."""

from __future__ import annotations

import json
import re
from typing import Any

from app.ai.context_builder import ContextBuilder
from app.ai.conversation_manager import ConversationManager
from app.ai.models import AIMessage, AIRequest, AIResponse
from app.ai.permissions import AIPermissionService
from app.ai.prompt_library import PromptLibrary
from app.ai.prompts import render_system_prompt
from app.ai.provider_registry import AIProviderRegistry
from app.ai.skills import SkillRegistry
from app.ai.tool_registry import ToolRegistry
from app.ai_providers import AIProvider, AIProviderError, OpenAICompatibleProvider
from app.config import Settings, get_settings


def get_ai_provider(settings: Settings | None = None) -> AIProvider:
    """Compatibility provider lookup backed by the AI platform registry."""

    resolved = settings or get_settings()
    provider = resolved.ai_provider.lower()
    if provider in {"", "none"}:
        raise AIProviderError("No AI provider is configured.")
    registry = AIProviderRegistry()
    spec = registry.get(provider) or registry.get(provider.replace("_", "-"))
    if spec is None:
        raise AIProviderError(f"Unsupported AI provider: {resolved.ai_provider}")
    if not spec.openai_compatible and provider not in {"openai", "openai-compatible", "openai_compatible"}:
        raise AIProviderError(f"{spec.display_name} adapter is registered but not implemented yet.")
    base_url = resolved.ai_base_url or spec.default_endpoint
    if not base_url:
        raise AIProviderError("Set AI_BASE_URL or configure a provider endpoint.")
    return OpenAICompatibleProvider(
        base_url=base_url,
        model=resolved.ai_model,
        api_key=resolved.ai_api_key or None,
        provider_name=spec.provider_id,
    )


class AIService:
    """Provider-agnostic entry point for Mundi AI features."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.providers = AIProviderRegistry()
        self.prompts = PromptLibrary()
        self.skills = SkillRegistry()
        self.tools = ToolRegistry()
        self.context = ContextBuilder()
        self.permissions = AIPermissionService()
        self.conversations = ConversationManager(self.settings)

    def catalog(self) -> dict[str, Any]:
        return {
            "providers": [item.__dict__ for item in self.providers.list()],
            "prompts": [item.__dict__ for item in self.prompts.list()],
            "skills": [item.__dict__ for item in self.skills.list()],
            "tools": [item.__dict__ for item in self.tools.list()],
        }

    def generate(self, request: AIRequest) -> AIResponse:
        provider = get_ai_provider(self.settings)
        system = next((message.content for message in request.messages if message.role == "system"), "")
        user = "\n\n".join(message.content for message in request.messages if message.role == "user")
        content = provider.chat(user, context=system or None)
        if request.output_mode == "json":
            json.loads(content)
        return AIResponse(
            content=content,
            provider=getattr(provider, "provider_name", self.settings.ai_provider),
            model=request.model or self.settings.ai_model,
            output_mode=request.output_mode,
        )

    def run_skill(
        self,
        *,
        actor_user_id: str,
        skill_id: str,
        inputs: dict[str, Any],
        provider_config_id: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        skill = self.skills.get(skill_id)
        self.permissions.assert_allowed(actor_user_id, skill.required_permissions)
        prompt = self.prompts.get(skill.prompt_id)
        context = self.context.build(skill_id=skill_id, inputs=inputs)
        context_summary = self.context.summarize(context)
        message = str(inputs.get("question") or inputs.get("message") or inputs.get("instruction") or "")
        if not conversation_id:
            conversation = self.conversations.create_conversation(actor_user_id, skill_id, provider_config_id)
            conversation_id = str(conversation["conversation_id"])
        self.conversations.append_message(conversation_id, "user", message, {"skill_id": skill_id})
        if skill_id == "teach_mundi":
            response = self._teach_mundi(message)
            provider_name = "mundi-help-rules"
            model = None
        else:
            try:
                ai_response = self.generate(
                    AIRequest(
                        messages=[
                            AIMessage("system", render_system_prompt(prompt, context_summary)),
                            AIMessage("user", message),
                        ],
                        provider_config_id=provider_config_id,
                        output_mode=skill.default_output_mode,
                    )
                )
                response = ai_response.content
                provider_name = ai_response.provider
                model = ai_response.model
            except AIProviderError as exc:
                response = f"AI provider unavailable. Deterministic fallback used. Details: {exc}"
                provider_name = "deterministic-fallback"
                model = None
        self.conversations.append_message(conversation_id, "assistant", response, {"provider": provider_name, "model": model})
        return {
            "conversation_id": conversation_id,
            "skill": skill.__dict__,
            "provider": provider_name,
            "model": model,
            "response": response,
            "context_summary": context_summary,
        }

    def ask_mundi(
        self,
        *,
        actor_user_id: str,
        message: str,
        conversation_id: str | None = None,
        context_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        text = message.strip()
        if not text:
            raise ValueError("Message is required.")
        route = self.route_intent(text)
        preferred = self.conversations.preferred_provider_config(actor_user_id)
        provider_config_id = str(preferred["provider_config_id"]) if preferred else None
        if not conversation_id:
            conversation = self.conversations.create_conversation(
                actor_user_id,
                route["skill_id"],
                provider_config_id,
                context_ids,
            )
            conversation_id = str(conversation["conversation_id"])
            self.conversations.update_conversation(
                actor_user_id,
                conversation_id,
                title=_conversation_title(text),
            )
        else:
            self.conversations.update_conversation(
                actor_user_id,
                conversation_id,
                context_ids=context_ids,
            )
        user_message = self.conversations.append_message(
            conversation_id,
            "user",
            text,
            {"router": route},
        )
        if route["skill_id"] == "teach_mundi":
            response_text = self._teach_mundi(text)
            provider_name = "mundi-help-rules"
            model = None
            sources: list[dict[str, Any]] = []
            tool_calls: list[dict[str, Any]] = []
        elif route["skill_id"] == "mundi_data_assistant":
            response_text, sources, tool_calls = self._answer_with_mundi_data(
                actor_user_id,
                text,
            )
            provider_name = "mundi-data-tools"
            model = None
        else:
            response_text, provider_name, model = self._answer_science(actor_user_id, text)
            sources = []
            tool_calls = []
        assistant_message = self.conversations.append_message(
            conversation_id,
            "assistant",
            response_text,
            {
                "skill_id": route["skill_id"],
                "provider": provider_name,
                "model": model,
                "sources": sources,
                "tool_calls": tool_calls,
            },
        )
        conversation = self.conversations.get_conversation(actor_user_id, conversation_id)
        return {
            "conversation": conversation,
            "user_message": user_message,
            "assistant_message": assistant_message,
            "chosen_skill": route["skill_id"],
            "provider": provider_name,
            "model": model,
            "sources": sources,
            "tool_calls": tool_calls,
            "warnings": _assistant_warnings(route["skill_id"], bool(preferred)),
        }

    def route_intent(self, message: str) -> dict[str, str]:
        lower = message.lower()
        navigation_terms = {
            "how do i",
            "where do i",
            "button",
            "screen",
            "navigate",
            "upload a protocol",
            "create a subgroup",
            "move a protocol",
            "settings",
        }
        data_terms = {
            "my protocol",
            "my protocols",
            "which protocol",
            "which protocols",
            "my experiment",
            "my experiments",
            "mention",
            "mentions",
            "find experiments",
            "find protocols",
            "available protocols",
        }
        if any(term in lower for term in navigation_terms):
            return {"skill_id": "teach_mundi", "reason": "navigation_help"}
        if any(term in lower for term in data_terms):
            return {"skill_id": "mundi_data_assistant", "reason": "mundi_record_query"}
        return {"skill_id": "scientific_assistant", "reason": "scientific_question"}

    def _answer_science(self, actor_user_id: str, message: str) -> tuple[str, str, str | None]:
        preferred = self.conversations.preferred_provider_config(actor_user_id)
        if preferred:
            raw = self.conversations.provider_config_with_secret(
                str(preferred["provider_config_id"]),
                actor_user_id,
            )
            if raw:
                provider = OpenAICompatibleProvider(
                    base_url=str(raw.get("endpoint") or ""),
                    model=str(raw.get("default_model") or self.settings.ai_model),
                    api_key=str(raw.get("api_key_secret") or "") or None,
                    provider_name=str(raw.get("provider") or "openai-compatible"),
                )
                try:
                    answer = provider.chat(
                        message,
                        context=(
                            "Answer as Mundi's Scientific Assistant. Distinguish general scientific knowledge "
                            "from facts retrieved from Mundi. Do not invent concentrations, timings, "
                            "temperatures, or citations. State uncertainty clearly."
                        ),
                    )
                    return answer, str(raw.get("provider") or "configured-provider"), str(raw.get("default_model") or "")
                except AIProviderError as exc:
                    safe_error = _redact_ai_provider_error(str(exc))
                    if safe_error == "Invalid API key.":
                        safe_error = (
                            "OpenAI authentication failed. The saved API key is invalid or unavailable. "
                            "Update it in Settings → AI Providers."
                        )
                    return (
                        safe_error,
                        "provider-error",
                        str(raw.get("default_model") or ""),
                    )
        return (
            "Scientific Assistant needs a configured AI provider for open-ended scientific questions. "
            "I can still help with Mundi navigation and search permitted Mundi records.",
            "no-provider",
            None,
        )

    def _answer_with_mundi_data(
        self,
        actor_user_id: str,
        message: str,
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        query = _search_query_from_message(message)
        sources: list[dict[str, Any]] = []
        tool_calls: list[dict[str, Any]] = []
        try:
            from app.protocol_hub import ProtocolHubService
            protocols = ProtocolHubService(settings=self.settings).list_protocols(query=query)[:5]
        except Exception as exc:  # pragma: no cover - defensive tool boundary
            protocols = []
            tool_calls.append({"tool": "search_protocols", "status": "error", "message": str(exc)})
        else:
            tool_calls.append({"tool": "search_protocols", "status": "ok", "result_count": len(protocols)})
        for item in protocols:
            sources.append(
                {
                    "type": "protocol",
                    "id": item.get("protocol_id"),
                    "title": item.get("title") or item.get("name") or "Protocol",
                }
            )
        try:
            from app.general_experiments import GeneralExperimentService
            experiments = GeneralExperimentService(settings=self.settings).list_experiments(user_id=actor_user_id)[:20]
            filtered = [
                item for item in experiments
                if query.lower() in json.dumps(item).lower()
            ][:5]
        except Exception as exc:  # pragma: no cover - defensive tool boundary
            filtered = []
            tool_calls.append({"tool": "search_experiments", "status": "error", "message": str(exc)})
        else:
            tool_calls.append({"tool": "search_experiments", "status": "ok", "result_count": len(filtered)})
        for item in filtered:
            sources.append(
                {
                    "type": "experiment",
                    "id": item.get("experiment_id"),
                    "title": item.get("title") or "Experiment",
                }
            )
        if not sources:
            return (
                f"I searched permitted Mundi records for “{query}” and did not find matching protocols or experiments.",
                sources,
                tool_calls,
            )
        lines = [f"I searched permitted Mundi records for “{query}” and found:"]
        for source in sources:
            lines.append(f"- {source['type'].title()}: {source['title']} ({source['id']})")
        lines.append("These are Mundi source records, not external literature citations.")
        return "\n".join(lines), sources, tool_calls

    def health(self, actor_user_id: str | None = None) -> dict[str, Any]:
        configs = self.conversations.list_provider_configs(actor_user_id) if actor_user_id else self.conversations.list_provider_configs()
        preferred = self.conversations.preferred_provider_config(actor_user_id) if actor_user_id else self.conversations.preferred_provider_config()
        return {
            "configured": bool(preferred),
            "preferred_provider": preferred,
            "provider_count": len(configs),
            "available_provider_count": len(self.providers.list()),
        }

    def test_provider_connection(
        self,
        payload: dict[str, Any],
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        provider_id = str(payload.get("provider") or "")
        spec = self.providers.get(provider_id)
        if spec is None:
            raise ValueError(f"Unsupported AI provider: {provider_id}")
        saved_config = None
        if payload.get("provider_config_id"):
            saved_config = self.conversations.provider_config_with_secret(
                str(payload["provider_config_id"]),
                actor_user_id or "user:pi-owner",
            )
            if saved_config is None:
                raise ValueError("AI provider configuration not found.")
        endpoint = str(
            payload.get("endpoint")
            or (saved_config or {}).get("endpoint")
            or spec.default_endpoint
            or ""
        ).strip()
        model = str(
            payload.get("default_model")
            or (saved_config or {}).get("default_model")
            or self.settings.ai_model
            or ""
        ).strip()
        api_key = str(
            payload.get("api_key") or (saved_config or {}).get("api_key_secret") or ""
        ).strip()
        if not endpoint:
            return {
                "ok": False,
                "provider": provider_id,
                "message": "Endpoint is required.",
                "network_tested": False,
            }
        if not model:
            return {
                "ok": False,
                "provider": provider_id,
                "message": "Model is required.",
                "network_tested": False,
            }
        if spec.requires_api_key and not api_key:
            return {
                "ok": False,
                "provider": provider_id,
                "message": "API key is required for this provider.",
                "network_tested": False,
            }
        if not spec.openai_compatible and provider_id not in {"openai", "openai-compatible", "openai_compatible"}:
            return {
                "ok": False,
                "provider": provider_id,
                "message": f"{spec.display_name} connection testing is not implemented yet.",
                "network_tested": False,
            }
        provider = OpenAICompatibleProvider(
            base_url=endpoint,
            model=model,
            api_key=api_key or None,
            provider_name=provider_id,
        )
        try:
            provider.chat("Reply with exactly: ok")
        except AIProviderError as exc:
            return {
                "ok": False,
                "provider": provider_id,
                "message": _redact_ai_provider_error(str(exc)),
                "network_tested": True,
            }
        return {
            "ok": True,
            "provider": provider_id,
            "message": "Connection successful.",
            "network_tested": True,
        }

    def _teach_mundi(self, question: str) -> str:
        lower = question.lower()
        if "subgroup" in lower or "group" in lower:
            return (
                "Open Protocols, tap New Group for a root folder, or use a folder's ... menu and choose "
                "New Subgroup. Use Rename, Move Group, Move Up, Move Down, or Delete Group from the same menu."
            )
        if "upload" in lower and "protocol" in lower:
            return "Open Protocols, tap +, choose Import PDF or Document, then Choose File and Upload Protocol."
        if "move" in lower and "protocol" in lower:
            return "Open a protocol row's ... menu, choose Move to Group, then pick Root / Ungrouped or a folder."
        return "I can help with Mundi navigation, screens, buttons, and workflows. Ask about the current screen or a task."


def _conversation_title(message: str) -> str:
    title = " ".join(message.split())
    return title[:60] if title else "Ask Mundi chat"


def _search_query_from_message(message: str) -> str:
    cleaned = re.sub(r"[?.,;:]", " ", message)
    stopwords = {
        "which",
        "of",
        "my",
        "the",
        "a",
        "an",
        "used",
        "use",
        "mention",
        "mentions",
        "protocol",
        "protocols",
        "experiment",
        "experiments",
        "find",
        "available",
    }
    tokens = [token for token in cleaned.split() if token.lower() not in stopwords]
    return tokens[-1] if tokens else message.strip()


def _assistant_warnings(skill_id: str, has_provider: bool) -> list[str]:
    if skill_id == "scientific_assistant":
        warning = "Scientific answers may contain errors. Verify protocol details before use."
        if not has_provider:
            return [warning, "No AI provider is configured for open-ended scientific answers."]
        return [warning]
    if skill_id == "mundi_data_assistant":
        return ["Mundi record answers are limited to permitted records returned by tools."]
    return []


def _redact_ai_provider_error(message: str) -> str:
    redacted = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer [redacted]", message)
    redacted = re.sub(r"sk-[A-Za-z0-9._\-]+", "sk-[redacted]", redacted)
    lower = redacted.lower()
    if (
        "401" in redacted
        or "unauthorized" in lower
        or "invalid api key" in lower
        or "invalid_api_key" in lower
    ):
        return "Invalid API key."
    if "404" in redacted or ("model" in lower and "not found" in lower):
        return "Model unavailable."
    if "quota" in lower or "billing" in lower or "insufficient" in lower:
        return "Quota or billing error."
    if "timed out" in lower or "timeout" in lower:
        return "Request timed out."
    if "failed" in lower or "connection" in lower or "network" in lower:
        return "Endpoint unreachable."
    return redacted[:240]
