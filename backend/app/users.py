"""ResearchOS user and permission scaffolding.

This is intentionally lightweight for local/demo mode. It prepares the backend
for future Microsoft/UCSD identity mapping without enforcing auth across the
existing demo workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.config import Settings
from app.storage import SQLiteStore

UserRole = Literal["admin", "researcher", "viewer"]

ROLE_PERMISSIONS: dict[str, dict[str, bool]] = {
    "admin": {"can_view": True, "can_edit": True, "can_admin": True},
    "researcher": {"can_view": True, "can_edit": True, "can_admin": False},
    "viewer": {"can_view": True, "can_edit": False, "can_admin": False},
}


@dataclass(frozen=True)
class User:
    """Basic ResearchOS user model."""

    user_id: str
    email: str
    display_name: str
    role: UserRole
    created_at: str | None = None
    last_login: str | None = None
    auth_provider: str = "local_dev"


def normalize_role(role: str) -> UserRole:
    """Normalize a role label."""

    normalized = role.strip().lower()
    if normalized not in ROLE_PERMISSIONS:
        raise ValueError(f"Unknown role: {role}")
    return normalized  # type: ignore[return-value]


def permissions_for_role(role: str) -> dict[str, bool]:
    """Return permission scaffolding for one role."""

    return dict(ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["viewer"]))


def user_with_permissions(user: dict[str, object]) -> dict[str, object]:
    """Add computed permission booleans to a user response."""

    role = str(user.get("role") or "viewer")
    return {**user, "permissions": permissions_for_role(role)}


def dev_user_id(settings: Settings) -> str:
    """Return stable development-mode user ID."""

    return "user:dev-local"


def current_user(settings: Settings, store: SQLiteStore) -> dict[str, object]:
    """Return the current ResearchOS user.

    Auth enforcement is intentionally disabled by default. In that mode,
    ResearchOS creates/updates a local admin user so demos, PWA access, smoke
    tests, OneNote auth, and provider workflows keep working.
    """

    if not settings.auth_enabled:
        user = store.upsert_user(
            user_id=dev_user_id(settings),
            email=settings.dev_user_email,
            display_name=settings.dev_user_display_name,
            role="admin",
            auth_provider="local_dev",
            mark_login=True,
        )
        return user_with_permissions(user)

    # Placeholder for future Microsoft/UCSD auth. Until request-bound auth is
    # introduced, return the dev user as a safe bootstrap fallback.
    user = store.get_user(dev_user_id(settings))
    if user is None:
        user = store.upsert_user(
            user_id=dev_user_id(settings),
            email=settings.dev_user_email,
            display_name=settings.dev_user_display_name,
            role="admin",
            auth_provider="local_dev",
            mark_login=True,
        )
    return user_with_permissions(user)


def auth_mode(settings: Settings) -> str:
    """Return user-facing auth mode."""

    return "enabled" if settings.auth_enabled else "disabled_dev_mode"

