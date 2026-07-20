"""Registry of AI provider families supported by the platform."""

from __future__ import annotations

from app.ai.models import AIProviderSpec


class AIProviderRegistry:
    """Provider catalog independent from feature code."""

    def __init__(self) -> None:
        self._providers: dict[str, AIProviderSpec] = {}
        for spec in _BUILTIN_PROVIDERS:
            self.register(spec)

    def register(self, spec: AIProviderSpec) -> None:
        self._providers[spec.provider_id] = spec

    def get(self, provider_id: str) -> AIProviderSpec | None:
        return self._providers.get(provider_id)

    def list(self) -> list[AIProviderSpec]:
        return sorted(self._providers.values(), key=lambda item: item.display_name)


_BUILTIN_PROVIDERS = [
    AIProviderSpec(
        "openai",
        "OpenAI",
        "cloud",
        supports_streaming=True,
        supports_json=True,
        supports_tools=True,
        supports_vision=True,
        supports_embeddings=True,
        openai_compatible=True,
        requires_api_key=True,
        default_endpoint="https://api.openai.com/v1",
    ),
    AIProviderSpec("anthropic", "Claude", "cloud", supports_streaming=True, supports_json=True, supports_tools=True, requires_api_key=True),
    AIProviderSpec("gemini", "Google Gemini", "cloud", supports_streaming=True, supports_json=True, supports_vision=True, requires_api_key=True),
    AIProviderSpec("grok", "Grok", "cloud", supports_streaming=True, supports_json=True, requires_api_key=True),
    AIProviderSpec("openrouter", "OpenRouter", "cloud", supports_streaming=True, supports_json=True, supports_tools=True, openai_compatible=True, requires_api_key=True, default_endpoint="https://openrouter.ai/api/v1"),
    AIProviderSpec("ollama", "Ollama", "local", supports_streaming=True, supports_json=True, openai_compatible=True, default_endpoint="http://localhost:11434/v1"),
    AIProviderSpec("lmstudio", "LM Studio", "local", supports_streaming=True, supports_json=True, openai_compatible=True, default_endpoint="http://localhost:1234/v1"),
    AIProviderSpec("vllm", "vLLM", "local", supports_streaming=True, supports_json=True, openai_compatible=True, default_endpoint="http://localhost:8000/v1"),
    AIProviderSpec("custom-openai-compatible", "Custom OpenAI Endpoint", "custom", supports_streaming=True, supports_json=True, supports_tools=True, supports_vision=True, supports_embeddings=True, openai_compatible=True),
]

