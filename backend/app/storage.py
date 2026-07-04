"""SQLite storage for ResearchOS documents and chunks."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.research_document import DocumentChunk, ResearchDocument

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _database_path(settings: Settings) -> Path:
    """Resolve the configured SQLite database path."""

    database_url = settings.database_url
    if not database_url.startswith("sqlite:///"):
        raise ValueError("Only sqlite:/// database URLs are supported in this milestone.")

    raw_path = database_url.removeprefix("sqlite:///")
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path

    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class SQLiteStore:
    """Small SQLite repository for provider-agnostic documents and chunks."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.path = _database_path(self.settings)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        """Create tables if they do not already exist."""

        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_path TEXT,
                    source_url TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    ingested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    token_estimate INTEGER NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_documents_provider ON documents(provider);
                CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);
                """
            )

    def upsert_document(self, document: ResearchDocument, chunks: list[DocumentChunk]) -> None:
        """Store one document and replace its chunks atomically."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO documents (
                    id, provider, source_id, title, content, source_path, source_url,
                    created_at, updated_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    provider = excluded.provider,
                    source_id = excluded.source_id,
                    title = excluded.title,
                    content = excluded.content,
                    source_path = excluded.source_path,
                    source_url = excluded.source_url,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    metadata_json = excluded.metadata_json,
                    ingested_at = CURRENT_TIMESTAMP
                """,
                (
                    document.id,
                    document.provider,
                    document.source_id,
                    document.title,
                    document.content,
                    document.source_path,
                    document.source_url,
                    document.created_at,
                    document.updated_at,
                    json.dumps(document.metadata, sort_keys=True),
                ),
            )
            connection.execute("DELETE FROM chunks WHERE document_id = ?", (document.id,))
            connection.executemany(
                """
                INSERT INTO chunks (id, document_id, chunk_index, text, token_estimate)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.id,
                        chunk.document_id,
                        chunk.chunk_index,
                        chunk.text,
                        chunk.token_estimate,
                    )
                    for chunk in chunks
                ],
            )

    def list_documents(self) -> list[dict[str, Any]]:
        """Return stored document summaries."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, provider, source_id, title, source_path, source_url,
                       created_at, updated_at, ingested_at
                FROM documents
                ORDER BY ingested_at DESC, title ASC
                """
            ).fetchall()

        return [dict(row) for row in rows]

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        """Return one stored document with metadata and chunk count."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, provider, source_id, title, content, source_path, source_url,
                       created_at, updated_at, metadata_json, ingested_at
                FROM documents
                WHERE id = ?
                """,
                (document_id,),
            ).fetchone()
            if row is None:
                return None

            chunk_count = connection.execute(
                "SELECT COUNT(*) AS count FROM chunks WHERE document_id = ?",
                (document_id,),
            ).fetchone()["count"]

        document = dict(row)
        document["metadata"] = json.loads(document.pop("metadata_json") or "{}")
        document["chunk_count"] = chunk_count
        return document

    def keyword_search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search documents and chunks with SQLite LIKE as a no-AI fallback."""

        terms = [term.lower() for term in re.findall(r"\w+", query) if term.strip()]
        if not terms:
            return []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    d.id AS document_id,
                    d.title AS title,
                    d.provider AS provider,
                    c.id AS chunk_id,
                    c.text AS snippet
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                """
            ).fetchall()

        scored_results: list[dict[str, Any]] = []
        for row in rows:
            result = dict(row)
            haystack = f"{result['title']} {result['snippet']}".lower()
            score = sum(haystack.count(term) for term in terms)
            if score > 0:
                scored_results.append(result | {"score": float(score), "source": "keyword"})

        scored_results.sort(key=lambda result: (-float(result["score"]), result["title"]))
        return scored_results[:limit]
