"""AI provider abstractions for ResearchOS."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import Settings, get_settings


class AIProviderError(RuntimeError):
    """Raised when AI generation is unavailable or fails."""


class AIProvider(Protocol):
    """Common interface for chat-capable AI providers."""

    provider_name: str

    def chat(self, message: str, context: str | None = None) -> str:
        """Generate a response for a user message and optional research context."""


ProviderApiStyle = Literal["openai_responses", "openai_chat", "anthropic_messages", "gemini_generate"]


@dataclass(frozen=True)
class ModelCapabilities:
    supports_temperature: bool = True
    supports_top_p: bool = False
    supports_json_mode: bool = False
    supports_vision: bool = False
    supports_streaming: bool = False
    api_style: ProviderApiStyle = "openai_chat"


def model_capabilities(provider_name: str, model: str) -> ModelCapabilities:
    """Return conservative capability metadata for request construction."""

    provider = provider_name.strip().lower().replace("_", "-")
    normalized_model = model.strip().lower()
    if provider in {"openai", "openai-compatible"} and normalized_model.startswith("gpt-5"):
        return ModelCapabilities(
            supports_temperature=False,
            supports_top_p=False,
            supports_json_mode=True,
            supports_vision=True,
            supports_streaming=True,
            api_style="openai_responses",
        )
    if provider == "anthropic" or provider == "claude":
        return ModelCapabilities(
            supports_temperature=True,
            supports_top_p=True,
            supports_json_mode=False,
            supports_vision=True,
            supports_streaming=True,
            api_style="anthropic_messages",
        )
    if provider == "gemini":
        return ModelCapabilities(
            supports_temperature=True,
            supports_top_p=True,
            supports_json_mode=True,
            supports_vision=True,
            supports_streaming=True,
            api_style="gemini_generate",
        )
    if provider == "openrouter":
        return ModelCapabilities(
            supports_temperature=True,
            supports_top_p=True,
            supports_json_mode=True,
            supports_vision=True,
            supports_streaming=True,
            api_style="openai_chat",
        )
    if provider in {"ollama", "lmstudio", "lm-studio", "vllm", "custom-openai-compatible"}:
        return ModelCapabilities(
            supports_temperature=True,
            supports_top_p=True,
            supports_json_mode=True,
            supports_vision=False,
            supports_streaming=True,
            api_style="openai_chat",
        )
    return ModelCapabilities()


def build_provider_request(
    *,
    provider_name: str,
    base_url: str,
    model: str,
    message: str,
    context: str | None = None,
    temperature: float | None = 0.2,
    top_p: float | None = None,
) -> tuple[str, dict[str, Any], ModelCapabilities]:
    """Build the smallest provider/model-valid text generation request."""

    capabilities = model_capabilities(provider_name, model)
    endpoint = base_url.rstrip("/")
    prompt = message if not context else f"{context}\n\n{message}"
    if capabilities.api_style == "openai_responses":
        if not endpoint.endswith("/responses"):
            endpoint = f"{endpoint}/responses"
        payload: dict[str, Any] = {"model": model, "input": prompt}
        return endpoint, payload, capabilities
    if capabilities.api_style == "anthropic_messages":
        if not endpoint.endswith("/messages"):
            endpoint = f"{endpoint}/messages"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 32,
        }
    elif capabilities.api_style == "gemini_generate":
        endpoint = f"{endpoint}/models/{model}:generateContent"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
    else:
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"
        system_prompt = (
            "You are ResearchOS, an AI assistant for scientific lab notes. "
            "Use provided context when available and be explicit about uncertainty."
        )
        if context:
            system_prompt = f"{system_prompt}\n\nResearch context:\n{context}"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
        }
    if temperature is not None and capabilities.supports_temperature:
        payload["temperature"] = temperature
    if top_p is not None and capabilities.supports_top_p:
        payload["top_p"] = top_p
    return endpoint, payload, capabilities


@dataclass
class OpenAICompatibleProvider:
    """Provider for OpenAI-compatible chat completion APIs.

    This works for OpenAI and local tools such as Ollama or LM Studio when they
    expose an OpenAI-compatible `/chat/completions` endpoint.
    """

    base_url: str
    model: str
    api_key: str | None = None
    provider_name: str = "openai-compatible"

    def chat(self, message: str, context: str | None = None) -> str:
        """Call an OpenAI-compatible chat completion endpoint."""

        endpoint, payload, capabilities = build_provider_request(
            provider_name=self.provider_name,
            base_url=self.base_url,
            model=self.model,
            message=message,
            context=context,
            temperature=0.2,
        )
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = Request(url=endpoint, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=75) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise AIProviderError(f"AI provider returned HTTP {exc.code}: {error_body}") from exc
        except URLError as exc:
            raise AIProviderError(f"AI provider request failed: {exc.reason}") from exc

        parsed = json.loads(raw_body)
        if capabilities.api_style == "openai_responses":
            output_text = parsed.get("output_text")
            if isinstance(output_text, str) and output_text.strip():
                return output_text
            for item in parsed.get("output", []):
                if not isinstance(item, dict):
                    continue
                for content_item in item.get("content", []):
                    if not isinstance(content_item, dict):
                        continue
                    text = content_item.get("text")
                    if isinstance(text, str) and text.strip():
                        return text
            raise AIProviderError("AI provider returned an empty response.")
        choices = parsed.get("choices", [])
        if not choices:
            raise AIProviderError("AI provider returned no choices.")

        message_payload = choices[0].get("message", {})
        content = message_payload.get("content")
        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("AI provider returned an empty response.")

        return content


class ClaudeProvider:
    """Placeholder for a future Anthropic Claude adapter."""

    provider_name = "claude"

    def chat(self, message: str, context: str | None = None) -> str:
        """Raise a clear error until the Claude adapter is implemented."""

        raise AIProviderError("Claude provider is not implemented yet.")


def get_ai_provider(settings: Settings | None = None) -> AIProvider:
    """Return the configured AI provider or raise a helpful setup error."""

    resolved_settings = settings or get_settings()
    provider = resolved_settings.ai_provider.lower()

    if provider in {"", "none"}:
        raise AIProviderError(
            "No AI provider is configured. Set AI_PROVIDER, AI_BASE_URL, AI_MODEL, "
            "and AI_API_KEY when required. /search still works without AI."
        )

    if provider in {
        "openai",
        "openai-compatible",
        "openai_compatible",
        "ollama",
        "lmstudio",
        "lm-studio",
    }:
        if not resolved_settings.ai_model:
            raise AIProviderError("Set AI_MODEL for the configured AI provider.")
        if not resolved_settings.ai_base_url:
            raise AIProviderError("Set AI_BASE_URL for the configured AI provider.")
        if provider == "openai" and not resolved_settings.ai_api_key:
            raise AIProviderError("OpenAI usage requires AI_API_KEY.")
        if resolved_settings.ai_base_url.startswith("https://") and not resolved_settings.ai_api_key:
            raise AIProviderError("Cloud OpenAI-compatible usage usually requires AI_API_KEY.")

        return OpenAICompatibleProvider(
            base_url=resolved_settings.ai_base_url,
            model=resolved_settings.ai_model,
            api_key=resolved_settings.ai_api_key or None,
            provider_name=provider,
        )

    if provider == "claude":
        return ClaudeProvider()

    raise AIProviderError(f"Unsupported AI provider: {resolved_settings.ai_provider}")
