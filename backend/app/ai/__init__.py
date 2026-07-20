"""Provider-agnostic AI platform for Mundi."""

from app.ai.provider_manager import AIService, get_ai_provider

__all__ = ["AIService", "get_ai_provider"]
