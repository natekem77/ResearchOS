"""SQLite storage for ResearchOS documents and chunks."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.experiments import Experiment
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

                CREATE TABLE IF NOT EXISTS experiments (
                    id TEXT PRIMARY KEY,
                    source_document_id TEXT NOT NULL,
                    source_provider TEXT NOT NULL,
                    title TEXT NOT NULL,
                    experiment_id TEXT,
                    date TEXT,
                    researcher TEXT,
                    cell_line TEXT,
                    organoid_batch TEXT,
                    compounds_json TEXT NOT NULL DEFAULT '[]',
                    treatments_json TEXT NOT NULL DEFAULT '[]',
                    concentrations_json TEXT NOT NULL DEFAULT '[]',
                    time_points_json TEXT NOT NULL DEFAULT '[]',
                    markers_json TEXT NOT NULL DEFAULT '[]',
                    antibodies_json TEXT NOT NULL DEFAULT '[]',
                    imaging_methods_json TEXT NOT NULL DEFAULT '[]',
                    sequencing_json TEXT NOT NULL DEFAULT '[]',
                    notes TEXT,
                    conclusions TEXT,
                    extracted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(source_document_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_experiments_source_document_id
                    ON experiments(source_document_id);
                CREATE INDEX IF NOT EXISTS idx_experiments_date ON experiments(date);

                CREATE TABLE IF NOT EXISTS pending_entries (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    experiment_id TEXT,
                    template TEXT NOT NULL,
                    structured_json TEXT NOT NULL DEFAULT '{}',
                    markdown TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_pending_entries_status
                    ON pending_entries(status);
                CREATE INDEX IF NOT EXISTS idx_pending_entries_updated_at
                    ON pending_entries(updated_at);

                CREATE TABLE IF NOT EXISTS assets (
                    asset_id TEXT PRIMARY KEY,
                    asset_type TEXT NOT NULL,
                    experiment_id TEXT,
                    title TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    path TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_assets_type
                    ON assets(asset_type);
                CREATE INDEX IF NOT EXISTS idx_assets_experiment_id
                    ON assets(experiment_id);
                CREATE INDEX IF NOT EXISTS idx_assets_provider
                    ON assets(provider);
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

    def upsert_experiment(self, experiment: Experiment) -> None:
        """Store or update an extracted experiment."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO experiments (
                    id, source_document_id, source_provider, title, experiment_id, date,
                    researcher, cell_line, organoid_batch, compounds_json,
                    treatments_json, concentrations_json, time_points_json, markers_json,
                    antibodies_json, imaging_methods_json, sequencing_json, notes, conclusions
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    source_document_id = excluded.source_document_id,
                    source_provider = excluded.source_provider,
                    title = excluded.title,
                    experiment_id = excluded.experiment_id,
                    date = excluded.date,
                    researcher = excluded.researcher,
                    cell_line = excluded.cell_line,
                    organoid_batch = excluded.organoid_batch,
                    compounds_json = excluded.compounds_json,
                    treatments_json = excluded.treatments_json,
                    concentrations_json = excluded.concentrations_json,
                    time_points_json = excluded.time_points_json,
                    markers_json = excluded.markers_json,
                    antibodies_json = excluded.antibodies_json,
                    imaging_methods_json = excluded.imaging_methods_json,
                    sequencing_json = excluded.sequencing_json,
                    notes = excluded.notes,
                    conclusions = excluded.conclusions,
                    extracted_at = CURRENT_TIMESTAMP
                """,
                (
                    experiment.id,
                    experiment.source_document_id,
                    experiment.source_provider,
                    experiment.title,
                    experiment.experiment_id,
                    experiment.date,
                    experiment.researcher,
                    experiment.cell_line,
                    experiment.organoid_batch,
                    json.dumps(experiment.compounds),
                    json.dumps(experiment.treatments),
                    json.dumps(experiment.concentrations),
                    json.dumps(experiment.time_points),
                    json.dumps(experiment.markers),
                    json.dumps(experiment.antibodies),
                    json.dumps(experiment.imaging_methods),
                    json.dumps(experiment.sequencing),
                    experiment.notes,
                    experiment.conclusions,
                ),
            )

    def list_experiments(self) -> list[dict[str, Any]]:
        """Return all extracted experiments."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM experiments
                ORDER BY COALESCE(date, extracted_at) DESC, title ASC
                """
            ).fetchall()

        return [self._experiment_row_to_dict(row) for row in rows]

    def get_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        """Return one extracted experiment."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM experiments WHERE id = ?",
                (experiment_id,),
            ).fetchone()

        if row is None:
            return None

        return self._experiment_row_to_dict(row)

    def get_all_research_documents(self) -> list[ResearchDocument]:
        """Return stored documents as ResearchDocument objects for extraction."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, provider, source_id, title, content, source_path, source_url,
                       created_at, updated_at, metadata_json
                FROM documents
                ORDER BY ingested_at DESC, title ASC
                """
            ).fetchall()

        documents: list[ResearchDocument] = []
        for row in rows:
            record = dict(row)
            documents.append(
                ResearchDocument(
                    id=record["id"],
                    provider=record["provider"],
                    source_id=record["source_id"],
                    title=record["title"],
                    content=record["content"],
                    source_path=record["source_path"],
                    source_url=record["source_url"],
                    created_at=record["created_at"],
                    updated_at=record["updated_at"],
                    metadata=json.loads(record["metadata_json"] or "{}"),
                )
            )

        return documents

    def get_research_document(self, document_id: str) -> ResearchDocument | None:
        """Return one stored document as a ResearchDocument for extraction."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, provider, source_id, title, content, source_path, source_url,
                       created_at, updated_at, metadata_json
                FROM documents
                WHERE id = ?
                """,
                (document_id,),
            ).fetchone()

        if row is None:
            return None

        record = dict(row)
        return ResearchDocument(
            id=record["id"],
            provider=record["provider"],
            source_id=record["source_id"],
            title=record["title"],
            content=record["content"],
            source_path=record["source_path"],
            source_url=record["source_url"],
            created_at=record["created_at"],
            updated_at=record["updated_at"],
            metadata=json.loads(record["metadata_json"] or "{}"),
        )

    def delete_documents_by_source_prefix(self, source_prefix: str) -> int:
        """Delete documents, chunks, and experiments under a trusted source prefix.

        This is used by the local demo reset endpoint. It intentionally requires
        a concrete source path prefix so it cannot wipe arbitrary stored data.
        """

        normalized_prefix = str(Path(source_prefix).resolve())
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id
                FROM documents
                WHERE source_path IS NOT NULL
                  AND (source_path = ? OR source_path LIKE ?)
                """,
                (normalized_prefix, f"{normalized_prefix}/%"),
            ).fetchall()
            document_ids = [row["id"] for row in rows]

            for document_id in document_ids:
                connection.execute(
                    "DELETE FROM experiments WHERE source_document_id = ?",
                    (document_id,),
                )
                connection.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
                connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))

        return len(document_ids)

    def save_pending_entry(
        self,
        title: str,
        experiment_id: str | None,
        template: str,
        structured: dict[str, Any],
        markdown: str,
        status: str = "draft",
        entry_id: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a local pending notebook entry draft."""

        resolved_id = entry_id or f"entry:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT created_at FROM pending_entries WHERE id = ?",
                (resolved_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO pending_entries (
                        id, title, experiment_id, template, structured_json,
                        markdown, status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        resolved_id,
                        title,
                        experiment_id,
                        template,
                        json.dumps(structured, sort_keys=True),
                        markdown,
                        status,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE pending_entries
                    SET title = ?,
                        experiment_id = ?,
                        template = ?,
                        structured_json = ?,
                        markdown = ?,
                        status = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        title,
                        experiment_id,
                        template,
                        json.dumps(structured, sort_keys=True),
                        markdown,
                        status,
                        resolved_id,
                    ),
                )

        saved = self.get_pending_entry(resolved_id)
        if saved is None:
            raise RuntimeError(f"Pending entry was not saved: {resolved_id}")
        return saved

    def list_pending_entries(self) -> list[dict[str, Any]]:
        """Return pending notebook-entry drafts."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, title, experiment_id, template, status, created_at, updated_at
                FROM pending_entries
                ORDER BY updated_at DESC, created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_pending_entry(self, entry_id: str) -> dict[str, Any] | None:
        """Return one pending notebook-entry draft."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM pending_entries WHERE id = ?",
                (entry_id,),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["structured"] = json.loads(record.pop("structured_json") or "{}")
        return record

    def delete_pending_entry(self, entry_id: str) -> bool:
        """Delete one pending notebook-entry draft."""

        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM pending_entries WHERE id = ?", (entry_id,))
        return cursor.rowcount > 0

    def register_asset(
        self,
        asset_type: str,
        experiment_id: str | None,
        title: str,
        filename: str,
        provider: str,
        path: str,
        metadata: dict[str, Any] | None = None,
        asset_id: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a local research asset registration.

        Assets are metadata records only at this milestone. ResearchOS records
        where a file came from and how it links to experiments without parsing
        provider-specific formats such as GraphPad, microscopy, or sequencing.
        """

        resolved_id = asset_id or f"asset:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT created_at FROM assets WHERE asset_id = ?",
                (resolved_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO assets (
                        asset_id, asset_type, experiment_id, title, filename,
                        provider, path, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        resolved_id,
                        asset_type,
                        experiment_id,
                        title,
                        filename,
                        provider,
                        path,
                        json.dumps(metadata or {}, sort_keys=True),
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE assets
                    SET asset_type = ?,
                        experiment_id = ?,
                        title = ?,
                        filename = ?,
                        provider = ?,
                        path = ?,
                        metadata_json = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE asset_id = ?
                    """,
                    (
                        asset_type,
                        experiment_id,
                        title,
                        filename,
                        provider,
                        path,
                        json.dumps(metadata or {}, sort_keys=True),
                        resolved_id,
                    ),
                )

        saved = self.get_asset(resolved_id)
        if saved is None:
            raise RuntimeError(f"Asset was not saved: {resolved_id}")
        return saved

    def list_assets(
        self,
        asset_type: str | None = None,
        query: str | None = None,
        experiment_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return registered research assets, optionally filtered."""

        clauses: list[str] = []
        values: list[str] = []
        if asset_type:
            clauses.append("asset_type = ?")
            values.append(asset_type)
        if experiment_id:
            clauses.append("experiment_id = ?")
            values.append(experiment_id)
        if query:
            clauses.append("(LOWER(title) LIKE ? OR LOWER(filename) LIKE ? OR LOWER(path) LIKE ?)")
            needle = f"%{query.lower()}%"
            values.extend([needle, needle, needle])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM assets
                {where}
                ORDER BY updated_at DESC, created_at DESC, title ASC
                """,
                values,
            ).fetchall()
        return [self._asset_row_to_dict(row) for row in rows]

    def get_asset(self, asset_id: str) -> dict[str, Any] | None:
        """Return one registered research asset."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM assets WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
        if row is None:
            return None
        return self._asset_row_to_dict(row)

    def link_asset(self, asset_id: str, experiment_id: str | None) -> dict[str, Any] | None:
        """Attach an asset to an experiment, or clear the link with null."""

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE assets
                SET experiment_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE asset_id = ?
                """,
                (experiment_id, asset_id),
            )
        if cursor.rowcount == 0:
            return None
        return self.get_asset(asset_id)

    def delete_asset(self, asset_id: str) -> bool:
        """Delete one local asset registration."""

        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM assets WHERE asset_id = ?", (asset_id,))
        return cursor.rowcount > 0

    def _experiment_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Deserialize an experiment row into API-ready fields."""

        record = dict(row)
        for key in [
            "compounds",
            "treatments",
            "concentrations",
            "time_points",
            "markers",
            "antibodies",
            "imaging_methods",
            "sequencing",
        ]:
            record[key] = json.loads(record.pop(f"{key}_json") or "[]")
        return record

    def _asset_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Deserialize an asset row into API-ready fields."""

        record = dict(row)
        record["metadata"] = json.loads(record.pop("metadata_json") or "{}")
        return record
