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
from app.resources import normalize_resource_type, resource_entity_type

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
                    workspace_id TEXT,
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
                    owner_user_id TEXT,
                    created_by TEXT,
                    workspace_id TEXT,
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
                    owner_user_id TEXT,
                    created_by TEXT,
                    workspace_id TEXT,
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
                    owner_user_id TEXT,
                    created_by TEXT,
                    workspace_id TEXT,
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
                    owner_user_id TEXT,
                    created_by TEXT,
                    workspace_id TEXT,
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
                    owner_user_id TEXT,
                    created_by TEXT,
                    workspace_id TEXT,
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

                CREATE TABLE IF NOT EXISTS resources (
                    resource_id TEXT PRIMARY KEY,
                    resource_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    aliases_json TEXT NOT NULL DEFAULT '[]',
                    vendor TEXT,
                    catalog_number TEXT,
                    lot_number TEXT,
                    rrid TEXT,
                    storage_location TEXT,
                    concentration TEXT,
                    units TEXT,
                    expiration TEXT,
                    notes TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    owner_user_id TEXT,
                    created_by TEXT,
                    workspace_id TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_resources_type
                    ON resources(resource_type);
                CREATE INDEX IF NOT EXISTS idx_resources_name
                    ON resources(name);

                CREATE TABLE IF NOT EXISTS resource_usages (
                    usage_id TEXT PRIMARY KEY,
                    resource_id TEXT NOT NULL,
                    object_type TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    usage_type TEXT NOT NULL DEFAULT 'referenced',
                    source TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    workspace_id TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(resource_id) REFERENCES resources(resource_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_resource_usages_resource_id
                    ON resource_usages(resource_id);
                CREATE INDEX IF NOT EXISTS idx_resource_usages_object
                    ON resource_usages(object_type, object_id);

                CREATE TABLE IF NOT EXISTS lab_workspaces (
                    workspace_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    institution TEXT,
                    description TEXT,
                    owner_user_id TEXT,
                    created_by TEXT,
                    default_role TEXT NOT NULL DEFAULT 'researcher',
                    settings_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS workspace_memberships (
                    workspace_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(workspace_id, user_id)
                );

                CREATE INDEX IF NOT EXISTS idx_workspace_memberships_user_id
                    ON workspace_memberships(user_id);

                CREATE TABLE IF NOT EXISTS active_workspaces (
                    user_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

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

                CREATE TABLE IF NOT EXISTS lab_intelligence_item_states (
                    item_id TEXT PRIMARY KEY,
                    dismissed INTEGER NOT NULL DEFAULT 0,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS inventory_items (
                    item_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT,
                    vendor TEXT,
                    catalog_number TEXT,
                    lot_number TEXT,
                    rrid TEXT,
                    price REAL,
                    unit TEXT,
                    storage_location TEXT,
                    quantity REAL,
                    reorder_threshold REAL,
                    expiration_date TEXT,
                    barcode TEXT,
                    qr_code TEXT,
                    internal_label TEXT,
                    freezer_box TEXT,
                    freezer_position TEXT,
                    shelf TEXT,
                    room TEXT,
                    notes TEXT,
                    linked_resource_id TEXT,
                    owner_user_id TEXT,
                    created_by TEXT,
                    workspace_id TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_inventory_category
                    ON inventory_items(category);
                CREATE INDEX IF NOT EXISTS idx_inventory_vendor
                    ON inventory_items(vendor);
                CREATE INDEX IF NOT EXISTS idx_inventory_storage_location
                    ON inventory_items(storage_location);
                CREATE INDEX IF NOT EXISTS idx_inventory_linked_resource
                    ON inventory_items(linked_resource_id);

                CREATE TABLE IF NOT EXISTS inventory_usage (
                    usage_id TEXT PRIMARY KEY,
                    inventory_item_id TEXT NOT NULL,
                    experiment_id TEXT NOT NULL,
                    session_id TEXT,
                    protocol_id TEXT,
                    amount_used REAL,
                    units TEXT,
                    date_used TEXT,
                    used_by TEXT,
                    purpose TEXT,
                    notes TEXT,
                    workspace_id TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_inventory_usage_item
                    ON inventory_usage(inventory_item_id);
                CREATE INDEX IF NOT EXISTS idx_inventory_usage_experiment
                    ON inventory_usage(experiment_id);
                CREATE INDEX IF NOT EXISTS idx_inventory_usage_session
                    ON inventory_usage(session_id);

                CREATE TABLE IF NOT EXISTS purchase_records (
                    purchase_id TEXT PRIMARY KEY,
                    item_name TEXT NOT NULL,
                    vendor TEXT,
                    catalog_number TEXT,
                    purchase_date TEXT,
                    cost REAL,
                    quantity REAL,
                    grant_or_funding_source TEXT,
                    purchaser TEXT,
                    oracle_po_number TEXT,
                    invoice_number TEXT,
                    status TEXT,
                    notes TEXT,
                    owner_user_id TEXT,
                    created_by TEXT,
                    workspace_id TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_purchase_vendor
                    ON purchase_records(vendor);
                CREATE INDEX IF NOT EXISTS idx_purchase_grant
                    ON purchase_records(grant_or_funding_source);
                CREATE INDEX IF NOT EXISTS idx_purchase_date
                    ON purchase_records(purchase_date);
                CREATE INDEX IF NOT EXISTS idx_purchase_oracle_po
                    ON purchase_records(oracle_po_number);

                CREATE TABLE IF NOT EXISTS purchase_requests (
                    request_id TEXT PRIMARY KEY,
                    item_name TEXT NOT NULL,
                    vendor TEXT,
                    catalog_number TEXT,
                    quantity_requested REAL,
                    estimated_cost REAL,
                    grant_or_funding_source TEXT,
                    requested_by TEXT,
                    request_date TEXT,
                    status TEXT NOT NULL DEFAULT 'draft',
                    notes TEXT,
                    linked_inventory_item_id TEXT,
                    owner_user_id TEXT,
                    created_by TEXT,
                    workspace_id TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_purchase_requests_status
                    ON purchase_requests(status);
                CREATE INDEX IF NOT EXISTS idx_purchase_requests_item
                    ON purchase_requests(item_name);
                CREATE INDEX IF NOT EXISTS idx_purchase_requests_inventory_item
                    ON purchase_requests(linked_inventory_item_id);

                CREATE TABLE IF NOT EXISTS purchase_import_templates (
                    template_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    provider TEXT,
                    mapping TEXT NOT NULL,
                    owner_user_id TEXT,
                    created_by TEXT,
                    workspace_id TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_purchase_import_templates_name
                    ON purchase_import_templates(name);
                """
            )
            self._ensure_permission_columns(connection)

    def _ensure_permission_columns(self, connection: sqlite3.Connection) -> None:
        """Add nullable owner columns to existing local databases."""

        for table in ["experiments", "pending_entries", "assets", "experiment_sessions", "workflow_states", "resources", "inventory_items", "inventory_usage", "purchase_records", "purchase_requests", "purchase_import_templates"]:
            existing = {
                str(row["name"])
                for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for column in ["owner_user_id", "created_by", "workspace_id"]:
                if column not in existing:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
            if table == "inventory_items":
                for column in ["barcode", "qr_code", "internal_label", "freezer_box", "freezer_position", "shelf", "room"]:
                    if column not in existing:
                        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
                connection.execute("CREATE INDEX IF NOT EXISTS idx_inventory_barcode ON inventory_items(barcode)")
                connection.execute("CREATE INDEX IF NOT EXISTS idx_inventory_qr_code ON inventory_items(qr_code)")
                connection.execute("CREATE INDEX IF NOT EXISTS idx_inventory_internal_label ON inventory_items(internal_label)")
        document_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(documents)").fetchall()
        }
        if "workspace_id" not in document_columns:
            connection.execute("ALTER TABLE documents ADD COLUMN workspace_id TEXT")
        workspace_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(lab_workspaces)").fetchall()
        }
        if "created_by" not in workspace_columns:
            connection.execute("ALTER TABLE lab_workspaces ADD COLUMN created_by TEXT")
        if "default_role" not in workspace_columns:
            connection.execute("ALTER TABLE lab_workspaces ADD COLUMN default_role TEXT NOT NULL DEFAULT 'researcher'")

    def _workspace_clause(self, workspace_id: str | None) -> tuple[str, list[str]]:
        """Return a permissive workspace filter for scaffolded isolation."""

        if not workspace_id:
            return "", []
        return "(workspace_id = ? OR workspace_id IS NULL OR workspace_id = '')", [workspace_id]

    def upsert_document(
        self,
        document: ResearchDocument,
        chunks: list[DocumentChunk],
        workspace_id: str | None = None,
    ) -> None:
        """Store one document and replace its chunks atomically."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO documents (
                    id, provider, source_id, title, content, source_path, source_url,
                    created_at, updated_at, metadata_json, workspace_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    workspace_id = COALESCE(excluded.workspace_id, documents.workspace_id),
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
                    workspace_id,
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

    def list_documents(self, workspace_id: str | None = None) -> list[dict[str, Any]]:
        """Return stored document summaries."""

        clause, values = self._workspace_clause(workspace_id)
        where = f"WHERE {clause}" if clause else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, provider, source_id, title, source_path, source_url,
                       created_at, updated_at, workspace_id, ingested_at
                FROM documents
                {where}
                ORDER BY ingested_at DESC, title ASC
                """,
                values,
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
            source_row = connection.execute(
                "SELECT workspace_id FROM documents WHERE id = ?",
                (experiment.source_document_id,),
            ).fetchone()
            workspace_id = source_row["workspace_id"] if source_row else None
            connection.execute(
                """
                INSERT INTO experiments (
                    id, source_document_id, source_provider, title, experiment_id, date,
                    researcher, cell_line, organoid_batch, compounds_json,
                    treatments_json, concentrations_json, time_points_json, markers_json,
                    antibodies_json, imaging_methods_json, sequencing_json, notes, conclusions,
                    workspace_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    workspace_id = COALESCE(excluded.workspace_id, experiments.workspace_id),
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
                    workspace_id,
                ),
            )

    def list_experiments(self, workspace_id: str | None = None) -> list[dict[str, Any]]:
        """Return all extracted experiments."""

        clause, values = self._workspace_clause(workspace_id)
        where = f"WHERE {clause}" if clause else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM experiments
                {where}
                ORDER BY COALESCE(date, extracted_at) DESC, title ASC
                """,
                values,
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

    def get_all_research_documents(self, workspace_id: str | None = None) -> list[ResearchDocument]:
        """Return stored documents as ResearchDocument objects for extraction."""

        clause, values = self._workspace_clause(workspace_id)
        where = f"WHERE {clause}" if clause else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, provider, source_id, title, content, source_path, source_url,
                       created_at, updated_at, metadata_json
                FROM documents
                {where}
                ORDER BY ingested_at DESC, title ASC
                """,
                values,
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
        owner_user_id: str | None = None,
        created_by: str | None = None,
        workspace_id: str | None = None,
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
                        markdown, status, owner_user_id, created_by, workspace_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        resolved_id,
                        title,
                        experiment_id,
                        template,
                        json.dumps(structured, sort_keys=True),
                        markdown,
                        status,
                        owner_user_id,
                        created_by or owner_user_id,
                        workspace_id,
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
                        owner_user_id = COALESCE(?, owner_user_id),
                        created_by = COALESCE(?, created_by),
                        workspace_id = COALESCE(?, workspace_id),
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
                        owner_user_id,
                        created_by or owner_user_id,
                        workspace_id,
                        resolved_id,
                    ),
                )

        saved = self.get_pending_entry(resolved_id)
        if saved is None:
            raise RuntimeError(f"Pending entry was not saved: {resolved_id}")
        return saved

    def list_pending_entries(self, workspace_id: str | None = None) -> list[dict[str, Any]]:
        """Return pending notebook-entry drafts."""

        clause, values = self._workspace_clause(workspace_id)
        where = f"WHERE {clause}" if clause else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, title, experiment_id, template, status, workspace_id, created_at, updated_at
                FROM pending_entries
                {where}
                ORDER BY updated_at DESC, created_at DESC
                """,
                values,
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

    def start_session(
        self,
        experiment_id: str | None = None,
        notes: str | None = None,
        owner_user_id: str | None = None,
        created_by: str | None = None,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Start one active laboratory experiment session."""

        session_id = f"session:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO experiment_sessions (
                    session_id, experiment_id, notes, owner_user_id, created_by, workspace_id
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, experiment_id, notes, owner_user_id, created_by or owner_user_id, workspace_id),
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

    def list_sessions(self, workspace_id: str | None = None) -> list[dict[str, Any]]:
        """Return laboratory experiment sessions."""

        clause, values = self._workspace_clause(workspace_id)
        where = f"WHERE {clause}" if clause else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM experiment_sessions
                {where}
                ORDER BY COALESCE(end_time, start_time) DESC, start_time DESC
                """,
                values,
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
        owner_user_id: str | None = None,
        created_by: str | None = None,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Return a workflow state, creating an initial state if needed."""

        state = self.get_workflow_state(workflow_id)
        if state is not None:
            return state
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workflow_states (
                    workflow_id, workflow_type, subject_id, current_stage,
                    metadata_json, owner_user_id, created_by, workspace_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    workflow_type,
                    subject_id,
                    initial_stage,
                    json.dumps(metadata or {}, sort_keys=True),
                    owner_user_id,
                    created_by or owner_user_id,
                    workspace_id,
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

    def list_workflow_states(
        self,
        workflow_type: str | None = None,
        workspace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return persisted workflow states."""

        clauses: list[str] = []
        values: list[str] = []
        if workflow_type:
            clauses.append("workflow_type = ?")
            values.append(workflow_type)
        workspace_clause, workspace_values = self._workspace_clause(workspace_id)
        if workspace_clause:
            clauses.append(workspace_clause)
            values.extend(workspace_values)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM workflow_states
                {where}
                ORDER BY updated_at DESC, created_at DESC
                """,
                values,
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

    def upsert_workspace(
        self,
        workspace_id: str,
        name: str,
        institution: str | None = None,
        description: str | None = None,
        owner_user_id: str | None = None,
        created_by: str | None = None,
        default_role: str = "researcher",
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create or update one lab workspace."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO lab_workspaces (
                    workspace_id, name, institution, description, owner_user_id,
                    created_by, default_role, settings_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workspace_id) DO UPDATE SET
                    name = excluded.name,
                    institution = excluded.institution,
                    description = excluded.description,
                    owner_user_id = excluded.owner_user_id,
                    created_by = COALESCE(lab_workspaces.created_by, excluded.created_by),
                    default_role = excluded.default_role,
                    settings_json = excluded.settings_json
                """,
                (
                    workspace_id,
                    name,
                    institution,
                    description,
                    owner_user_id,
                    created_by or owner_user_id,
                    default_role,
                    json.dumps(settings or {}, sort_keys=True),
                ),
            )
        workspace = self.get_workspace(workspace_id)
        assert workspace is not None
        return workspace

    def get_workspace(self, workspace_id: str) -> dict[str, Any] | None:
        """Return one lab workspace."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM lab_workspaces WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone()
        return self._workspace_row_to_dict(row) if row else None

    def list_workspaces(self) -> list[dict[str, Any]]:
        """Return lab workspaces."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM lab_workspaces
                ORDER BY created_at ASC, name ASC
                """
            ).fetchall()
        return [self._workspace_row_to_dict(row) for row in rows]

    def upsert_workspace_membership(self, workspace_id: str, user_id: str, role: str) -> dict[str, Any]:
        """Create or update one workspace membership."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workspace_memberships (workspace_id, user_id, role)
                VALUES (?, ?, ?)
                ON CONFLICT(workspace_id, user_id) DO UPDATE SET
                    role = excluded.role
                """,
                (workspace_id, user_id, role),
            )
        membership = self.get_workspace_membership(workspace_id, user_id)
        assert membership is not None
        return membership

    def get_workspace_membership(self, workspace_id: str, user_id: str | None) -> dict[str, Any] | None:
        """Return one workspace membership."""

        if not user_id:
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM workspace_memberships
                WHERE workspace_id = ? AND user_id = ?
                """,
                (workspace_id, user_id),
            ).fetchone()
        return dict(row) if row else None

    def list_workspace_memberships(self, workspace_id: str) -> list[dict[str, Any]]:
        """Return memberships for one workspace."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    wm.workspace_id,
                    wm.user_id,
                    wm.role,
                    wm.joined_at,
                    u.email,
                    u.display_name,
                    u.auth_provider
                FROM workspace_memberships wm
                LEFT JOIN users u ON u.user_id = wm.user_id
                WHERE wm.workspace_id = ?
                ORDER BY wm.joined_at ASC
                """,
                (workspace_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def workspace_member(self, workspace_id: str, user_id: str) -> dict[str, Any] | None:
        """Return one workspace membership with user display metadata."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    wm.workspace_id,
                    wm.user_id,
                    wm.role,
                    wm.joined_at,
                    u.email,
                    u.display_name,
                    u.auth_provider
                FROM workspace_memberships wm
                LEFT JOIN users u ON u.user_id = wm.user_id
                WHERE wm.workspace_id = ? AND wm.user_id = ?
                """,
                (workspace_id, user_id),
            ).fetchone()
        return dict(row) if row else None

    def get_active_workspace_id(self, user_id: str) -> str | None:
        """Return the user's active workspace pointer, if one has been selected."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT workspace_id FROM active_workspaces WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return str(row["workspace_id"]) if row else None

    def set_active_workspace(self, user_id: str, workspace_id: str) -> dict[str, Any] | None:
        """Persist the active workspace pointer for one user."""

        workspace = self.get_workspace(workspace_id)
        if workspace is None:
            return None
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO active_workspaces (user_id, workspace_id, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    workspace_id = excluded.workspace_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, workspace_id),
            )
        return workspace

    def workspace_counts(self, workspace_id: str) -> dict[str, int]:
        """Return workspace-level counts without enforcing strict isolation."""

        with self._connect() as connection:
            documents = connection.execute(
                "SELECT COUNT(*) AS count FROM documents WHERE workspace_id = ? OR workspace_id IS NULL",
                (workspace_id,),
            ).fetchone()
            experiments = connection.execute(
                "SELECT COUNT(*) AS count FROM experiments WHERE workspace_id = ? OR workspace_id IS NULL",
                (workspace_id,),
            ).fetchone()
            assets = connection.execute(
                "SELECT COUNT(*) AS count FROM assets WHERE workspace_id = ? OR workspace_id IS NULL",
                (workspace_id,),
            ).fetchone()
            entries = connection.execute(
                "SELECT COUNT(*) AS count FROM pending_entries WHERE workspace_id = ? OR workspace_id IS NULL",
                (workspace_id,),
            ).fetchone()
            sessions = connection.execute(
                "SELECT COUNT(*) AS count FROM experiment_sessions WHERE workspace_id = ? OR workspace_id IS NULL",
                (workspace_id,),
            ).fetchone()
            workflows = connection.execute(
                "SELECT COUNT(*) AS count FROM workflow_states WHERE workspace_id = ? OR workspace_id IS NULL",
                (workspace_id,),
            ).fetchone()
            resources = connection.execute(
                "SELECT COUNT(*) AS count FROM resources WHERE workspace_id = ? OR workspace_id IS NULL",
                (workspace_id,),
            ).fetchone()
        return {
            "documents": int(documents["count"]),
            "experiments": int(experiments["count"]),
            "assets": int(assets["count"]),
            "entries": int(entries["count"]),
            "sessions": int(sessions["count"]),
            "workflows": int(workflows["count"]),
            "resources": int(resources["count"]),
        }

    def lab_intelligence_item_states(self) -> dict[str, dict[str, Any]]:
        """Return persisted UI state for dynamic intelligence feed items."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT item_id, dismissed, pinned, updated_at
                FROM lab_intelligence_item_states
                """
            ).fetchall()
        return {
            str(row["item_id"]): {
                "dismissed": bool(row["dismissed"]),
                "pinned": bool(row["pinned"]),
                "updated_at": row["updated_at"],
            }
            for row in rows
        }

    def set_lab_intelligence_item_state(
        self,
        item_id: str,
        dismissed: bool | None = None,
        pinned: bool | None = None,
    ) -> dict[str, Any]:
        """Persist dismiss/pin state for a deterministic feed item ID."""

        existing = self.lab_intelligence_item_states().get(item_id, {})
        resolved_dismissed = bool(existing.get("dismissed", False) if dismissed is None else dismissed)
        resolved_pinned = bool(existing.get("pinned", False) if pinned is None else pinned)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO lab_intelligence_item_states (item_id, dismissed, pinned, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(item_id) DO UPDATE SET
                    dismissed = excluded.dismissed,
                    pinned = excluded.pinned,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (item_id, int(resolved_dismissed), int(resolved_pinned)),
            )
            row = connection.execute(
                """
                SELECT item_id, dismissed, pinned, updated_at
                FROM lab_intelligence_item_states
                WHERE item_id = ?
                """,
                (item_id,),
            ).fetchone()
        assert row is not None
        return {
            "item_id": row["item_id"],
            "dismissed": bool(row["dismissed"]),
            "pinned": bool(row["pinned"]),
            "updated_at": row["updated_at"],
        }

    def save_resource(
        self,
        name: str,
        resource_type: str = "other",
        aliases: list[str] | None = None,
        vendor: str | None = None,
        catalog_number: str | None = None,
        lot_number: str | None = None,
        rrid: str | None = None,
        storage_location: str | None = None,
        concentration: str | None = None,
        units: str | None = None,
        expiration: str | None = None,
        notes: str | None = None,
        metadata: dict[str, Any] | None = None,
        resource_id: str | None = None,
        owner_user_id: str | None = None,
        created_by: str | None = None,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a reusable laboratory resource."""

        resolved_id = resource_id or f"resource:{uuid.uuid4().hex[:16]}"
        normalized_type = normalize_resource_type(resource_type)
        clean_aliases = _dedupe_strings(aliases or [])
        clean_metadata = dict(metadata or {})
        clean_metadata.setdefault("entities", {resource_entity_type(normalized_type): [name, *clean_aliases]})
        if clean_aliases:
            clean_metadata.setdefault("aliases", {name: clean_aliases})
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT created_at FROM resources WHERE resource_id = ?",
                (resolved_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO resources (
                        resource_id, resource_type, name, aliases_json, vendor,
                        catalog_number, lot_number, rrid, storage_location,
                        concentration, units, expiration, notes, metadata_json,
                        owner_user_id, created_by, workspace_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        resolved_id,
                        normalized_type,
                        name,
                        json.dumps(clean_aliases, sort_keys=True),
                        vendor,
                        catalog_number,
                        lot_number,
                        rrid,
                        storage_location,
                        concentration,
                        units,
                        expiration,
                        notes,
                        json.dumps(clean_metadata, sort_keys=True),
                        owner_user_id,
                        created_by or owner_user_id,
                        workspace_id,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE resources
                    SET resource_type = ?,
                        name = ?,
                        aliases_json = ?,
                        vendor = ?,
                        catalog_number = ?,
                        lot_number = ?,
                        rrid = ?,
                        storage_location = ?,
                        concentration = ?,
                        units = ?,
                        expiration = ?,
                        notes = ?,
                        metadata_json = ?,
                        owner_user_id = COALESCE(?, owner_user_id),
                        created_by = COALESCE(?, created_by),
                        workspace_id = COALESCE(?, workspace_id),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE resource_id = ?
                    """,
                    (
                        normalized_type,
                        name,
                        json.dumps(clean_aliases, sort_keys=True),
                        vendor,
                        catalog_number,
                        lot_number,
                        rrid,
                        storage_location,
                        concentration,
                        units,
                        expiration,
                        notes,
                        json.dumps(clean_metadata, sort_keys=True),
                        owner_user_id,
                        created_by or owner_user_id,
                        workspace_id,
                        resolved_id,
                    ),
                )

        saved = self.get_resource(resolved_id)
        if saved is None:
            raise RuntimeError(f"Resource was not saved: {resolved_id}")
        return saved

    def list_resources(
        self,
        resource_type: str | None = None,
        query: str | None = None,
        workspace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return reusable lab resources."""

        clauses: list[str] = []
        values: list[str] = []
        if resource_type:
            clauses.append("resource_type = ?")
            values.append(normalize_resource_type(resource_type))
        if query:
            clauses.append("(LOWER(name) LIKE ? OR LOWER(aliases_json) LIKE ? OR LOWER(vendor) LIKE ? OR LOWER(catalog_number) LIKE ? OR LOWER(rrid) LIKE ?)")
            needle = f"%{query.lower()}%"
            values.extend([needle, needle, needle, needle, needle])
        workspace_clause, workspace_values = self._workspace_clause(workspace_id)
        if workspace_clause:
            clauses.append(workspace_clause)
            values.extend(workspace_values)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM resources
                {where}
                ORDER BY resource_type ASC, name ASC
                """,
                values,
            ).fetchall()
        return [self._resource_row_to_dict(row) for row in rows]

    def get_resource(self, resource_id: str) -> dict[str, Any] | None:
        """Return one lab resource."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM resources WHERE resource_id = ?",
                (resource_id,),
            ).fetchone()
        return self._resource_row_to_dict(row) if row else None

    def find_resource_by_name(self, name: str, workspace_id: str | None = None) -> dict[str, Any] | None:
        """Find a resource by name or alias."""

        needle = name.strip().lower()
        for resource in self.list_resources(workspace_id=workspace_id):
            aliases = [str(alias).lower() for alias in resource.get("aliases") or []]
            if str(resource.get("name") or "").lower() == needle or needle in aliases:
                return resource
        return None

    def resource_usages(self, resource_id: str) -> list[dict[str, Any]]:
        """Return usage records for one resource."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM resource_usages
                WHERE resource_id = ?
                ORDER BY created_at DESC
                """,
                (resource_id,),
            ).fetchall()
        return [self._resource_usage_row_to_dict(row) for row in rows]

    def record_resource_usage(
        self,
        resource_id: str,
        object_type: str,
        object_id: str,
        usage_type: str = "referenced",
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Record that a resource is used by another ResearchOS object."""

        usage_id = f"resource-usage:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO resource_usages (
                    usage_id, resource_id, object_type, object_id, usage_type,
                    source, metadata_json, workspace_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usage_id,
                    resource_id,
                    object_type,
                    object_id,
                    usage_type,
                    source,
                    json.dumps(metadata or {}, sort_keys=True),
                    workspace_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM resource_usages WHERE usage_id = ?",
                (usage_id,),
            ).fetchone()
        assert row is not None
        return self._resource_usage_row_to_dict(row)

    def save_inventory_item(
        self,
        name: str,
        category: str | None = None,
        vendor: str | None = None,
        catalog_number: str | None = None,
        lot_number: str | None = None,
        rrid: str | None = None,
        price: float | None = None,
        unit: str | None = None,
        storage_location: str | None = None,
        quantity: float | None = None,
        reorder_threshold: float | None = None,
        expiration_date: str | None = None,
        barcode: str | None = None,
        qr_code: str | None = None,
        internal_label: str | None = None,
        freezer_box: str | None = None,
        freezer_position: str | None = None,
        shelf: str | None = None,
        room: str | None = None,
        notes: str | None = None,
        linked_resource_id: str | None = None,
        item_id: str | None = None,
        owner_user_id: str | None = None,
        created_by: str | None = None,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Create or update one inventory item."""

        resolved_id = item_id or f"inventory:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT created_at FROM inventory_items WHERE item_id = ?",
                (resolved_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO inventory_items (
                        item_id, name, category, vendor, catalog_number, lot_number,
                        rrid, price, unit, storage_location, quantity, reorder_threshold,
                        expiration_date, barcode, qr_code, internal_label,
                        freezer_box, freezer_position, shelf, room, notes,
                        linked_resource_id, owner_user_id, created_by, workspace_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        resolved_id,
                        name,
                        category,
                        vendor,
                        catalog_number,
                        lot_number,
                        rrid,
                        price,
                        unit,
                        storage_location,
                        quantity,
                        reorder_threshold,
                        expiration_date,
                        barcode,
                        qr_code,
                        internal_label,
                        freezer_box,
                        freezer_position,
                        shelf,
                        room,
                        notes,
                        linked_resource_id,
                        owner_user_id,
                        created_by or owner_user_id,
                        workspace_id,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE inventory_items
                    SET name = ?,
                        category = ?,
                        vendor = ?,
                        catalog_number = ?,
                        lot_number = ?,
                        rrid = ?,
                        price = ?,
                        unit = ?,
                        storage_location = ?,
                        quantity = ?,
                        reorder_threshold = ?,
                        expiration_date = ?,
                        barcode = ?,
                        qr_code = ?,
                        internal_label = ?,
                        freezer_box = ?,
                        freezer_position = ?,
                        shelf = ?,
                        room = ?,
                        notes = ?,
                        linked_resource_id = ?,
                        owner_user_id = COALESCE(?, owner_user_id),
                        created_by = COALESCE(?, created_by),
                        workspace_id = COALESCE(?, workspace_id),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE item_id = ?
                    """,
                    (
                        name,
                        category,
                        vendor,
                        catalog_number,
                        lot_number,
                        rrid,
                        price,
                        unit,
                        storage_location,
                        quantity,
                        reorder_threshold,
                        expiration_date,
                        barcode,
                        qr_code,
                        internal_label,
                        freezer_box,
                        freezer_position,
                        shelf,
                        room,
                        notes,
                        linked_resource_id,
                        owner_user_id,
                        created_by or owner_user_id,
                        workspace_id,
                        resolved_id,
                    ),
                )
        saved = self.get_inventory_item(resolved_id)
        if saved is None:
            raise RuntimeError(f"Inventory item was not saved: {resolved_id}")
        return saved

    def list_inventory_items(
        self,
        vendor: str | None = None,
        category: str | None = None,
        storage_location: str | None = None,
        query: str | None = None,
        workspace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return inventory items with optional filters."""

        clauses: list[str] = []
        values: list[str] = []
        for column, value in [("vendor", vendor), ("category", category), ("storage_location", storage_location)]:
            if value:
                clauses.append(f"LOWER({column}) = ?")
                values.append(value.lower())
        if query:
            needle = f"%{query.lower()}%"
            clauses.append("(LOWER(name) LIKE ? OR LOWER(vendor) LIKE ? OR LOWER(catalog_number) LIKE ? OR LOWER(lot_number) LIKE ? OR LOWER(rrid) LIKE ? OR LOWER(barcode) LIKE ? OR LOWER(qr_code) LIKE ? OR LOWER(internal_label) LIKE ? OR LOWER(freezer_box) LIKE ? OR LOWER(freezer_position) LIKE ? OR LOWER(shelf) LIKE ? OR LOWER(room) LIKE ?)")
            values.extend([needle] * 12)
        workspace_clause, workspace_values = self._workspace_clause(workspace_id)
        if workspace_clause:
            clauses.append(workspace_clause)
            values.extend(workspace_values)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM inventory_items
                {where}
                ORDER BY name ASC, vendor ASC
                """,
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def lookup_inventory_item_by_code(
        self,
        code: str,
        workspace_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Find an inventory item by barcode, QR code, or internal label."""

        clauses = ["(barcode = ? OR qr_code = ? OR internal_label = ?)"]
        values: list[Any] = [code, code, code]
        workspace_clause, workspace_values = self._workspace_clause(workspace_id)
        if workspace_clause:
            clauses.append(workspace_clause)
            values.extend(workspace_values)
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT *
                FROM inventory_items
                WHERE {' AND '.join(clauses)}
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                values,
            ).fetchone()
        return dict(row) if row else None

    def get_inventory_item(self, item_id: str) -> dict[str, Any] | None:
        """Return one inventory item."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM inventory_items WHERE item_id = ?",
                (item_id,),
            ).fetchone()
        return dict(row) if row else None

    def delete_inventory_item(self, item_id: str) -> bool:
        """Delete one inventory item."""

        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM inventory_items WHERE item_id = ?", (item_id,))
        return cursor.rowcount > 0

    def record_inventory_usage(
        self,
        inventory_item_id: str,
        experiment_id: str,
        session_id: str | None = None,
        protocol_id: str | None = None,
        amount_used: float | None = None,
        units: str | None = None,
        date_used: str | None = None,
        used_by: str | None = None,
        purpose: str | None = None,
        notes: str | None = None,
        decrement_quantity: bool = False,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Record where an inventory item was used."""

        usage_id = f"inventory-usage:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            item = connection.execute(
                "SELECT quantity, workspace_id FROM inventory_items WHERE item_id = ?",
                (inventory_item_id,),
            ).fetchone()
            if item is None:
                raise ValueError(f"Inventory item not found: {inventory_item_id}")
            resolved_workspace = workspace_id or item["workspace_id"]
            connection.execute(
                """
                INSERT INTO inventory_usage (
                    usage_id, inventory_item_id, experiment_id, session_id,
                    protocol_id, amount_used, units, date_used, used_by,
                    purpose, notes, workspace_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usage_id,
                    inventory_item_id,
                    experiment_id,
                    session_id,
                    protocol_id,
                    amount_used,
                    units,
                    date_used,
                    used_by,
                    purpose,
                    notes,
                    resolved_workspace,
                ),
            )
            if decrement_quantity and amount_used is not None and item["quantity"] is not None:
                new_quantity = max(0.0, float(item["quantity"]) - float(amount_used))
                connection.execute(
                    """
                    UPDATE inventory_items
                    SET quantity = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE item_id = ?
                    """,
                    (new_quantity, inventory_item_id),
                )
        saved = self.get_inventory_usage(usage_id)
        if saved is None:
            raise RuntimeError(f"Inventory usage was not saved: {usage_id}")
        return saved

    def get_inventory_usage(self, usage_id: str) -> dict[str, Any] | None:
        """Return one inventory usage record."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT u.*, i.name AS inventory_item_name, i.vendor, i.catalog_number, i.lot_number, i.rrid
                FROM inventory_usage u
                LEFT JOIN inventory_items i ON i.item_id = u.inventory_item_id
                WHERE u.usage_id = ?
                """,
                (usage_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_inventory_usage_for_item(
        self,
        inventory_item_id: str,
        workspace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return usage history for one inventory item."""

        clauses = ["u.inventory_item_id = ?"]
        values: list[Any] = [inventory_item_id]
        if workspace_id:
            clauses.append("(u.workspace_id = ? OR u.workspace_id IS NULL OR u.workspace_id = '')")
            values.append(workspace_id)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT u.*, i.name AS inventory_item_name, i.vendor, i.catalog_number, i.lot_number, i.rrid
                FROM inventory_usage u
                LEFT JOIN inventory_items i ON i.item_id = u.inventory_item_id
                WHERE {' AND '.join(clauses)}
                ORDER BY COALESCE(u.date_used, u.created_at) DESC
                """,
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def list_inventory_usage_for_experiment(
        self,
        experiment_id: str,
        workspace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return inventory usage records for an experiment reference."""

        clauses = ["u.experiment_id = ?"]
        values: list[Any] = [experiment_id]
        if workspace_id:
            clauses.append("(u.workspace_id = ? OR u.workspace_id IS NULL OR u.workspace_id = '')")
            values.append(workspace_id)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT u.*, i.name AS inventory_item_name, i.vendor, i.catalog_number, i.lot_number, i.rrid
                FROM inventory_usage u
                LEFT JOIN inventory_items i ON i.item_id = u.inventory_item_id
                WHERE {' AND '.join(clauses)}
                ORDER BY COALESCE(u.date_used, u.created_at) DESC
                """,
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def save_purchase_record(
        self,
        item_name: str,
        vendor: str | None = None,
        catalog_number: str | None = None,
        purchase_date: str | None = None,
        cost: float | None = None,
        quantity: float | None = None,
        grant_or_funding_source: str | None = None,
        purchaser: str | None = None,
        oracle_po_number: str | None = None,
        invoice_number: str | None = None,
        status: str | None = None,
        notes: str | None = None,
        purchase_id: str | None = None,
        owner_user_id: str | None = None,
        created_by: str | None = None,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Create or update one purchase record."""

        resolved_id = purchase_id or f"purchase:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT created_at FROM purchase_records WHERE purchase_id = ?",
                (resolved_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO purchase_records (
                        purchase_id, item_name, vendor, catalog_number, purchase_date,
                        cost, quantity, grant_or_funding_source, purchaser,
                        oracle_po_number, invoice_number, status, notes,
                        owner_user_id, created_by, workspace_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        resolved_id,
                        item_name,
                        vendor,
                        catalog_number,
                        purchase_date,
                        cost,
                        quantity,
                        grant_or_funding_source,
                        purchaser,
                        oracle_po_number,
                        invoice_number,
                        status,
                        notes,
                        owner_user_id,
                        created_by or owner_user_id,
                        workspace_id,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE purchase_records
                    SET item_name = ?,
                        vendor = ?,
                        catalog_number = ?,
                        purchase_date = ?,
                        cost = ?,
                        quantity = ?,
                        grant_or_funding_source = ?,
                        purchaser = ?,
                        oracle_po_number = ?,
                        invoice_number = ?,
                        status = ?,
                        notes = ?,
                        owner_user_id = COALESCE(?, owner_user_id),
                        created_by = COALESCE(?, created_by),
                        workspace_id = COALESCE(?, workspace_id),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE purchase_id = ?
                    """,
                    (
                        item_name,
                        vendor,
                        catalog_number,
                        purchase_date,
                        cost,
                        quantity,
                        grant_or_funding_source,
                        purchaser,
                        oracle_po_number,
                        invoice_number,
                        status,
                        notes,
                        owner_user_id,
                        created_by or owner_user_id,
                        workspace_id,
                        resolved_id,
                    ),
                )
        saved = self.get_purchase_record(resolved_id)
        if saved is None:
            raise RuntimeError(f"Purchase record was not saved: {resolved_id}")
        return saved

    def list_purchase_records(
        self,
        vendor: str | None = None,
        grant_or_funding_source: str | None = None,
        status: str | None = None,
        query: str | None = None,
        workspace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return purchase records with optional filters."""

        clauses: list[str] = []
        values: list[str] = []
        for column, value in [("vendor", vendor), ("grant_or_funding_source", grant_or_funding_source), ("status", status)]:
            if value:
                clauses.append(f"LOWER({column}) = ?")
                values.append(value.lower())
        if query:
            needle = f"%{query.lower()}%"
            clauses.append("(LOWER(item_name) LIKE ? OR LOWER(vendor) LIKE ? OR LOWER(catalog_number) LIKE ? OR LOWER(oracle_po_number) LIKE ? OR LOWER(invoice_number) LIKE ?)")
            values.extend([needle, needle, needle, needle, needle])
        workspace_clause, workspace_values = self._workspace_clause(workspace_id)
        if workspace_clause:
            clauses.append(workspace_clause)
            values.extend(workspace_values)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM purchase_records
                {where}
                ORDER BY COALESCE(purchase_date, created_at) DESC, item_name ASC
                """,
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def get_purchase_record(self, purchase_id: str) -> dict[str, Any] | None:
        """Return one purchase record."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM purchase_records WHERE purchase_id = ?",
                (purchase_id,),
            ).fetchone()
        return dict(row) if row else None

    def save_purchase_request(
        self,
        item_name: str,
        vendor: str | None = None,
        catalog_number: str | None = None,
        quantity_requested: float | None = None,
        estimated_cost: float | None = None,
        grant_or_funding_source: str | None = None,
        requested_by: str | None = None,
        request_date: str | None = None,
        status: str | None = "draft",
        notes: str | None = None,
        linked_inventory_item_id: str | None = None,
        request_id: str | None = None,
        owner_user_id: str | None = None,
        created_by: str | None = None,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a lab purchase request."""

        resolved_id = request_id or f"purchase-request:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT created_at FROM purchase_requests WHERE request_id = ?",
                (resolved_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO purchase_requests (
                        request_id, item_name, vendor, catalog_number,
                        quantity_requested, estimated_cost, grant_or_funding_source,
                        requested_by, request_date, status, notes,
                        linked_inventory_item_id, owner_user_id, created_by,
                        workspace_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        resolved_id,
                        item_name,
                        vendor,
                        catalog_number,
                        quantity_requested,
                        estimated_cost,
                        grant_or_funding_source,
                        requested_by,
                        request_date,
                        status or "draft",
                        notes,
                        linked_inventory_item_id,
                        owner_user_id,
                        created_by or owner_user_id,
                        workspace_id,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE purchase_requests
                    SET item_name = ?,
                        vendor = ?,
                        catalog_number = ?,
                        quantity_requested = ?,
                        estimated_cost = ?,
                        grant_or_funding_source = ?,
                        requested_by = ?,
                        request_date = ?,
                        status = ?,
                        notes = ?,
                        linked_inventory_item_id = ?,
                        owner_user_id = COALESCE(?, owner_user_id),
                        created_by = COALESCE(?, created_by),
                        workspace_id = COALESCE(?, workspace_id),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE request_id = ?
                    """,
                    (
                        item_name,
                        vendor,
                        catalog_number,
                        quantity_requested,
                        estimated_cost,
                        grant_or_funding_source,
                        requested_by,
                        request_date,
                        status or "draft",
                        notes,
                        linked_inventory_item_id,
                        owner_user_id,
                        created_by or owner_user_id,
                        workspace_id,
                        resolved_id,
                    ),
                )
        saved = self.get_purchase_request(resolved_id)
        if saved is None:
            raise RuntimeError(f"Purchase request was not saved: {resolved_id}")
        return saved

    def list_purchase_requests(
        self,
        status: str | None = None,
        query: str | None = None,
        linked_inventory_item_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return lab purchase requests with optional filters."""

        clauses: list[str] = []
        values: list[Any] = []
        if status:
            clauses.append("LOWER(status) = ?")
            values.append(status.lower())
        if linked_inventory_item_id:
            clauses.append("linked_inventory_item_id = ?")
            values.append(linked_inventory_item_id)
        if query:
            needle = f"%{query.lower()}%"
            clauses.append(
                "(LOWER(item_name) LIKE ? OR LOWER(vendor) LIKE ? OR LOWER(catalog_number) LIKE ? OR LOWER(grant_or_funding_source) LIKE ? OR LOWER(requested_by) LIKE ?)"
            )
            values.extend([needle] * 5)
        workspace_clause, workspace_values = self._workspace_clause(workspace_id)
        if workspace_clause:
            clauses.append(workspace_clause)
            values.extend(workspace_values)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM purchase_requests
                {where}
                ORDER BY COALESCE(request_date, created_at) DESC, item_name ASC
                """,
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def get_purchase_request(self, request_id: str) -> dict[str, Any] | None:
        """Return one lab purchase request."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM purchase_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_inventory_quantity(
        self,
        item_id: str,
        quantity_delta: float,
    ) -> dict[str, Any] | None:
        """Adjust inventory quantity by a positive or negative delta."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT quantity FROM inventory_items WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            if row is None:
                return None
            current = float(row["quantity"] or 0)
            connection.execute(
                """
                UPDATE inventory_items
                SET quantity = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE item_id = ?
                """,
                (current + float(quantity_delta), item_id),
            )
        return self.get_inventory_item(item_id)

    def save_purchase_import_template(
        self,
        name: str,
        mapping: dict[str, str],
        provider: str | None = "oracle_purchasing",
        template_id: str | None = None,
        owner_user_id: str | None = None,
        created_by: str | None = None,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a saved purchasing import mapping template."""

        resolved_id = template_id or f"purchase_import_template:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT created_at FROM purchase_import_templates WHERE template_id = ?",
                (resolved_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO purchase_import_templates (
                        template_id, name, provider, mapping,
                        owner_user_id, created_by, workspace_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        resolved_id,
                        name,
                        provider,
                        json.dumps(mapping, sort_keys=True),
                        owner_user_id,
                        created_by or owner_user_id,
                        workspace_id,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE purchase_import_templates
                    SET name = ?,
                        provider = ?,
                        mapping = ?,
                        owner_user_id = COALESCE(?, owner_user_id),
                        created_by = COALESCE(?, created_by),
                        workspace_id = COALESCE(?, workspace_id),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE template_id = ?
                    """,
                    (
                        name,
                        provider,
                        json.dumps(mapping, sort_keys=True),
                        owner_user_id,
                        created_by or owner_user_id,
                        workspace_id,
                        resolved_id,
                    ),
                )
        saved = self.get_purchase_import_template(resolved_id)
        if saved is None:
            raise RuntimeError(f"Purchase import template was not saved: {resolved_id}")
        return saved

    def list_purchase_import_templates(self, workspace_id: str | None = None) -> list[dict[str, Any]]:
        """Return saved purchasing import mapping templates."""

        workspace_clause, workspace_values = self._workspace_clause(workspace_id)
        where = f"WHERE {workspace_clause}" if workspace_clause else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM purchase_import_templates
                {where}
                ORDER BY name ASC
                """,
                workspace_values,
            ).fetchall()
        templates = [dict(row) for row in rows]
        for template in templates:
            template["mapping"] = json.loads(template.get("mapping") or "{}")
            template["is_default"] = False
        return templates

    def get_purchase_import_template(self, template_id: str) -> dict[str, Any] | None:
        """Return one saved purchasing import mapping template."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM purchase_import_templates WHERE template_id = ?",
                (template_id,),
            ).fetchone()
        if not row:
            return None
        template = dict(row)
        template["mapping"] = json.loads(template.get("mapping") or "{}")
        template["is_default"] = False
        return template

    def delete_purchase_import_template(self, template_id: str) -> bool:
        """Delete one saved purchasing import mapping template."""

        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM purchase_import_templates WHERE template_id = ?",
                (template_id,),
            )
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
        owner_user_id: str | None = None,
        created_by: str | None = None,
        workspace_id: str | None = None,
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
                        provider, path, metadata_json, owner_user_id, created_by, workspace_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        owner_user_id,
                        created_by or owner_user_id,
                        workspace_id,
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
                        owner_user_id = COALESCE(?, owner_user_id),
                        created_by = COALESCE(?, created_by),
                        workspace_id = COALESCE(?, workspace_id),
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
                        owner_user_id,
                        created_by or owner_user_id,
                        workspace_id,
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
        workspace_id: str | None = None,
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
        workspace_clause, workspace_values = self._workspace_clause(workspace_id)
        if workspace_clause:
            clauses.append(workspace_clause)
            values.extend(workspace_values)

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

    def _resource_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Deserialize a resource row into API-ready fields."""

        record = dict(row)
        record["aliases"] = json.loads(record.pop("aliases_json") or "[]")
        record["metadata"] = json.loads(record.pop("metadata_json") or "{}")
        record["usages"] = self.resource_usages(str(record["resource_id"]))
        return record

    def _resource_usage_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Deserialize a resource usage row."""

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

    def _workspace_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Deserialize a lab workspace row."""

        record = dict(row)
        record["settings"] = json.loads(record.pop("settings_json") or "{}")
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


def _dedupe_strings(values: list[str]) -> list[str]:
    """Return non-empty strings with case-insensitive deduplication."""

    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        clean = str(value).strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            output.append(clean)
    return output
