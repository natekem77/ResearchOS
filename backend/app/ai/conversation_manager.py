"""Persistent AI provider settings and conversations."""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from app.ai.models import AIProviderConfig
from app.config import Settings, get_settings
from app.storage import SQLiteStore


class ConversationManager:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.store = SQLiteStore(self.settings)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return self.store._connect()

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS ai_provider_configs (
                    provider_config_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    endpoint TEXT,
                    default_model TEXT,
                    api_key_secret TEXT,
                    is_preferred INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS ai_conversations (
                    conversation_id TEXT PRIMARY KEY,
                    actor_user_id TEXT NOT NULL,
                    provider_config_id TEXT,
                    skill_id TEXT NOT NULL,
                    title TEXT,
                    context_ids_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS ai_messages (
                    message_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS mobile_navigation_preferences (
                    user_id TEXT PRIMARY KEY,
                    destination_ids_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            self._ensure_column(connection, "ai_conversations", "title", "TEXT")
            self._repair_provider_config_duplicates(connection)

    def list_provider_configs(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            self._repair_provider_config_duplicates(connection)
            rows = connection.execute(
                "SELECT * FROM ai_provider_configs ORDER BY is_preferred DESC, display_name ASC"
            ).fetchall()
        return [self._provider_config_payload(row) for row in rows]

    def upsert_provider_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        provider = str(payload.get("provider") or "").strip()
        display_name = str(payload.get("display_name") or provider or "AI Provider").strip()
        if not provider:
            raise ValueError("Provider is required.")
        endpoint = _normal_text(payload.get("endpoint"))
        default_model = _normal_text(payload.get("default_model"))
        provider_config_id = _normal_text(payload.get("provider_config_id"))
        enabled = 1 if payload.get("enabled", True) else 0
        preferred = 1 if payload.get("is_preferred") else 0
        api_key = payload.get("api_key")
        api_key_secret = str(api_key) if api_key is not None and str(api_key).strip() else None
        remove_api_key = bool(payload.get("remove_api_key"))
        with self._connect() as connection:
            self._repair_provider_config_duplicates(connection)
            if not provider_config_id:
                existing = self._find_provider_config(
                    connection,
                    provider=provider,
                    endpoint=endpoint,
                    display_name=display_name,
                )
                provider_config_id = (
                    str(existing["provider_config_id"])
                    if existing is not None
                    else self._stable_provider_config_id(provider, endpoint, display_name)
                )
            if preferred:
                connection.execute("UPDATE ai_provider_configs SET is_preferred = 0")
            if remove_api_key:
                api_key_sql = "NULL"
            elif api_key_secret is not None:
                api_key_sql = "excluded.api_key_secret"
            else:
                api_key_sql = "ai_provider_configs.api_key_secret"
            connection.execute(
                f"""
                INSERT INTO ai_provider_configs
                    (provider_config_id, provider, display_name, enabled, endpoint, default_model, api_key_secret, is_preferred)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_config_id) DO UPDATE SET
                    provider = excluded.provider,
                    display_name = excluded.display_name,
                    enabled = excluded.enabled,
                    endpoint = excluded.endpoint,
                    default_model = excluded.default_model,
                    api_key_secret = {api_key_sql},
                    is_preferred = excluded.is_preferred,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    provider_config_id,
                    provider,
                    display_name,
                    enabled,
                    endpoint,
                    default_model,
                    api_key_secret,
                    preferred,
                ),
            )
            row = connection.execute(
                "SELECT * FROM ai_provider_configs WHERE provider_config_id = ?",
                (provider_config_id,),
            ).fetchone()
        assert row is not None
        return self._provider_config_payload(row)

    def set_preferred_provider_config(self, provider_config_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM ai_provider_configs WHERE provider_config_id = ?",
                (provider_config_id,),
            ).fetchone()
            if row is None:
                raise ValueError("AI provider configuration not found.")
            connection.execute("UPDATE ai_provider_configs SET is_preferred = 0")
            connection.execute(
                """
                UPDATE ai_provider_configs
                SET is_preferred = 1, enabled = 1, updated_at = CURRENT_TIMESTAMP
                WHERE provider_config_id = ?
                """,
                (provider_config_id,),
            )
            row = connection.execute(
                "SELECT * FROM ai_provider_configs WHERE provider_config_id = ?",
                (provider_config_id,),
            ).fetchone()
        assert row is not None
        return self._provider_config_payload(row)

    def provider_config_with_secret(self, provider_config_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM ai_provider_configs WHERE provider_config_id = ?",
                (provider_config_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def preferred_provider_config(self) -> dict[str, Any] | None:
        configs = self.list_provider_configs()
        return next((item for item in configs if item.get("enabled") and item.get("is_preferred")), None) or next(
            (item for item in configs if item.get("enabled")), None
        )

    def create_conversation(self, actor_user_id: str, skill_id: str, provider_config_id: str | None, context_ids: list[str] | None = None) -> dict[str, Any]:
        conversation_id = f"ai-conversation:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ai_conversations
                    (conversation_id, actor_user_id, provider_config_id, skill_id, title, context_ids_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    actor_user_id,
                    provider_config_id,
                    skill_id,
                    "New Ask Mundi chat",
                    json.dumps(context_ids or []),
                ),
            )
        return self.get_conversation(actor_user_id, conversation_id)

    def list_conversations(self, actor_user_id: str, include_archived: bool = False) -> list[dict[str, Any]]:
        with self._connect() as connection:
            status_clause = "" if include_archived else "AND status != 'archived'"
            rows = connection.execute(
                f"""
                SELECT *
                FROM ai_conversations
                WHERE actor_user_id = ? {status_clause}
                ORDER BY updated_at DESC, created_at DESC
                """,
                (actor_user_id,),
            ).fetchall()
        return [self._conversation_payload(row, include_messages=False) for row in rows]

    def update_conversation(
        self,
        actor_user_id: str,
        conversation_id: str,
        *,
        title: str | None = None,
        status: str | None = None,
        context_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM ai_conversations WHERE conversation_id = ? AND actor_user_id = ?",
                (conversation_id, actor_user_id),
            ).fetchone()
            if row is None:
                raise ValueError("AI conversation not found.")
            if title is not None:
                connection.execute(
                    "UPDATE ai_conversations SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE conversation_id = ?",
                    (title.strip() or "Ask Mundi chat", conversation_id),
                )
            if status is not None:
                connection.execute(
                    "UPDATE ai_conversations SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE conversation_id = ?",
                    (status, conversation_id),
                )
            if context_ids is not None:
                connection.execute(
                    "UPDATE ai_conversations SET context_ids_json = ?, updated_at = CURRENT_TIMESTAMP WHERE conversation_id = ?",
                    (json.dumps(context_ids), conversation_id),
                )
        return self.get_conversation(actor_user_id, conversation_id)

    def append_message(self, conversation_id: str, role: str, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        message_id = f"ai-message:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ai_messages (message_id, conversation_id, role, content, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (message_id, conversation_id, role, content, json.dumps(metadata or {})),
            )
            connection.execute(
                "UPDATE ai_conversations SET updated_at = CURRENT_TIMESTAMP WHERE conversation_id = ?",
                (conversation_id,),
            )
        return {"message_id": message_id, "conversation_id": conversation_id, "role": role, "content": content, "metadata": metadata or {}}

    def get_conversation(self, actor_user_id: str, conversation_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            conversation = connection.execute(
                "SELECT * FROM ai_conversations WHERE conversation_id = ? AND actor_user_id = ?",
                (conversation_id, actor_user_id),
            ).fetchone()
            if conversation is None:
                raise ValueError("AI conversation not found.")
            messages = connection.execute(
                "SELECT * FROM ai_messages WHERE conversation_id = ? ORDER BY rowid ASC",
                (conversation_id,),
            ).fetchall()
        payload = self._conversation_payload(conversation, include_messages=False)
        payload["messages"] = [
            {
                "message_id": row["message_id"],
                "role": row["role"],
                "content": row["content"],
                "metadata": json.loads(row["metadata_json"] or "{}"),
                "created_at": row["created_at"],
            }
            for row in messages
        ]
        return payload

    def _conversation_payload(self, row: sqlite3.Row, *, include_messages: bool) -> dict[str, Any]:
        payload = dict(row)
        payload["context_ids"] = json.loads(payload.pop("context_ids_json") or "[]")
        if not payload.get("title"):
            payload["title"] = "Ask Mundi chat"
        if not include_messages:
            payload["message_count"] = self._message_count(str(payload["conversation_id"]))
        return payload

    def _message_count(self, conversation_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM ai_messages WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        return int(row["count"] if row is not None else 0)

    def _ensure_column(
        self,
        connection: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        existing = {
            str(row["name"])
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _provider_config_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "provider_config_id": row["provider_config_id"],
            "provider": row["provider"],
            "display_name": row["display_name"],
            "enabled": bool(row["enabled"]),
            "endpoint": row["endpoint"],
            "default_model": row["default_model"],
            "api_key_configured": bool(row["api_key_secret"]),
            "is_preferred": bool(row["is_preferred"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def get_navigation_preferences(
        self,
        user_id: str,
        available_ids: list[str],
        default_ids: list[str],
    ) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM mobile_navigation_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        configured = json.loads(row["destination_ids_json"]) if row is not None else default_ids
        destination_ids = _safe_navigation_ids(configured, available_ids, default_ids)
        return {
            "user_id": user_id,
            "destination_ids": destination_ids,
            "available_destinations": available_ids,
        }

    def save_navigation_preferences(
        self,
        user_id: str,
        destination_ids: list[str],
        available_ids: list[str],
    ) -> dict[str, Any]:
        if len(destination_ids) != 5:
            raise ValueError("Exactly five navigation destinations are required.")
        if len(set(destination_ids)) != len(destination_ids):
            raise ValueError("Navigation destinations must not contain duplicates.")
        invalid = [item for item in destination_ids if item not in available_ids]
        if invalid:
            raise ValueError(f"Unavailable navigation destinations: {', '.join(invalid)}")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO mobile_navigation_preferences (user_id, destination_ids_json)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    destination_ids_json = excluded.destination_ids_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, json.dumps(destination_ids)),
            )
        return self.get_navigation_preferences(user_id, available_ids, destination_ids)

    def _find_provider_config(
        self,
        connection: sqlite3.Connection,
        *,
        provider: str,
        endpoint: str | None,
        display_name: str,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT *
            FROM ai_provider_configs
            WHERE lower(provider) = lower(?)
              AND lower(COALESCE(endpoint, '')) = lower(?)
              AND lower(display_name) = lower(?)
            ORDER BY is_preferred DESC, api_key_secret IS NOT NULL DESC, updated_at DESC, created_at DESC
            LIMIT 1
            """,
            (provider, endpoint or "", display_name),
        ).fetchone()

    def _stable_provider_config_id(
        self,
        provider: str,
        endpoint: str | None,
        display_name: str,
    ) -> str:
        import hashlib

        identity = "|".join(
            [
                provider.strip().lower(),
                (endpoint or "").strip().lower(),
                display_name.strip().lower(),
            ]
        )
        return f"ai-provider:{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:16]}"

    def _repair_provider_config_duplicates(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT * FROM ai_provider_configs ORDER BY created_at ASC, updated_at ASC"
        ).fetchall()
        groups: dict[tuple[str, str, str], list[sqlite3.Row]] = {}
        for row in rows:
            key = (
                str(row["provider"] or "").strip().lower(),
                str(row["endpoint"] or "").strip().lower(),
                str(row["display_name"] or "").strip().lower(),
            )
            groups.setdefault(key, []).append(row)

        for duplicate_rows in groups.values():
            if len(duplicate_rows) < 2:
                continue
            keep = sorted(
                duplicate_rows,
                key=lambda row: (
                    1 if row["is_preferred"] else 0,
                    1 if row["api_key_secret"] else 0,
                    str(row["updated_at"] or ""),
                    str(row["created_at"] or ""),
                ),
                reverse=True,
            )[0]
            secret = keep["api_key_secret"]
            if not secret:
                secret_row = next((row for row in duplicate_rows if row["api_key_secret"]), None)
                secret = secret_row["api_key_secret"] if secret_row is not None else None
            preferred = 1 if any(row["is_preferred"] for row in duplicate_rows) else 0
            connection.execute(
                """
                UPDATE ai_provider_configs
                SET api_key_secret = COALESCE(?, api_key_secret),
                    is_preferred = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE provider_config_id = ?
                """,
                (secret, preferred, keep["provider_config_id"]),
            )
            connection.execute(
                """
                DELETE FROM ai_provider_configs
                WHERE provider_config_id IN ({})
                """.format(",".join("?" for _ in duplicate_rows if _["provider_config_id"] != keep["provider_config_id"])),
                [
                    row["provider_config_id"]
                    for row in duplicate_rows
                    if row["provider_config_id"] != keep["provider_config_id"]
                ],
            )

        preferred_rows = connection.execute(
            """
            SELECT provider_config_id
            FROM ai_provider_configs
            WHERE is_preferred = 1
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()
        if len(preferred_rows) > 1:
            keep_id = preferred_rows[0]["provider_config_id"]
            connection.execute(
                "UPDATE ai_provider_configs SET is_preferred = 0 WHERE provider_config_id != ?",
                (keep_id,),
            )


def _normal_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_navigation_ids(
    configured: list[Any],
    available_ids: list[str],
    default_ids: list[str],
) -> list[str]:
    result: list[str] = []
    for item in configured:
        destination_id = str(item)
        if destination_id in available_ids and destination_id not in result:
            result.append(destination_id)
    for item in default_ids:
        if len(result) >= 5:
            break
        if item in available_ids and item not in result:
            result.append(item)
    for item in available_ids:
        if len(result) >= 5:
            break
        if item not in result:
            result.append(item)
    return result[:5]
