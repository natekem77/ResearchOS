"""Backend-enforced lab account and notebook sharing authorization.

This module keeps authorization decisions centralized. Route handlers should
ask ``AuthorizationService.can_user(...)`` instead of duplicating role and
sharing logic.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.config import Settings
from app.storage import SQLiteStore

LAB_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": {
        "lab.members.manage",
        "lab.roles.manage",
        "lab.notebooks.view_all",
        "lab.notebooks.comment_all",
        "lab.notebooks.manage_sharing",
        "lab.audit.view",
    },
    "admin": {"lab.members.manage"},
    "supervisor": set(),
    "researcher": set(),
    "guest": set(),
}

NOTEBOOK_ACCESS_ORDER = {"view": 1, "comment": 2, "edit": 3, "manage": 4}


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    elevated: bool = False


class AuthorizationService:
    """Centralized authorization and sharing service."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = SQLiteStore(settings=settings)
        self._ensure_schema()
        self.ensure_demo_data()

    def _connect(self) -> sqlite3.Connection:
        return self.store._connect()  # Central service owns these tables.

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS labs (
                    lab_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    institution TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    owner_user_id TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS lab_memberships (
                    membership_id TEXT PRIMARY KEY,
                    lab_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(lab_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS lab_member_permissions (
                    permission_id TEXT PRIMARY KEY,
                    lab_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    permission TEXT NOT NULL,
                    granted_by TEXT,
                    granted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(lab_id, user_id, permission)
                );

                CREATE TABLE IF NOT EXISTS notebooks (
                    notebook_id TEXT PRIMARY KEY,
                    lab_id TEXT NOT NULL,
                    owner_user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    visibility TEXT NOT NULL DEFAULT 'private',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS notebook_permissions (
                    permission_id TEXT PRIMARY KEY,
                    notebook_id TEXT NOT NULL,
                    principal_type TEXT NOT NULL,
                    principal_id TEXT NOT NULL,
                    access_level TEXT NOT NULL,
                    granted_by TEXT NOT NULL,
                    granted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    expires_at TEXT
                );

                CREATE TABLE IF NOT EXISTS lab_groups (
                    group_id TEXT PRIMARY KEY,
                    lab_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_by TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS lab_group_memberships (
                    group_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    added_by TEXT,
                    added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(group_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS notebook_entries (
                    entry_id TEXT PRIMARY KEY,
                    notebook_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    audit_id TEXT PRIMARY KEY,
                    actor_user_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    lab_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def ensure_demo_data(self) -> None:
        """Seed demo lab/users/notebooks while preserving existing data."""

        with self._connect() as connection:
            users = [
                ("user:pi-owner", "pi@researchos.local", "PI / Owner", "admin"),
                ("user:lab-admin", "admin@researchos.local", "Lab Admin", "admin"),
                ("user:researcher-a", "researcher.a@researchos.local", "Researcher A", "researcher"),
                ("user:researcher-b", "researcher.b@researchos.local", "Researcher B", "researcher"),
                ("user:guest", "guest@researchos.local", "Guest Scientist", "viewer"),
            ]
            for user_id, email, display_name, role in users:
                connection.execute(
                    """
                    INSERT INTO users (user_id, email, display_name, role, auth_provider)
                    VALUES (?, ?, ?, ?, 'demo')
                    ON CONFLICT(user_id) DO UPDATE SET
                        email = excluded.email,
                        display_name = excluded.display_name
                    """,
                    (user_id, email, display_name, role),
                )

            connection.execute(
                """
                INSERT INTO labs (lab_id, name, institution, owner_user_id)
                VALUES ('lab:demo', 'ResearchOS Demo Lab', 'Demo Institution', 'user:pi-owner')
                ON CONFLICT(lab_id) DO NOTHING
                """
            )
            for user_id, role in [
                ("user:pi-owner", "owner"),
                ("user:lab-admin", "admin"),
                ("user:researcher-a", "researcher"),
                ("user:researcher-b", "researcher"),
                ("user:guest", "guest"),
            ]:
                connection.execute(
                    """
                    INSERT INTO lab_memberships (membership_id, lab_id, user_id, role)
                    VALUES (?, 'lab:demo', ?, ?)
                    ON CONFLICT(lab_id, user_id) DO UPDATE SET role = excluded.role, active = 1
                    """,
                    (f"membership:{user_id}", user_id, role),
                )

            self._seed_notebook(
                connection,
                "notebook:researcher-a",
                "Researcher A private notebook",
                "user:researcher-a",
            )
            self._seed_notebook(
                connection,
                "notebook:researcher-b",
                "Researcher B private notebook",
                "user:researcher-b",
            )
            self._seed_notebook(
                connection,
                "notebook:shared-demo",
                "Shared SAG/BMP4 demo notebook",
                "user:researcher-a",
                visibility="shared",
            )
            self._grant_notebook_permission(
                connection,
                notebook_id="notebook:shared-demo",
                principal_type="user",
                principal_id="user:researcher-b",
                access_level="comment",
                granted_by="user:researcher-a",
            )

    def _seed_notebook(
        self,
        connection: sqlite3.Connection,
        notebook_id: str,
        title: str,
        owner_user_id: str,
        visibility: str = "private",
    ) -> None:
        connection.execute(
            """
            INSERT INTO notebooks (notebook_id, lab_id, owner_user_id, title, visibility)
            VALUES (?, 'lab:demo', ?, ?, ?)
            ON CONFLICT(notebook_id) DO NOTHING
            """,
            (notebook_id, owner_user_id, title, visibility),
        )
        connection.execute(
            """
            INSERT INTO notebook_entries (entry_id, notebook_id, title, body, state)
            VALUES (?, ?, ?, ?, 'draft')
            ON CONFLICT(entry_id) DO NOTHING
            """,
            (
                f"entry:{notebook_id}",
                notebook_id,
                "Demo entry",
                f"Demo content for {title}.",
            ),
        )

    def current_user_id(self, request_headers: dict[str, str] | None = None) -> str:
        headers = request_headers or {}
        return headers.get("x-researchos-user") or headers.get("X-ResearchOS-User") or "user:pi-owner"

    def user_access(self, user_id: str, lab_id: str = "lab:demo") -> dict[str, Any]:
        membership = self.membership(user_id, lab_id)
        role = str(membership.get("role") if membership else "guest")
        permissions = set(LAB_ROLE_PERMISSIONS.get(role, set()))
        permissions.update(self.explicit_lab_permissions(user_id, lab_id))
        return {"user_id": user_id, "lab_id": lab_id, "role": role, "permissions": sorted(permissions)}

    def membership(self, user_id: str, lab_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM lab_memberships WHERE lab_id = ? AND user_id = ? AND active = 1",
                (lab_id, user_id),
            ).fetchone()
            return dict(row) if row else None

    def explicit_lab_permissions(self, user_id: str, lab_id: str) -> set[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT permission FROM lab_member_permissions WHERE lab_id = ? AND user_id = ?",
                (lab_id, user_id),
            ).fetchall()
            return {str(row["permission"]) for row in rows}

    def can_user(
        self,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
    ) -> AuthorizationDecision:
        if resource_type != "notebook":
            return AuthorizationDecision(False, "Unsupported resource type.")
        notebook = self.get_notebook_raw(resource_id)
        if notebook is None:
            return AuthorizationDecision(False, "Notebook not found.")
        if notebook["owner_user_id"] == user_id:
            return AuthorizationDecision(True, "Notebook owner.")
        access = self.user_access(user_id, str(notebook["lab_id"]))
        required = _required_access(action)
        if "lab.notebooks.view_all" in access["permissions"] and required == "view":
            return AuthorizationDecision(True, "Lab view-all permission.", elevated=True)
        if notebook["visibility"] == "lab" and required == "view":
            return AuthorizationDecision(True, "Lab-visible notebook.")
        if self._has_notebook_grant(user_id, notebook, required):
            return AuthorizationDecision(True, "Explicit notebook grant.")
        return AuthorizationDecision(False, "Notebook is private or not shared.")

    def list_visible_notebooks(self, user_id: str, lab_id: str = "lab:demo") -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM notebooks WHERE lab_id = ? ORDER BY updated_at DESC", (lab_id,)).fetchall()
        notebooks = []
        for row in rows:
            notebook = dict(row)
            if self.can_user(user_id, "view", "notebook", notebook["notebook_id"]).allowed:
                notebooks.append(notebook)
        return notebooks

    def get_notebook(self, user_id: str, notebook_id: str) -> dict[str, Any] | None:
        decision = self.can_user(user_id, "view", "notebook", notebook_id)
        if not decision.allowed:
            return None
        notebook = self.get_notebook_raw(notebook_id)
        if notebook and decision.elevated and notebook["owner_user_id"] != user_id:
            self.audit(user_id, "notebook.viewed_elevated", "notebook", notebook_id, notebook["lab_id"], {"reason": decision.reason})
        return notebook

    def get_notebook_raw(self, notebook_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM notebooks WHERE notebook_id = ?", (notebook_id,)).fetchone()
            return dict(row) if row else None

    def list_members(self, lab_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(
                """
                SELECT lm.*, u.email, u.display_name
                FROM lab_memberships lm JOIN users u ON u.user_id = lm.user_id
                WHERE lm.lab_id = ? AND lm.active = 1
                ORDER BY u.display_name
                """,
                (lab_id,),
            ).fetchall()]

    def list_permissions(self, notebook_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM notebook_permissions WHERE notebook_id = ? ORDER BY granted_at DESC",
                (notebook_id,),
            ).fetchall()]

    def share_notebook(
        self,
        actor_user_id: str,
        notebook_id: str,
        principal_type: str,
        principal_id: str,
        access_level: str,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        if not self.can_user(actor_user_id, "manage", "notebook", notebook_id).allowed:
            raise PermissionError("User cannot manage notebook sharing.")
        with self._connect() as connection:
            permission = self._grant_notebook_permission(connection, notebook_id, principal_type, principal_id, access_level, actor_user_id, expires_at)
            notebook = connection.execute("SELECT lab_id FROM notebooks WHERE notebook_id = ?", (notebook_id,)).fetchone()
            self._audit_with_connection(
                connection,
                actor_user_id,
                "notebook.shared",
                "notebook",
                notebook_id,
                notebook["lab_id"] if notebook else None,
                permission,
            )
            return permission

    def _grant_notebook_permission(
        self,
        connection: sqlite3.Connection,
        notebook_id: str,
        principal_type: str,
        principal_id: str,
        access_level: str,
        granted_by: str,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        permission_id = f"notebook-permission:{uuid.uuid4().hex}"
        connection.execute(
            """
            INSERT INTO notebook_permissions
                (permission_id, notebook_id, principal_type, principal_id, access_level, granted_by, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (permission_id, notebook_id, principal_type, principal_id, access_level, granted_by, expires_at),
        )
        connection.execute("UPDATE notebooks SET visibility = 'shared', updated_at = CURRENT_TIMESTAMP WHERE notebook_id = ?", (notebook_id,))
        return {
            "permission_id": permission_id,
            "notebook_id": notebook_id,
            "principal_type": principal_type,
            "principal_id": principal_id,
            "access_level": access_level,
            "granted_by": granted_by,
            "expires_at": expires_at,
        }

    def update_permission(self, actor_user_id: str, notebook_id: str, permission_id: str, access_level: str) -> dict[str, Any] | None:
        if not self.can_user(actor_user_id, "manage", "notebook", notebook_id).allowed:
            raise PermissionError("User cannot manage notebook sharing.")
        with self._connect() as connection:
            connection.execute("UPDATE notebook_permissions SET access_level = ? WHERE permission_id = ? AND notebook_id = ?", (access_level, permission_id, notebook_id))
            row = connection.execute("SELECT * FROM notebook_permissions WHERE permission_id = ?", (permission_id,)).fetchone()
            notebook = connection.execute("SELECT lab_id FROM notebooks WHERE notebook_id = ?", (notebook_id,)).fetchone()
            self._audit_with_connection(
                connection,
                actor_user_id,
                "notebook.permission_changed",
                "notebook",
                notebook_id,
                notebook["lab_id"] if notebook else None,
                {"permission_id": permission_id, "access_level": access_level},
            )
            return dict(row) if row else None

    def revoke_permission(self, actor_user_id: str, notebook_id: str, permission_id: str) -> bool:
        if not self.can_user(actor_user_id, "manage", "notebook", notebook_id).allowed:
            raise PermissionError("User cannot manage notebook sharing.")
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM notebook_permissions WHERE permission_id = ? AND notebook_id = ?", (permission_id, notebook_id))
            notebook = connection.execute("SELECT lab_id FROM notebooks WHERE notebook_id = ?", (notebook_id,)).fetchone()
            self._audit_with_connection(
                connection,
                actor_user_id,
                "notebook.permission_revoked",
                "notebook",
                notebook_id,
                notebook["lab_id"] if notebook else None,
                {"permission_id": permission_id},
            )
            return cursor.rowcount > 0

    def create_group(self, actor_user_id: str, lab_id: str, name: str, description: str | None = None) -> dict[str, Any]:
        if "lab.members.manage" not in self.user_access(actor_user_id, lab_id)["permissions"]:
            raise PermissionError("User cannot create groups.")
        group_id = f"group:{uuid.uuid4().hex}"
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO lab_groups (group_id, lab_id, name, description, created_by) VALUES (?, ?, ?, ?, ?)",
                (group_id, lab_id, name, description, actor_user_id),
            )
            self._audit_with_connection(connection, actor_user_id, "group.created", "group", group_id, lab_id, {"name": name})
        return {"group_id": group_id, "lab_id": lab_id, "name": name, "description": description}

    def add_group_member(self, actor_user_id: str, group_id: str, user_id: str) -> dict[str, Any]:
        group = self.get_group(group_id)
        if group is None:
            raise KeyError("Group not found.")
        if "lab.members.manage" not in self.user_access(actor_user_id, group["lab_id"])["permissions"]:
            raise PermissionError("User cannot manage groups.")
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO lab_group_memberships (group_id, user_id, added_by) VALUES (?, ?, ?)",
                (group_id, user_id, actor_user_id),
            )
            self._audit_with_connection(connection, actor_user_id, "group.member_added", "group", group_id, group["lab_id"], {"user_id": user_id})
        return {"group_id": group_id, "user_id": user_id}

    def get_group(self, group_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM lab_groups WHERE group_id = ?", (group_id,)).fetchone()
            return dict(row) if row else None

    def notebook_entries(self, user_id: str, notebook_id: str) -> list[dict[str, Any]]:
        if not self.can_user(user_id, "view", "notebook", notebook_id).allowed:
            raise PermissionError("User cannot view notebook entries.")
        with self._connect() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM notebook_entries WHERE notebook_id = ? ORDER BY created_at", (notebook_id,)).fetchall()]

    def entry_detail(self, user_id: str, entry_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM notebook_entries WHERE entry_id = ?", (entry_id,)).fetchone()
        if not row:
            return None
        entry = dict(row)
        if not self.can_user(user_id, "view", "notebook", entry["notebook_id"]).allowed:
            raise PermissionError("User cannot view notebook entry.")
        return entry

    def audit(self, actor_user_id: str, action: str, resource_type: str, resource_id: str, lab_id: str | None, metadata: dict[str, Any]) -> None:
        with self._connect() as connection:
            self._audit_with_connection(connection, actor_user_id, action, resource_type, resource_id, lab_id, metadata)

    def _audit_with_connection(
        self,
        connection: sqlite3.Connection,
        actor_user_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        lab_id: str | None,
        metadata: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_events (audit_id, actor_user_id, action, resource_type, resource_id, lab_id, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (f"audit:{uuid.uuid4().hex}", actor_user_id, action, resource_type, resource_id, lab_id, json.dumps(metadata)),
        )

    def audit_events(self, user_id: str, lab_id: str) -> list[dict[str, Any]]:
        if "lab.audit.view" not in self.user_access(user_id, lab_id)["permissions"]:
            raise PermissionError("User cannot view audit logs.")
        with self._connect() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM audit_events WHERE lab_id = ? ORDER BY created_at DESC", (lab_id,)).fetchall()]

    def _has_notebook_grant(self, user_id: str, notebook: dict[str, Any], required: str) -> bool:
        required_rank = NOTEBOOK_ACCESS_ORDER[required]
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM notebook_permissions WHERE notebook_id = ?", (notebook["notebook_id"],)).fetchall()
            group_ids = {row["group_id"] for row in connection.execute("SELECT group_id FROM lab_group_memberships WHERE user_id = ?", (user_id,)).fetchall()}
        access = self.user_access(user_id, str(notebook["lab_id"]))
        for row in rows:
            grant = dict(row)
            if NOTEBOOK_ACCESS_ORDER.get(grant["access_level"], 0) < required_rank:
                continue
            if grant["principal_type"] == "user" and grant["principal_id"] == user_id:
                return True
            if grant["principal_type"] == "group" and grant["principal_id"] in group_ids:
                return True
            if grant["principal_type"] == "role" and grant["principal_id"] == access["role"]:
                return True
        return False


def _required_access(action: str) -> str:
    if action in {"manage", "share", "delete"}:
        return "manage"
    if action in {"edit", "update"}:
        return "edit"
    if action in {"comment"}:
        return "comment"
    return "view"
