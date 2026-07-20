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
                """
            )

    def list_provider_configs(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM ai_provider_configs ORDER BY is_preferred DESC, display_name ASC"
            ).fetchall()
        return [self._provider_config_payload(row) for row in rows]

    def upsert_provider_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        provider_config_id = str(payload.get("provider_config_id") or f"ai-provider:{uuid.uuid4().hex[:16]}")
        provider = str(payload.get("provider") or "").strip()
        display_name = str(payload.get("display_name") or provider or "AI Provider").strip()
        if not provider:
            raise ValueError("Provider is required.")
        enabled = 1 if payload.get("enabled", True) else 0
        preferred = 1 if payload.get("is_preferred") else 0
        with self._connect() as connection:
            if preferred:
                connection.execute("UPDATE ai_provider_configs SET is_preferred = 0")
            connection.execute(
                """
                INSERT INTO ai_provider_configs
                    (provider_config_id, provider, display_name, enabled, endpoint, default_model, api_key_secret, is_preferred)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_config_id) DO UPDATE SET
                    provider = excluded.provider,
                    display_name = excluded.display_name,
                    enabled = excluded.enabled,
                    endpoint = excluded.endpoint,
                    default_model = excluded.default_model,
                    api_key_secret = COALESCE(excluded.api_key_secret, ai_provider_configs.api_key_secret),
                    is_preferred = excluded.is_preferred,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    provider_config_id,
                    provider,
                    display_name,
                    enabled,
                    payload.get("endpoint"),
                    payload.get("default_model"),
                    payload.get("api_key"),
                    preferred,
                ),
            )
            row = connection.execute(
                "SELECT * FROM ai_provider_configs WHERE provider_config_id = ?",
                (provider_config_id,),
            ).fetchone()
        assert row is not None
        return self._provider_config_payload(row)

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
                    (conversation_id, actor_user_id, provider_config_id, skill_id, context_ids_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (conversation_id, actor_user_id, provider_config_id, skill_id, json.dumps(context_ids or [])),
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
        payload = dict(conversation)
        payload["context_ids"] = json.loads(payload.pop("context_ids_json") or "[]")
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
