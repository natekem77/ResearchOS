"""Persistent, backend-authorized lab chat foundation.

Private group chats and direct messages intentionally do not have an elevated
owner/admin override. Current membership is the only read path.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from app.authorization import AuthorizationService
from app.config import Settings
from app.storage import SQLiteStore

ConversationType = Literal["lab_channel", "project_channel", "group_chat", "direct_message"]
MembershipPolicy = Literal["members_manage", "moderators_manage", "creator_manages"]
MemberRole = Literal["owner", "moderator", "member"]
AttachmentType = Literal[
    "file",
    "experiment",
    "notebook",
    "entry",
    "image",
    "protocol",
    "inventory",
    "purchase_request",
    "design",
    "statistic",
    "paper",
    "custom",
]

PRIVATE_CONVERSATION_TYPES = {"group_chat", "direct_message"}


@dataclass(frozen=True)
class ChatAccessDecision:
    allowed: bool
    reason: str


class ChatAuthorizationError(PermissionError):
    """Raised when a user is not authorized for a chat action."""


class ChatValidationError(ValueError):
    """Raised when a chat request violates conversation rules."""


class LabChatService:
    """Repository and authorization boundary for ResearchOS lab chat."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = SQLiteStore(settings=settings)
        self.authz = AuthorizationService(settings=settings)
        self._ensure_schema()
        self.ensure_demo_data()

    def _connect(self) -> sqlite3.Connection:
        return self.store._connect()

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    lab_id TEXT NOT NULL,
                    conversation_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    project_id TEXT,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    archived_at TEXT,
                    membership_policy TEXT NOT NULL DEFAULT 'members_manage'
                );

                CREATE INDEX IF NOT EXISTS idx_conversations_lab
                    ON conversations(lab_id);
                CREATE INDEX IF NOT EXISTS idx_conversations_type
                    ON conversations(conversation_type);

                CREATE TABLE IF NOT EXISTS conversation_members (
                    conversation_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    member_role TEXT NOT NULL DEFAULT 'member',
                    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    added_by TEXT,
                    removed_at TEXT,
                    removed_by TEXT,
                    muted INTEGER NOT NULL DEFAULT 0,
                    last_read_message_id TEXT,
                    PRIMARY KEY(conversation_id, user_id, joined_at)
                );

                CREATE INDEX IF NOT EXISTS idx_conversation_members_user
                    ON conversation_members(user_id, removed_at);
                CREATE INDEX IF NOT EXISTS idx_conversation_members_conversation
                    ON conversation_members(conversation_id, removed_at);

                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    sender_user_id TEXT NOT NULL,
                    body TEXT NOT NULL,
                    message_type TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    edited_at TEXT,
                    deleted_at TEXT,
                    reply_to_message_id TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
                    ON messages(conversation_id, created_at);

                CREATE TABLE IF NOT EXISTS message_attachments (
                    attachment_id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    attachment_type TEXT NOT NULL,
                    resource_id TEXT,
                    display_name TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS conversation_membership_events (
                    event_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor_user_id TEXT NOT NULL,
                    target_user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def ensure_demo_data(self) -> None:
        """Seed channels and private demo conversations without exposing content."""

        self._seed_channel("chat:general", "General Lab Chat", "General lab coordination.")
        self._seed_channel("chat:announcements", "Announcements", "Lab-wide announcements.", policy="moderators_manage")
        self._seed_channel("chat:inventory", "Inventory", "Inventory and purchasing coordination.")
        self._seed_channel("chat:sag-project", "SAG Project", "SAG project discussion.", conversation_type="project_channel", project_id="project:sag")
        self._seed_group_chat()
        self._seed_direct_message()

    def _seed_channel(
        self,
        conversation_id: str,
        name: str,
        description: str,
        conversation_type: ConversationType = "lab_channel",
        policy: MembershipPolicy = "members_manage",
        project_id: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO conversations
                    (conversation_id, lab_id, conversation_type, name, description, project_id, created_by, membership_policy)
                VALUES (?, 'lab:demo', ?, ?, ?, ?, 'user:pi-owner', ?)
                ON CONFLICT(conversation_id) DO NOTHING
                """,
                (conversation_id, conversation_type, name, description, project_id, policy),
            )
            for user_id, role in [
                ("user:pi-owner", "owner"),
                ("user:lab-admin", "moderator"),
                ("user:researcher-a", "member"),
                ("user:researcher-b", "member"),
                ("user:researcher-c", "member"),
            ]:
                self._add_member_row(connection, conversation_id, user_id, role, "user:pi-owner")
            if not self._has_messages(connection, conversation_id):
                self._insert_message(
                    connection,
                    conversation_id,
                    "user:pi-owner",
                    f"Welcome to {name}.",
                    attachments=[],
                )

    def _seed_group_chat(self) -> None:
        conversation_id = "chat:private-ab"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO conversations
                    (conversation_id, lab_id, conversation_type, name, description, created_by, membership_policy)
                VALUES (?, 'lab:demo', 'group_chat', 'SAG private planning', 'Private group chat for SAG planning.', 'user:researcher-a', 'members_manage')
                ON CONFLICT(conversation_id) DO NOTHING
                """,
                (conversation_id,),
            )
            self._add_member_row(connection, conversation_id, "user:researcher-a", "owner", "user:researcher-a")
            self._add_member_row(connection, conversation_id, "user:researcher-b", "member", "user:researcher-a")
            if not self._has_messages(connection, conversation_id):
                self._insert_message(
                    connection,
                    conversation_id,
                    "user:researcher-a",
                    "Can you look at the NK_Expt_31 SAG timeline before imaging?",
                    attachments=[
                        {
                            "attachment_type": "experiment",
                            "resource_id": "NK_Expt_31",
                            "display_name": "NK_Expt_31",
                        }
                    ],
                )
                self._insert_message(
                    connection,
                    conversation_id,
                    "user:researcher-b",
                    "Yes. I will also check the D32 design reminders.",
                    attachments=[
                        {
                            "attachment_type": "design",
                            "resource_id": "design:demo-d1-d9",
                            "display_name": "D1/D9 SAG design",
                        }
                    ],
                )
                self._add_member_row(connection, conversation_id, "user:researcher-c", "member", "user:researcher-a")
                self._membership_event(connection, conversation_id, "member_added", "user:researcher-a", "user:researcher-c")
                self._system_message(connection, conversation_id, "Researcher C was added by Researcher A.")
                self._remove_member_row(connection, conversation_id, "user:researcher-c", "user:researcher-b")
                self._membership_event(connection, conversation_id, "member_removed", "user:researcher-b", "user:researcher-c")
                self._system_message(connection, conversation_id, "Researcher C was removed by Researcher B.")

    def _seed_direct_message(self) -> None:
        conversation_id = "chat:dm-a-b"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO conversations
                    (conversation_id, lab_id, conversation_type, name, description, created_by, membership_policy)
                VALUES (?, 'lab:demo', 'direct_message', 'Researcher A + Researcher B', 'Direct message.', 'user:researcher-a', 'creator_manages')
                ON CONFLICT(conversation_id) DO NOTHING
                """,
                (conversation_id,),
            )
            self._add_member_row(connection, conversation_id, "user:researcher-a", "owner", "user:researcher-a")
            self._add_member_row(connection, conversation_id, "user:researcher-b", "member", "user:researcher-a")
            if not self._has_messages(connection, conversation_id):
                self._insert_message(
                    connection,
                    conversation_id,
                    "user:researcher-b",
                    "I ordered the SAG aliquot for the next run.",
                    attachments=[
                        {
                            "attachment_type": "inventory",
                            "resource_id": "inventory:demo-sag",
                            "display_name": "SAG aliquot",
                        }
                    ],
                )

    def list_conversations(self, user_id: str, lab_id: str = "lab:demo") -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM conversations WHERE lab_id = ? AND archived_at IS NULL ORDER BY created_at DESC",
                (lab_id,),
            ).fetchall()
        return [self._public_conversation(user_id, dict(row)) for row in rows if self.can_access_conversation(user_id, str(row["conversation_id"])).allowed]

    def get_conversation(self, user_id: str, conversation_id: str) -> dict[str, Any] | None:
        decision = self.can_access_conversation(user_id, conversation_id)
        if not decision.allowed:
            return None
        conversation = self._conversation(conversation_id)
        return self._public_conversation(user_id, conversation) if conversation else None

    def create_conversation(
        self,
        actor_user_id: str,
        lab_id: str,
        conversation_type: ConversationType,
        name: str,
        description: str | None = None,
        project_id: str | None = None,
        member_user_ids: list[str] | None = None,
        membership_policy: MembershipPolicy = "members_manage",
    ) -> dict[str, Any]:
        self._require_lab_member(actor_user_id, lab_id)
        member_user_ids = list(dict.fromkeys(member_user_ids or []))
        if conversation_type == "direct_message" and len([u for u in member_user_ids if u != actor_user_id]) != 1:
            raise ChatValidationError("Direct messages must contain exactly two participants.")
        if conversation_type in PRIVATE_CONVERSATION_TYPES:
            for member_user_id in member_user_ids:
                self._require_lab_member(member_user_id, lab_id)
        conversation_id = f"chat:{uuid.uuid4().hex}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO conversations
                    (conversation_id, lab_id, conversation_type, name, description, project_id, created_by, membership_policy)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (conversation_id, lab_id, conversation_type, name, description, project_id, actor_user_id, membership_policy),
            )
            self._add_member_row(connection, conversation_id, actor_user_id, "owner", actor_user_id)
            if conversation_type in PRIVATE_CONVERSATION_TYPES or member_user_ids:
                for member_user_id in member_user_ids:
                    if member_user_id != actor_user_id:
                        self._add_member_row(connection, conversation_id, member_user_id, "member", actor_user_id)
            self._audit(connection, actor_user_id, "conversation.created", "conversation", conversation_id, lab_id, {"conversation_type": conversation_type})
        conversation = self.get_conversation(actor_user_id, conversation_id)
        assert conversation is not None
        return conversation

    def update_conversation(self, actor_user_id: str, conversation_id: str, name: str | None, description: str | None) -> dict[str, Any]:
        conversation = self._require_conversation_access(actor_user_id, conversation_id)
        if not self._can_manage_conversation(actor_user_id, conversation):
            raise ChatAuthorizationError("User cannot update this conversation.")
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE conversations
                SET name = COALESCE(?, name), description = COALESCE(?, description)
                WHERE conversation_id = ?
                """,
                (name, description, conversation_id),
            )
        updated = self.get_conversation(actor_user_id, conversation_id)
        assert updated is not None
        return updated

    def archive_conversation(self, actor_user_id: str, conversation_id: str) -> dict[str, Any]:
        conversation = self._require_conversation_access(actor_user_id, conversation_id)
        if not self._can_manage_conversation(actor_user_id, conversation):
            raise ChatAuthorizationError("User cannot archive this conversation.")
        now = _now()
        with self._connect() as connection:
            connection.execute("UPDATE conversations SET archived_at = ? WHERE conversation_id = ?", (now, conversation_id))
            self._audit(connection, actor_user_id, "conversation.archived", "conversation", conversation_id, conversation["lab_id"], {})
        return {"conversation_id": conversation_id, "archived_at": now}

    def list_members(self, user_id: str, conversation_id: str) -> list[dict[str, Any]]:
        self._require_conversation_access(user_id, conversation_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT cm.*, u.display_name, u.email
                FROM conversation_members cm JOIN users u ON u.user_id = cm.user_id
                WHERE cm.conversation_id = ? AND cm.removed_at IS NULL
                ORDER BY cm.joined_at
                """,
                (conversation_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_member(self, actor_user_id: str, conversation_id: str, target_user_id: str, member_role: MemberRole = "member") -> dict[str, Any]:
        conversation = self._require_conversation_access(actor_user_id, conversation_id)
        if conversation["conversation_type"] == "direct_message":
            raise ChatValidationError("Direct messages cannot add a third participant.")
        self._require_lab_member(target_user_id, str(conversation["lab_id"]))
        if not self._can_manage_members(actor_user_id, conversation):
            raise ChatAuthorizationError("User cannot add members to this conversation.")
        with self._connect() as connection:
            self._add_member_row(connection, conversation_id, target_user_id, member_role, actor_user_id)
            self._membership_event(connection, conversation_id, "member_added", actor_user_id, target_user_id)
            self._system_message(connection, conversation_id, f"{self._display_name(connection, target_user_id)} was added.")
            self._audit(connection, actor_user_id, "conversation.member_added", "conversation", conversation_id, conversation["lab_id"], {"target_user_id": target_user_id})
        return {"conversation_id": conversation_id, "user_id": target_user_id, "member_role": member_role}

    def remove_member(self, actor_user_id: str, conversation_id: str, target_user_id: str) -> dict[str, Any]:
        conversation = self._require_conversation_access(actor_user_id, conversation_id)
        if conversation["conversation_type"] == "direct_message":
            raise ChatValidationError("Direct-message participants cannot be removed.")
        if not self._can_manage_members(actor_user_id, conversation) and actor_user_id != target_user_id:
            raise ChatAuthorizationError("User cannot remove members from this conversation.")
        with self._connect() as connection:
            active_count = connection.execute(
                "SELECT COUNT(*) AS count FROM conversation_members WHERE conversation_id = ? AND removed_at IS NULL",
                (conversation_id,),
            ).fetchone()["count"]
            if active_count <= 1:
                raise ChatValidationError("Cannot remove the final remaining member.")
            if self._active_member_row(connection, conversation_id, target_user_id) is None:
                raise ChatValidationError("User is not an active conversation member.")
            self._remove_member_row(connection, conversation_id, target_user_id, actor_user_id)
            self._membership_event(connection, conversation_id, "member_left" if actor_user_id == target_user_id else "member_removed", actor_user_id, target_user_id)
            self._system_message(connection, conversation_id, f"{self._display_name(connection, target_user_id)} left." if actor_user_id == target_user_id else f"{self._display_name(connection, target_user_id)} was removed.")
            self._audit(connection, actor_user_id, "conversation.member_removed", "conversation", conversation_id, conversation["lab_id"], {"target_user_id": target_user_id})
        return {"conversation_id": conversation_id, "user_id": target_user_id, "removed": True}

    def set_member_role(self, actor_user_id: str, conversation_id: str, target_user_id: str, member_role: MemberRole) -> dict[str, Any]:
        conversation = self._require_conversation_access(actor_user_id, conversation_id)
        if not self._can_manage_members(actor_user_id, conversation):
            raise ChatAuthorizationError("User cannot change member roles.")
        with self._connect() as connection:
            if self._active_member_row(connection, conversation_id, target_user_id) is None:
                raise ChatValidationError("User is not an active conversation member.")
            connection.execute(
                "UPDATE conversation_members SET member_role = ? WHERE conversation_id = ? AND user_id = ? AND removed_at IS NULL",
                (member_role, conversation_id, target_user_id),
            )
            self._membership_event(connection, conversation_id, "role_changed", actor_user_id, target_user_id)
            self._system_message(connection, conversation_id, f"{self._display_name(connection, target_user_id)} is now {member_role}.")
        return {"conversation_id": conversation_id, "user_id": target_user_id, "member_role": member_role}

    def list_messages(self, user_id: str, conversation_id: str, limit: int = 50, cursor: str | None = None) -> dict[str, Any]:
        self._require_conversation_access(user_id, conversation_id)
        limit = max(1, min(limit, 100))
        with self._connect() as connection:
            cursor_clause = ""
            params: list[Any] = [conversation_id]
            if cursor:
                cursor_row = connection.execute("SELECT created_at FROM messages WHERE message_id = ?", (cursor,)).fetchone()
                if cursor_row:
                    cursor_clause = "AND created_at < ?"
                    params.append(cursor_row["created_at"])
            params.append(limit + 1)
            rows = connection.execute(
                f"""
                SELECT * FROM messages
                WHERE conversation_id = ? {cursor_clause}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            messages = [self._public_message(connection, dict(row), user_id) for row in rows[:limit]]
        return {
            "messages": list(reversed(messages)),
            "next_cursor": rows[limit]["message_id"] if len(rows) > limit else None,
        }

    def send_message(
        self,
        sender_user_id: str,
        conversation_id: str,
        body: str,
        reply_to_message_id: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        conversation = self._require_conversation_access(sender_user_id, conversation_id)
        if self._is_announcement_channel(conversation) and not self._can_manage_conversation(sender_user_id, conversation):
            raise ChatAuthorizationError("Only authorized moderators may post announcements.")
        if not body.strip() and not attachments:
            raise ChatValidationError("Message body or attachment is required.")
        attachments = attachments or []
        with self._connect() as connection:
            for attachment in attachments:
                self._check_attachment_access(connection, sender_user_id, attachment)
            message = self._insert_message(connection, conversation_id, sender_user_id, body.strip(), reply_to_message_id=reply_to_message_id, attachments=attachments)
        return message

    def edit_message(self, actor_user_id: str, message_id: str, body: str) -> dict[str, Any]:
        message = self._message(message_id)
        if message is None:
            raise ChatValidationError("Message not found.")
        self._require_conversation_access(actor_user_id, str(message["conversation_id"]))
        if message["sender_user_id"] != actor_user_id:
            raise ChatAuthorizationError("Only the author can edit this message.")
        with self._connect() as connection:
            connection.execute("UPDATE messages SET body = ?, edited_at = ? WHERE message_id = ?", (body, _now(), message_id))
            row = connection.execute("SELECT * FROM messages WHERE message_id = ?", (message_id,)).fetchone()
            assert row is not None
            return self._public_message(connection, dict(row), actor_user_id)

    def delete_message(self, actor_user_id: str, message_id: str) -> dict[str, Any]:
        message = self._message(message_id)
        if message is None:
            raise ChatValidationError("Message not found.")
        conversation = self._require_conversation_access(actor_user_id, str(message["conversation_id"]))
        if message["sender_user_id"] != actor_user_id and not self._can_manage_conversation(actor_user_id, conversation):
            raise ChatAuthorizationError("User cannot delete this message.")
        now = _now()
        with self._connect() as connection:
            connection.execute("UPDATE messages SET deleted_at = ? WHERE message_id = ?", (now, message_id))
            if message["sender_user_id"] != actor_user_id:
                self._audit(connection, actor_user_id, "message.administratively_removed", "message", message_id, conversation["lab_id"], {"conversation_id": conversation["conversation_id"]})
            return {"message_id": message_id, "deleted_at": now}

    def mark_read(self, user_id: str, message_id: str) -> dict[str, Any]:
        message = self._message(message_id)
        if message is None:
            raise ChatValidationError("Message not found.")
        conversation_id = str(message["conversation_id"])
        self._require_conversation_access(user_id, conversation_id)
        with self._connect() as connection:
            connection.execute(
                "UPDATE conversation_members SET last_read_message_id = ? WHERE conversation_id = ? AND user_id = ? AND removed_at IS NULL",
                (message_id, conversation_id, user_id),
            )
        return {"message_id": message_id, "read": True}

    def unread_counts(self, user_id: str, lab_id: str = "lab:demo") -> dict[str, Any]:
        conversations = self.list_conversations(user_id, lab_id)
        counts = []
        with self._connect() as connection:
            for conversation in conversations:
                member = self._active_member_row(connection, conversation["conversation_id"], user_id)
                last_read = member["last_read_message_id"] if member else None
                params: list[Any] = [conversation["conversation_id"], user_id]
                clause = ""
                if last_read:
                    row = connection.execute("SELECT created_at FROM messages WHERE message_id = ?", (last_read,)).fetchone()
                    if row:
                        clause = "AND created_at > ?"
                        params.append(row["created_at"])
                count = connection.execute(
                    f"""
                    SELECT COUNT(*) AS count FROM messages
                    WHERE conversation_id = ? AND deleted_at IS NULL AND sender_user_id != ? {clause}
                    """,
                    params,
                ).fetchone()["count"]
                if count:
                    counts.append({"conversation_id": conversation["conversation_id"], "unread": count})
        return {"conversations": counts, "total_unread": sum(item["unread"] for item in counts)}

    def search(self, user_id: str, query: str, lab_id: str = "lab:demo") -> dict[str, Any]:
        query = query.strip()
        if not query:
            return {"query": query, "results": []}
        visible_ids = {conversation["conversation_id"] for conversation in self.list_conversations(user_id, lab_id)}
        if not visible_ids:
            return {"query": query, "results": []}
        placeholders = ",".join("?" for _ in visible_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT m.*, c.name AS conversation_name, c.conversation_type
                FROM messages m JOIN conversations c ON c.conversation_id = m.conversation_id
                WHERE m.conversation_id IN ({placeholders})
                  AND m.deleted_at IS NULL
                  AND LOWER(m.body) LIKE ?
                ORDER BY m.created_at DESC
                LIMIT 50
                """,
                [*visible_ids, f"%{query.lower()}%"],
            ).fetchall()
        return {
            "query": query,
            "results": [
                {
                    "conversation_id": row["conversation_id"],
                    "conversation_name": row["conversation_name"],
                    "conversation_type": row["conversation_type"],
                    "message_id": row["message_id"],
                    "snippet": _snippet(str(row["body"]), query),
                    "created_at": row["created_at"],
                }
                for row in rows
            ],
        }

    def can_access_conversation(self, user_id: str, conversation_id: str) -> ChatAccessDecision:
        conversation = self._conversation(conversation_id)
        if conversation is None:
            return ChatAccessDecision(False, "Conversation not found.")
        if conversation["archived_at"]:
            return ChatAccessDecision(False, "Conversation archived.")
        conversation_type = str(conversation["conversation_type"])
        if conversation_type in PRIVATE_CONVERSATION_TYPES:
            return ChatAccessDecision(self._is_current_member(user_id, conversation_id), "Current private conversation member required.")
        if not self.authz.membership(user_id, str(conversation["lab_id"])):
            return ChatAccessDecision(False, "Active lab membership required.")
        if conversation_type == "project_channel":
            # Project membership is represented by explicit conversation
            # membership until ResearchOS has a first-class project model.
            return ChatAccessDecision(self._is_current_member(user_id, conversation_id), "Project channel membership required.")
        return ChatAccessDecision(True, "Active lab channel member.")

    def _public_conversation(self, user_id: str, conversation: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            last_message = connection.execute(
                "SELECT message_id, sender_user_id, body, message_type, created_at, deleted_at FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 1",
                (conversation["conversation_id"],),
            ).fetchone()
            member_count = connection.execute(
                "SELECT COUNT(*) AS count FROM conversation_members WHERE conversation_id = ? AND removed_at IS NULL",
                (conversation["conversation_id"],),
            ).fetchone()["count"]
            current_member = self._active_member_row(connection, conversation["conversation_id"], user_id)
        payload = dict(conversation)
        payload["member_count"] = member_count
        payload["current_user_member_role"] = current_member["member_role"] if current_member else None
        payload["private"] = conversation["conversation_type"] in PRIVATE_CONVERSATION_TYPES
        payload["last_message"] = dict(last_message) if last_message else None
        return payload

    def _public_message(self, connection: sqlite3.Connection, message: dict[str, Any], user_id: str) -> dict[str, Any]:
        attachments = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM message_attachments WHERE message_id = ?",
                (message["message_id"],),
            ).fetchall()
        ]
        safe_attachments = []
        for attachment in attachments:
            try:
                self._check_attachment_access(connection, user_id, attachment)
                safe_attachments.append({**attachment, "metadata": json.loads(attachment.get("metadata_json") or "{}")})
            except ChatAuthorizationError:
                safe_attachments.append(
                    {
                        "attachment_id": attachment["attachment_id"],
                        "attachment_type": attachment["attachment_type"],
                        "display_name": attachment["display_name"],
                        "unavailable": True,
                    }
                )
        return {**message, "attachments": safe_attachments}

    def _conversation(self, conversation_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM conversations WHERE conversation_id = ?", (conversation_id,)).fetchone()
            return dict(row) if row else None

    def _message(self, message_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM messages WHERE message_id = ?", (message_id,)).fetchone()
            return dict(row) if row else None

    def _require_conversation_access(self, user_id: str, conversation_id: str) -> dict[str, Any]:
        decision = self.can_access_conversation(user_id, conversation_id)
        if not decision.allowed:
            raise ChatAuthorizationError(decision.reason)
        conversation = self._conversation(conversation_id)
        if conversation is None:
            raise ChatAuthorizationError("Conversation not found.")
        return conversation

    def _require_lab_member(self, user_id: str, lab_id: str) -> None:
        if not self.authz.membership(user_id, lab_id):
            raise ChatValidationError("User is not an active member of this lab.")

    def _is_current_member(self, user_id: str, conversation_id: str) -> bool:
        with self._connect() as connection:
            return self._active_member_row(connection, conversation_id, user_id) is not None

    def _active_member_row(self, connection: sqlite3.Connection, conversation_id: str, user_id: str) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT * FROM conversation_members
            WHERE conversation_id = ? AND user_id = ? AND removed_at IS NULL
            ORDER BY joined_at DESC LIMIT 1
            """,
            (conversation_id, user_id),
        ).fetchone()

    def _can_manage_conversation(self, user_id: str, conversation: dict[str, Any]) -> bool:
        if conversation["conversation_type"] not in PRIVATE_CONVERSATION_TYPES:
            access = self.authz.user_access(user_id, str(conversation["lab_id"]))
            if "lab.members.manage" in access["permissions"]:
                return True
        with self._connect() as connection:
            member = self._active_member_row(connection, conversation["conversation_id"], user_id)
        return bool(member and member["member_role"] in {"owner", "moderator"})

    def _can_manage_members(self, user_id: str, conversation: dict[str, Any]) -> bool:
        with self._connect() as connection:
            member = self._active_member_row(connection, conversation["conversation_id"], user_id)
        if member is None:
            return False
        policy = conversation["membership_policy"]
        if policy == "members_manage":
            return True
        if policy == "moderators_manage":
            return member["member_role"] in {"owner", "moderator"}
        if policy == "creator_manages":
            return conversation["created_by"] == user_id
        return False

    def _is_announcement_channel(self, conversation: dict[str, Any]) -> bool:
        return conversation["conversation_type"] == "lab_channel" and str(conversation["name"]).lower() == "announcements"

    def _has_messages(self, connection: sqlite3.Connection, conversation_id: str) -> bool:
        return bool(connection.execute("SELECT 1 FROM messages WHERE conversation_id = ? LIMIT 1", (conversation_id,)).fetchone())

    def _add_member_row(self, connection: sqlite3.Connection, conversation_id: str, user_id: str, member_role: str, added_by: str) -> None:
        if self._active_member_row(connection, conversation_id, user_id):
            return
        connection.execute(
            """
            INSERT INTO conversation_members
                (conversation_id, user_id, member_role, joined_at, added_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, user_id, member_role, _now(), added_by),
        )

    def _remove_member_row(self, connection: sqlite3.Connection, conversation_id: str, user_id: str, removed_by: str) -> None:
        connection.execute(
            """
            UPDATE conversation_members
            SET removed_at = CURRENT_TIMESTAMP, removed_by = ?
            WHERE conversation_id = ? AND user_id = ? AND removed_at IS NULL
            """,
            (removed_by, conversation_id, user_id),
        )

    def _membership_event(self, connection: sqlite3.Connection, conversation_id: str, event_type: str, actor_user_id: str, target_user_id: str) -> None:
        connection.execute(
            """
            INSERT INTO conversation_membership_events
                (event_id, conversation_id, event_type, actor_user_id, target_user_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (f"chat-event:{uuid.uuid4().hex}", conversation_id, event_type, actor_user_id, target_user_id),
        )

    def _system_message(self, connection: sqlite3.Connection, conversation_id: str, body: str) -> None:
        self._insert_message(connection, conversation_id, "system", body, message_type="system", attachments=[])

    def _insert_message(
        self,
        connection: sqlite3.Connection,
        conversation_id: str,
        sender_user_id: str,
        body: str,
        message_type: str = "user",
        reply_to_message_id: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        message_id = f"message:{uuid.uuid4().hex}"
        connection.execute(
            """
            INSERT INTO messages
                (message_id, conversation_id, sender_user_id, body, message_type, reply_to_message_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (message_id, conversation_id, sender_user_id, body, message_type, reply_to_message_id),
        )
        for attachment in attachments or []:
            connection.execute(
                """
                INSERT INTO message_attachments
                    (attachment_id, message_id, attachment_type, resource_id, display_name, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"attachment:{uuid.uuid4().hex}",
                    message_id,
                    attachment.get("attachment_type", "custom"),
                    attachment.get("resource_id"),
                    attachment.get("display_name") or attachment.get("resource_id") or "Attachment",
                    json.dumps(attachment.get("metadata") or {}),
                ),
            )
        row = connection.execute("SELECT * FROM messages WHERE message_id = ?", (message_id,)).fetchone()
        assert row is not None
        return self._public_message(connection, dict(row), sender_user_id)

    def _check_attachment_access(self, connection: sqlite3.Connection, user_id: str, attachment: dict[str, Any]) -> None:
        attachment_type = str(attachment.get("attachment_type") or "")
        resource_id = attachment.get("resource_id")
        if attachment_type == "notebook" and resource_id:
            if not self.authz.can_user(user_id, "view", "notebook", str(resource_id)).allowed:
                raise ChatAuthorizationError("User cannot access attached notebook.")
        if attachment_type == "entry" and resource_id:
            try:
                self.authz.entry_detail(user_id, str(resource_id))
            except PermissionError as exc:
                raise ChatAuthorizationError("User cannot access attached notebook entry.") from exc
        if attachment_type == "experiment" and resource_id:
            exists = connection.execute(
                "SELECT 1 FROM experiments WHERE id = ? OR experiment_id = ? LIMIT 1",
                (resource_id, resource_id),
            ).fetchone()
            if not exists and str(resource_id).startswith("experiment:"):
                raise ChatAuthorizationError("Attached experiment is unavailable.")

    def _display_name(self, connection: sqlite3.Connection, user_id: str) -> str:
        if user_id == "system":
            return "System"
        row = connection.execute("SELECT display_name FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return str(row["display_name"]) if row else user_id

    def _audit(
        self,
        connection: sqlite3.Connection,
        actor_user_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        lab_id: str,
        metadata: dict[str, Any],
    ) -> None:
        # Never write private message bodies to audit logs.
        connection.execute(
            """
            INSERT INTO audit_events
                (audit_id, actor_user_id, action, resource_type, resource_id, lab_id, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (f"audit:{uuid.uuid4().hex}", actor_user_id, action, resource_type, resource_id, lab_id, json.dumps(metadata)),
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _snippet(body: str, query: str) -> str:
    lowered = body.lower()
    index = lowered.find(query.lower())
    if index < 0:
        return body[:160]
    start = max(0, index - 45)
    end = min(len(body), index + len(query) + 90)
    prefix = "..." if start else ""
    suffix = "..." if end < len(body) else ""
    return f"{prefix}{body[start:end]}{suffix}"
