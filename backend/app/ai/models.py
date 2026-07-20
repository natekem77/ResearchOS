"""Shared AI platform data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


AIOutputMode = Literal["text", "markdown", "json", "tool_calls"]


@dataclass(frozen=True)
class AIProviderSpec:
    provider_id: str
    display_name: str
    provider_type: str
    supports_streaming: bool = False
    supports_json: bool = False
    supports_tools: bool = False
    supports_vision: bool = False
    supports_embeddings: bool = False
    openai_compatible: bool = False
    requires_api_key: bool = False
    default_endpoint: str | None = None


@dataclass
class AIProviderConfig:
    provider_config_id: str
    provider: str
    display_name: str
    enabled: bool
    endpoint: str | None = None
    default_model: str | None = None
    api_key_configured: bool = False
    is_preferred: bool = False
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class AIMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AIRequest:
    messages: list[AIMessage]
    provider_config_id: str | None = None
    model: str | None = None
    temperature: float = 0.2
    max_tokens: int | None = None
    timeout_seconds: int = 60
    output_mode: AIOutputMode = "markdown"
    json_schema: dict[str, Any] | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class AIResponse:
    content: str
    provider: str
    model: str | None
    output_mode: AIOutputMode = "markdown"
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PromptTemplate:
    prompt_id: str
    title: str
    system_prompt: str
    required_context: list[str]
    allowed_tools: list[str]
    expected_schema: dict[str, Any] | None = None


@dataclass(frozen=True)
class AISkill:
    skill_id: str
    title: str
    prompt_id: str
    required_permissions: list[str]
    default_output_mode: AIOutputMode = "markdown"
    description: str = ""


@dataclass(frozen=True)
class AITool:
    tool_id: str
    title: str
    description: str
    parameters_schema: dict[str, Any]
    required_permissions: list[str]

