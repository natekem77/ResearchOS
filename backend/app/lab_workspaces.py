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


class ActiveWorkspaceService:
    """Resolve and persist the active lab workspace for the current user.

    Workspace awareness is metadata-only for now. The service records which
    workspace is active, while endpoints use that value for permissive filtering
    that still includes legacy unscoped local rows.
    """

    def __init__(self, settings: Settings, store: SQLiteStore) -> None:
        self.settings = settings
        self.store = store

    def ensure_default_workspace(self) -> dict[str, Any]:
        """Create the demo/default lab workspace and attach the current user."""

        user = current_user(self.settings, self.store)
        workspace = self.store.upsert_workspace(
            workspace_id=DEFAULT_WORKSPACE_ID,
            name="ResearchOS Demo Lab",
            institution="ResearchOS Local Demo",
            description="Default local development workspace for demos, PWA testing, and early lab-server setup.",
            owner_user_id=str(user["user_id"]),
            created_by=str(user["user_id"]),
            default_role="researcher",
            settings={
                "mode": "development" if not self.settings.auth_enabled else "auth_enabled",
                "strict_isolation": False,
                "default_workspace": True,
                "workspace_scoping": "metadata_only",
            },
        )
        self.store.upsert_workspace_membership(
            workspace_id=str(workspace["workspace_id"]),
            user_id=str(user["user_id"]),
            role="admin",
        )
        if self.store.get_active_workspace_id(str(user["user_id"])) is None:
            self.store.set_active_workspace(str(user["user_id"]), str(workspace["workspace_id"]))
        return workspace_with_membership(self.store, workspace, str(user["user_id"]))

    def get_current_workspace(self) -> dict[str, Any]:
        """Return the selected workspace, falling back to the default workspace."""

        user = current_user(self.settings, self.store)
        workspace_id = self.store.get_active_workspace_id(str(user["user_id"]))
        if workspace_id:
            workspace = self.store.get_workspace(workspace_id)
            if workspace is not None:
                return workspace_with_membership(self.store, workspace, str(user["user_id"]))
        return self.ensure_default_workspace()

    def set_current_workspace(self, workspace_id: str) -> dict[str, Any]:
        """Persist the current user's active workspace."""

        user = current_user(self.settings, self.store)
        workspace = self.store.set_active_workspace(str(user["user_id"]), workspace_id)
        if workspace is None:
            raise LookupError(f"Workspace not found: {workspace_id}")
        if self.store.get_workspace_membership(workspace_id, str(user["user_id"])) is None and not self.settings.auth_enabled:
            self.store.upsert_workspace_membership(workspace_id, str(user["user_id"]), "admin")
        return workspace_with_membership(self.store, workspace, str(user["user_id"]))


def bootstrap_default_workspace(settings: Settings, store: SQLiteStore) -> dict[str, Any]:
    """Create the demo/default lab workspace and attach the current user."""

    return ActiveWorkspaceService(settings, store).ensure_default_workspace()


def current_workspace(settings: Settings, store: SQLiteStore) -> dict[str, Any]:
    """Return the current workspace, bootstrapping demo workspace when needed."""

    return ActiveWorkspaceService(settings, store).get_current_workspace()


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
