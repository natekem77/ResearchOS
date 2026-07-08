"""Lab Workspace scaffolding for ResearchOS multi-user deployment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config import Settings
from app.storage import SQLiteStore
from app.users import current_user

DEFAULT_WORKSPACE_ID = "workspace:demo-lab"


@dataclass(frozen=True)
class LabWorkspace:
    """A lab or project workspace containing users and research records."""

    workspace_id: str
    name: str
    institution: str | None = None
    description: str | None = None
    owner_user_id: str | None = None
    settings: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None


def bootstrap_default_workspace(settings: Settings, store: SQLiteStore) -> dict[str, Any]:
    """Create the demo/default lab workspace and attach the current user."""

    user = current_user(settings, store)
    workspace = store.upsert_workspace(
        workspace_id=DEFAULT_WORKSPACE_ID,
        name="Demo Lab Workspace",
        institution="ResearchOS Local Demo",
        description="Default local development workspace for demos, PWA testing, and early lab-server setup.",
        owner_user_id=str(user["user_id"]),
        settings={
            "mode": "development" if not settings.auth_enabled else "auth_enabled",
            "strict_isolation": False,
            "default_workspace": True,
        },
    )
    store.upsert_workspace_membership(
        workspace_id=str(workspace["workspace_id"]),
        user_id=str(user["user_id"]),
        role="admin",
    )
    return workspace_with_membership(store, workspace, str(user["user_id"]))


def current_workspace(settings: Settings, store: SQLiteStore) -> dict[str, Any]:
    """Return the current workspace, bootstrapping demo workspace when needed."""

    if not settings.auth_enabled:
        return bootstrap_default_workspace(settings, store)
    workspace = store.get_workspace(DEFAULT_WORKSPACE_ID)
    if workspace is None:
        return bootstrap_default_workspace(settings, store)
    user = current_user(settings, store)
    return workspace_with_membership(store, workspace, str(user["user_id"]))


def workspace_with_membership(
    store: SQLiteStore,
    workspace: dict[str, Any],
    user_id: str | None = None,
) -> dict[str, Any]:
    """Attach membership and counts metadata to a workspace response."""

    workspace_id = str(workspace["workspace_id"])
    membership = store.get_workspace_membership(workspace_id, user_id) if user_id else None
    return {
        **workspace,
        "current_user_membership": membership,
        "members": store.list_workspace_memberships(workspace_id),
        "counts": store.workspace_counts(workspace_id),
    }

