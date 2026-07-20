"""AI permission checks."""

from __future__ import annotations


class AIPermissionError(PermissionError):
    """Raised when a user cannot run a skill or tool."""


class AIPermissionService:
    """Small permission adapter for AI skills.

    The platform keeps required permissions explicit. Demo mode allows read-only
    skill execution while preserving the place where stricter AuthorizationService
    checks plug in.
    """

    def assert_allowed(self, actor_user_id: str, required_permissions: list[str]) -> None:
        if not actor_user_id:
            raise AIPermissionError("AI requests require an authenticated actor.")
        denied = [item for item in required_permissions if item.endswith(".modify")]
        if denied:
            raise AIPermissionError(f"AI cannot modify data without explicit approval: {', '.join(denied)}")

