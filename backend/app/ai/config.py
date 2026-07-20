"""AI platform configuration helpers."""

from app.config import Settings


def ai_runtime_config(settings: Settings) -> dict[str, object]:
    return {
        "provider": settings.ai_provider,
        "model": settings.ai_model,
        "timeout_seconds": settings.protocol_extraction_timeout_seconds,
        "protocol_extraction_enabled": settings.protocol_extraction_ai_enabled,
        "max_source_chars": settings.protocol_extraction_max_source_chars,
    }

