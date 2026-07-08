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

                CREATE TABLE IF NOT EXISTS experiment_sessions (
                    session_id TEXT PRIMARY KEY,
                    experiment_id TEXT,
                    start_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    end_time TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    notes TEXT,
                    voice_transcripts_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_experiment_sessions_status
                    ON experiment_sessions(status);
                CREATE INDEX IF NOT EXISTS idx_experiment_sessions_experiment_id
                    ON experiment_sessions(experiment_id);
                CREATE INDEX IF NOT EXISTS idx_experiment_sessions_start_time
                    ON experiment_sessions(start_time);

                CREATE TABLE IF NOT EXISTS session_events (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT,
                    asset_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES experiment_sessions(session_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_session_events_session_id
                    ON session_events(session_id);
                CREATE INDEX IF NOT EXISTS idx_session_events_created_at
                    ON session_events(created_at);

                CREATE TABLE IF NOT EXISTS experiment_lifecycles (
                    experiment_id TEXT PRIMARY KEY,
                    current_stage TEXT NOT NULL DEFAULT 'Planning',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS experiment_lifecycle_events (
                    lifecycle_event_id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    from_stage TEXT,
                    to_stage TEXT NOT NULL,
                    reason TEXT,
                    actor TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_experiment_lifecycle_events_experiment_id
                    ON experiment_lifecycle_events(experiment_id);
                CREATE INDEX IF NOT EXISTS idx_experiment_lifecycle_events_created_at
                    ON experiment_lifecycle_events(created_at);

                CREATE TABLE IF NOT EXISTS workflow_states (
                    workflow_id TEXT PRIMARY KEY,
                    workflow_type TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    current_stage TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS workflow_history (
                    history_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    from_stage TEXT,
                    to_stage TEXT NOT NULL,
                    reason TEXT,
                    actor TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(workflow_id) REFERENCES workflow_states(workflow_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS workflow_notes (
                    note_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    note TEXT NOT NULL,
                    actor TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(workflow_id) REFERENCES workflow_states(workflow_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_workflow_states_type_subject
                    ON workflow_states(workflow_type, subject_id);
                CREATE INDEX IF NOT EXISTS idx_workflow_states_stage
                    ON workflow_states(workflow_type, current_stage);
                CREATE INDEX IF NOT EXISTS idx_workflow_history_workflow_id
                    ON workflow_history(workflow_id);
                CREATE INDEX IF NOT EXISTS idx_workflow_notes_workflow_id
                    ON workflow_notes(workflow_id);

                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    auth_provider TEXT NOT NULL DEFAULT 'local_dev',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_login TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_users_email
                    ON users(email);
                CREATE INDEX IF NOT EXISTS idx_users_role
                    ON users(role);
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

    def find_experiment_by_reference(self, experiment_reference: str) -> dict[str, Any] | None:
        """Return an experiment by internal ID or human experiment ID."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM experiments
                WHERE id = ? OR experiment_id = ?
                ORDER BY extracted_at DESC
                LIMIT 1
                """,
                (experiment_reference, experiment_reference),
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

    def start_session(self, experiment_id: str | None = None, notes: str | None = None) -> dict[str, Any]:
        """Start one active laboratory experiment session."""

        session_id = f"session:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO experiment_sessions (
                    session_id, experiment_id, notes
                )
                VALUES (?, ?, ?)
                """,
                (session_id, experiment_id, notes),
            )
        session = self.get_session(session_id)
        if session is None:
            raise RuntimeError(f"Session was not saved: {session_id}")
        if notes:
            self.append_session_event(
                session_id=session_id,
                event_type="manual_note",
                title="Session started",
                content=notes,
                metadata={"source": "session_start"},
            )
            session = self.get_session(session_id) or session
        return session

    def end_session(self, session_id: str, notes: str | None = None) -> dict[str, Any] | None:
        """End one active laboratory experiment session."""

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE experiment_sessions
                SET status = 'ended',
                    end_time = CURRENT_TIMESTAMP,
                    notes = COALESCE(?, notes),
                    updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ?
                """,
                (notes, session_id),
            )
        if cursor.rowcount == 0:
            return None
        if notes:
            self.append_session_event(
                session_id=session_id,
                event_type="manual_note",
                title="Session ended",
                content=notes,
                metadata={"source": "session_end"},
            )
        return self.get_session(session_id)

    def list_sessions(self) -> list[dict[str, Any]]:
        """Return laboratory experiment sessions."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM experiment_sessions
                ORDER BY COALESCE(end_time, start_time) DESC, start_time DESC
                """
            ).fetchall()
        return [self._session_row_to_dict(row) for row in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Return one laboratory experiment session with assets and timeline."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM experiment_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        session = self._session_row_to_dict(row)
        timeline = self.session_timeline(session_id)
        session["timeline"] = timeline
        session["assets"] = [
            self.get_asset(str(event["asset_id"]))
            for event in timeline
            if event.get("asset_id")
        ]
        session["assets"] = [asset for asset in session["assets"] if asset]
        session["recent_notes"] = [
            event
            for event in timeline
            if event.get("event_type") in {"voice_note", "manual_note", "observation", "treatment", "media_change"}
        ][:8]
        return session

    def append_session_event(
        self,
        session_id: str,
        event_type: str,
        title: str,
        content: str | None = None,
        asset_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Append one event to a session timeline."""

        event_id = f"session-event:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM experiment_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if exists is None:
                return None
            connection.execute(
                """
                INSERT INTO session_events (
                    event_id, session_id, event_type, title, content, asset_id,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    session_id,
                    event_type,
                    title,
                    content,
                    asset_id,
                    json.dumps(metadata or {}, sort_keys=True),
                ),
            )
            if event_type == "voice_note" and content:
                row = connection.execute(
                    "SELECT voice_transcripts_json FROM experiment_sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                transcripts = json.loads(row["voice_transcripts_json"] or "[]") if row else []
                transcripts.append(content)
                connection.execute(
                    """
                    UPDATE experiment_sessions
                    SET voice_transcripts_json = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE session_id = ?
                    """,
                    (json.dumps(transcripts), session_id),
                )
            else:
                connection.execute(
                    "UPDATE experiment_sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
                    (session_id,),
                )
        return self.get_session_event(event_id)

    def get_session_event(self, event_id: str) -> dict[str, Any] | None:
        """Return one session timeline event."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM session_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return self._session_event_row_to_dict(row) if row else None

    def session_timeline(self, session_id: str) -> list[dict[str, Any]]:
        """Return session timeline events in chronological order."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM session_events
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
        return [self._session_event_row_to_dict(row) for row in rows]

    def get_experiment_lifecycle(self, experiment_id: str) -> dict[str, Any]:
        """Return lifecycle state for an experiment, creating Planning if missing."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM experiment_lifecycles WHERE experiment_id = ?",
                (experiment_id,),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO experiment_lifecycles (experiment_id, current_stage)
                    VALUES (?, 'Planning')
                    """,
                    (experiment_id,),
                )
                connection.execute(
                    """
                    INSERT INTO experiment_lifecycle_events (
                        lifecycle_event_id, experiment_id, from_stage, to_stage,
                        reason, actor, metadata_json
                    )
                    VALUES (?, ?, NULL, 'Planning', ?, ?, ?)
                    """,
                    (
                        f"lifecycle-event:{uuid.uuid4().hex[:16]}",
                        experiment_id,
                        "Lifecycle initialized.",
                        "ResearchOS",
                        json.dumps({"source": "default"}, sort_keys=True),
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM experiment_lifecycles WHERE experiment_id = ?",
                    (experiment_id,),
                ).fetchone()
        lifecycle = dict(row)
        lifecycle["history"] = self.experiment_lifecycle_history(experiment_id)
        return lifecycle

    def transition_experiment_lifecycle(
        self,
        experiment_id: str,
        to_stage: str,
        reason: str | None = None,
        actor: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Transition an experiment lifecycle and append history."""

        current = self.get_experiment_lifecycle(experiment_id)
        from_stage = str(current["current_stage"])
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO experiment_lifecycle_events (
                    lifecycle_event_id, experiment_id, from_stage, to_stage,
                    reason, actor, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"lifecycle-event:{uuid.uuid4().hex[:16]}",
                    experiment_id,
                    from_stage,
                    to_stage,
                    reason,
                    actor,
                    json.dumps(metadata or {}, sort_keys=True),
                ),
            )
            connection.execute(
                """
                INSERT INTO experiment_lifecycles (experiment_id, current_stage)
                VALUES (?, ?)
                ON CONFLICT(experiment_id) DO UPDATE SET
                    current_stage = excluded.current_stage,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (experiment_id, to_stage),
            )
        return self.get_experiment_lifecycle(experiment_id)

    def experiment_lifecycle_history(self, experiment_id: str) -> list[dict[str, Any]]:
        """Return lifecycle transition history."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM experiment_lifecycle_events
                WHERE experiment_id = ?
                ORDER BY created_at ASC
                """,
                (experiment_id,),
            ).fetchall()
        return [self._lifecycle_event_row_to_dict(row) for row in rows]

    def lifecycle_stage_counts(self) -> dict[str, int]:
        """Return experiment counts grouped by lifecycle stage."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT COALESCE(l.current_stage, 'Planning') AS stage, COUNT(e.id) AS count
                FROM experiments e
                LEFT JOIN experiment_lifecycles l ON l.experiment_id = e.id
                GROUP BY COALESCE(l.current_stage, 'Planning')
                """
            ).fetchall()
        return {str(row["stage"]): int(row["count"]) for row in rows}

    def get_or_create_workflow_state(
        self,
        workflow_id: str,
        workflow_type: str,
        subject_id: str,
        initial_stage: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a workflow state, creating an initial state if needed."""

        state = self.get_workflow_state(workflow_id)
        if state is not None:
            return state
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workflow_states (
                    workflow_id, workflow_type, subject_id, current_stage, metadata_json
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    workflow_type,
                    subject_id,
                    initial_stage,
                    json.dumps(metadata or {}, sort_keys=True),
                ),
            )
            connection.execute(
                """
                INSERT INTO workflow_history (
                    history_id, workflow_id, from_stage, to_stage, reason, actor, metadata_json
                )
                VALUES (?, ?, NULL, ?, ?, ?, ?)
                """,
                (
                    f"workflow-history:{uuid.uuid4().hex[:16]}",
                    workflow_id,
                    initial_stage,
                    "Workflow initialized.",
                    "ResearchOS",
                    json.dumps({"source": "default"}, sort_keys=True),
                ),
            )
        state = self.get_workflow_state(workflow_id)
        assert state is not None
        return state

    def get_workflow_state(self, workflow_id: str) -> dict[str, Any] | None:
        """Return one workflow state."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM workflow_states WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
        return self._workflow_state_row_to_dict(row) if row else None

    def list_workflow_states(self, workflow_type: str | None = None) -> list[dict[str, Any]]:
        """Return persisted workflow states."""

        with self._connect() as connection:
            if workflow_type:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM workflow_states
                    WHERE workflow_type = ?
                    ORDER BY updated_at DESC, created_at DESC
                    """,
                    (workflow_type,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM workflow_states
                    ORDER BY updated_at DESC, created_at DESC
                    """
                ).fetchall()
        return [self._workflow_state_row_to_dict(row) for row in rows]

    def transition_workflow(
        self,
        workflow_id: str,
        to_stage: str,
        reason: str | None = None,
        actor: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Update workflow stage and append history."""

        state = self.get_workflow_state(workflow_id)
        if state is None:
            return None
        from_stage = str(state["current_stage"])
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workflow_history (
                    history_id, workflow_id, from_stage, to_stage, reason, actor, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"workflow-history:{uuid.uuid4().hex[:16]}",
                    workflow_id,
                    from_stage,
                    to_stage,
                    reason,
                    actor,
                    json.dumps(metadata or {}, sort_keys=True),
                ),
            )
            connection.execute(
                """
                UPDATE workflow_states
                SET current_stage = ?, updated_at = CURRENT_TIMESTAMP
                WHERE workflow_id = ?
                """,
                (to_stage, workflow_id),
            )
        return self.get_workflow_state(workflow_id)

    def workflow_history(self, workflow_id: str) -> list[dict[str, Any]]:
        """Return workflow transition history."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM workflow_history
                WHERE workflow_id = ?
                ORDER BY created_at ASC
                """,
                (workflow_id,),
            ).fetchall()
        return [self._workflow_history_row_to_dict(row) for row in rows]

    def add_workflow_note(
        self,
        workflow_id: str,
        stage: str,
        note: str,
        actor: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Append one workflow note."""

        if self.get_workflow_state(workflow_id) is None:
            return None
        note_id = f"workflow-note:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workflow_notes (
                    note_id, workflow_id, stage, note, actor, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    note_id,
                    workflow_id,
                    stage,
                    note,
                    actor,
                    json.dumps(metadata or {}, sort_keys=True),
                ),
            )
        return self.get_workflow_note(note_id)

    def get_workflow_note(self, note_id: str) -> dict[str, Any] | None:
        """Return one workflow note."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM workflow_notes WHERE note_id = ?",
                (note_id,),
            ).fetchone()
        return self._workflow_note_row_to_dict(row) if row else None

    def workflow_notes(self, workflow_id: str) -> list[dict[str, Any]]:
        """Return workflow notes in chronological order."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM workflow_notes
                WHERE workflow_id = ?
                ORDER BY created_at ASC
                """,
                (workflow_id,),
            ).fetchall()
        return [self._workflow_note_row_to_dict(row) for row in rows]

    def workflow_stage_counts(self, workflow_type: str = "experiment") -> dict[str, int]:
        """Return extracted experiment counts grouped by workflow stage."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT COALESCE(w.current_stage, 'Planning') AS stage, COUNT(e.id) AS count
                FROM experiments e
                LEFT JOIN workflow_states w
                    ON w.workflow_type = ? AND w.subject_id = e.id
                GROUP BY COALESCE(w.current_stage, 'Planning')
                """,
                (workflow_type,),
            ).fetchall()
        return {str(row["stage"]): int(row["count"]) for row in rows}

    def upsert_user(
        self,
        user_id: str,
        email: str,
        display_name: str,
        role: str,
        auth_provider: str = "local_dev",
        mark_login: bool = False,
    ) -> dict[str, Any]:
        """Create or update one ResearchOS user."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO users (
                    user_id, email, display_name, role, auth_provider, last_login
                )
                VALUES (?, ?, ?, ?, ?, CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END)
                ON CONFLICT(user_id) DO UPDATE SET
                    email = excluded.email,
                    display_name = excluded.display_name,
                    role = excluded.role,
                    auth_provider = excluded.auth_provider,
                    last_login = CASE
                        WHEN ? THEN CURRENT_TIMESTAMP
                        ELSE users.last_login
                    END
                """,
                (user_id, email, display_name, role, auth_provider, mark_login, mark_login),
            )
        user = self.get_user(user_id)
        assert user is not None
        return user

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        """Return one user by ID."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        """Return one user by email."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE lower(email) = lower(?)",
                (email,),
            ).fetchone()
        return dict(row) if row else None

    def list_users(self) -> list[dict[str, Any]]:
        """Return all ResearchOS users."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM users
                ORDER BY created_at ASC, email ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

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

    def list_assets_for_experiment(self, experiment: dict[str, Any]) -> list[dict[str, Any]]:
        """Return assets linked by internal or human experiment reference."""

        references = sorted(_experiment_asset_references(experiment))

        placeholders = ", ".join("?" for _ in references)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM assets
                WHERE experiment_id IN ({placeholders})
                ORDER BY updated_at DESC, created_at DESC, title ASC
                """,
                references,
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

    def get_asset_by_provider_path(self, provider: str, path: str) -> dict[str, Any] | None:
        """Return one asset by provider/path for duplicate prevention."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM assets WHERE provider = ? AND path = ?",
                (provider, path),
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

    def update_asset_metadata(
        self,
        asset_id: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Replace asset metadata JSON and refresh the update timestamp."""

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE assets
                SET metadata_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE asset_id = ?
                """,
                (json.dumps(metadata, sort_keys=True), asset_id),
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

    def _session_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Deserialize a session row into API-ready fields."""

        record = dict(row)
        record["voice_transcripts"] = json.loads(record.pop("voice_transcripts_json") or "[]")
        return record

    def _session_event_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Deserialize a session timeline event row."""

        record = dict(row)
        record["metadata"] = json.loads(record.pop("metadata_json") or "{}")
        return record

    def _lifecycle_event_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Deserialize a lifecycle history row."""

        record = dict(row)
        record["metadata"] = json.loads(record.pop("metadata_json") or "{}")
        return record

    def _workflow_state_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Deserialize a workflow state row."""

        record = dict(row)
        record["metadata"] = json.loads(record.pop("metadata_json") or "{}")
        return record

    def _workflow_history_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Deserialize a workflow history row."""

        record = dict(row)
        record["metadata"] = json.loads(record.pop("metadata_json") or "{}")
        return record

    def _workflow_note_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Deserialize a workflow note row."""

        record = dict(row)
        record["metadata"] = json.loads(record.pop("metadata_json") or "{}")
        return record


def _experiment_asset_references(experiment: dict[str, Any]) -> set[str]:
    """Return internal and human experiment references for asset matching."""

    candidates = [
        str(experiment.get("id") or ""),
        str(experiment.get("experiment_id") or ""),
        str(experiment.get("title") or ""),
        str(experiment.get("notes") or ""),
        str(experiment.get("conclusions") or ""),
    ]
    references = {value for value in candidates if value and not value.startswith("None")}
    haystack = " ".join(candidates)
    for match in re.finditer(r"(?:^|[^A-Za-z0-9])NK[_-]?Expt[_-]?(\d+)(?=$|[^A-Za-z0-9])", haystack, flags=re.IGNORECASE):
        references.add(f"NK_Expt_{match.group(1)}")
    for match in re.finditer(r"(?:^|[^A-Za-z0-9])EXP[_-]?(\d+)(?=$|[^A-Za-z0-9])", haystack, flags=re.IGNORECASE):
        references.add(f"EXP_{match.group(1)}")
    return references
