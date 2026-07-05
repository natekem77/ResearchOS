"""Application configuration for ResearchOS.

Settings are loaded from environment variables so the same code can run in
local development, Docker, continuous integration, and production-like
deployments without source changes.
"""

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the ResearchOS backend.

    Most environment variables use the ``RESEARCHOS_`` prefix. Microsoft Graph
    auth settings also accept the exact variable names used by Azure examples,
    such as ``MICROSOFT_CLIENT_ID`` and ``GRAPH_SCOPES``.
    """

    project_name: str = Field(default="ResearchOS", description="Public project name.")
    environment: str = Field(default="development", description="Runtime environment.")
    log_level: str = Field(default="INFO", description="Python logging level.")

    api_host: str = Field(default="0.0.0.0", description="Host used by local API runners.")
    api_port: int = Field(default=8000, description="Port used by local API runners.")

    database_url: str = Field(
        default="sqlite:///./data/researchos.db",
        description="Database connection URL. SQLite is the initial default.",
    )
    chroma_persist_directory: str = Field(
        default="./data/chroma",
        description="Local persistence directory for ChromaDB collections.",
    )

    microsoft_client_id: str = Field(
        default="",
        description="Azure application client ID used for Microsoft Graph delegated login.",
        validation_alias=AliasChoices("MICROSOFT_CLIENT_ID", "RESEARCHOS_MICROSOFT_CLIENT_ID"),
    )
    microsoft_tenant_id: str = Field(
        default="common",
        description="Azure tenant ID. Use 'common' for multi-tenant development.",
        validation_alias=AliasChoices("MICROSOFT_TENANT_ID", "RESEARCHOS_MICROSOFT_TENANT_ID"),
    )
    microsoft_redirect_uri: str = Field(
        default="http://localhost:8000/auth/callback",
        description="Redirect URI registered for the Azure application.",
        validation_alias=AliasChoices("MICROSOFT_REDIRECT_URI", "RESEARCHOS_MICROSOFT_REDIRECT_URI"),
    )
    graph_scopes: str = Field(
        default="User.Read Notes.Read",
        description="Space-separated Microsoft Graph delegated scopes requested during login.",
        validation_alias=AliasChoices("GRAPH_SCOPES", "RESEARCHOS_GRAPH_SCOPES"),
    )

    ai_provider: str = Field(
        default="none",
        description="AI provider name: none, openai_compatible, ollama, lmstudio, claude.",
        validation_alias=AliasChoices("AI_PROVIDER", "RESEARCHOS_AI_PROVIDER"),
    )
    ai_api_key: str = Field(
        default="",
        description="Optional API key for cloud or authenticated OpenAI-compatible providers.",
        validation_alias=AliasChoices("AI_API_KEY", "RESEARCHOS_AI_API_KEY"),
    )
    ai_base_url: str = Field(
        default="",
        description="OpenAI-compatible base URL, including local Ollama or LM Studio endpoints.",
        validation_alias=AliasChoices("AI_BASE_URL", "RESEARCHOS_AI_BASE_URL"),
    )
    ai_model: str = Field(
        default="gpt-4o-mini",
        description="Chat model name for the configured AI provider.",
        validation_alias=AliasChoices("AI_MODEL", "RESEARCHOS_AI_MODEL"),
    )

    @property
    def graph_scope_list(self) -> list[str]:
        """Return Microsoft Graph scopes as a normalized list for MSAL."""

        return [scope for scope in self.graph_scopes.split() if scope]

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_prefix="RESEARCHOS_",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for dependency injection and app startup.

    Caching prevents repeated parsing of environment variables while keeping
    the settings object easy to override in tests.
    """

    return Settings()
