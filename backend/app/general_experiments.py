"""General-purpose experiment workspace and rich notebook foundation.

This module intentionally avoids organoid-specific assumptions. It models a
free-form notebook layer and a structured plan layer side by side; structured
data never overwrites narrative notes.
"""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlparse

from app.attachment_storage import SPREADSHEET_EXTENSIONS, classify_attachment_type
from app.authorization import AuthorizationService
from app.config import Settings
from app.storage import SQLiteStore

EXPERIMENT_ACCESS_ORDER = {"view": 1, "comment": 2, "edit": 3, "manage": 4}
CANONICAL_BLANK_DELTA_JSON = json.dumps([{"insert": "\n"}], separators=(",", ":"))
NOTEBOOK_SCHEMA_VERSION = 1
NOTEBOOK_MIGRATION_VERSION = 2
logger = logging.getLogger(__name__)


class ExperimentAuthorizationError(PermissionError):
    """Raised when a user cannot access an experiment workspace."""


class ExperimentConflictError(RuntimeError):
    """Raised when optimistic concurrency detects a stale notebook save."""


class ExperimentValidationError(ValueError):
    """Raised for invalid experiment workspace requests."""


@dataclass(frozen=True)
class ExtractionProviderResult:
    """Future-ready extraction provider result."""

    proposed_cohorts: list[dict[str, Any]]
    proposed_conditions: list[dict[str, Any]]
    proposed_interventions: list[dict[str, Any]]
    proposed_events: list[dict[str, Any]]
    ambiguities: list[str]
    warnings: list[str]
    confidence_by_field: dict[str, float]


class ExperimentExtractionProvider:
    """Interface for future text, voice, document, or AI extraction."""

    def extract_from_text(self, source_text: str) -> ExtractionProviderResult:
        raise NotImplementedError

    def extract_from_transcript(self, source_text: str) -> ExtractionProviderResult:
        return self.extract_from_text(source_text)

    def reconcile_with_protocol(self, draft: dict[str, Any], protocol_version_id: str | None) -> dict[str, Any]:
        return draft | {"proposed_protocol_version_id": protocol_version_id}

    def validate_draft(self, draft: dict[str, Any]) -> dict[str, Any]:
        warnings = list(draft.get("warnings") or [])
        if not draft.get("source_text"):
            warnings.append("No source text provided.")
        return draft | {"warnings": warnings}


class DeterministicExperimentExtractionProvider(ExperimentExtractionProvider):
    """Small deterministic provider for demos and tests; no LLM calls."""

    def extract_from_text(self, source_text: str) -> ExtractionProviderResult:
        lowered = source_text.lower()
        conditions = []
        for term in ["untreated", "dmso", "vehicle", "control"]:
            if term in lowered:
                conditions.append({"name": term.upper() if term == "dmso" else term, "condition_type": "vehicle_control" if term in {"dmso", "vehicle"} else "untreated"})
        events = []
        for token in source_text.replace(",", " ").split():
            if token.upper().startswith("D") and token[1:].isdigit():
                events.append({"title": f"Event on {token.upper()}", "event_type": "milestone", "day": int(token[1:]), "source": "generated"})
        return ExtractionProviderResult(
            proposed_cohorts=[],
            proposed_conditions=conditions,
            proposed_interventions=[],
            proposed_events=events,
            ambiguities=[],
            warnings=["Deterministic draft only; researcher confirmation required."],
            confidence_by_field={"conditions": 0.45, "events": 0.4},
        )


class SamplePlanningService:
    """Explainable sample-planning preview without inventing recommendations."""

    def preview(self, assumptions: dict[str, Any]) -> dict[str, Any]:
        required = ["biological_replicates", "technical_replicates", "sample_units_per_replicate"]
        missing = [field for field in required if assumptions.get(field) in (None, "", 0)]
        if missing:
            return {
                "status": "incomplete",
                "assumptions": assumptions,
                "missing_values": missing,
                "calculation_preview": None,
                "message": "Sample counts are not calculated until required inputs are provided.",
            }
        biological = float(assumptions["biological_replicates"])
        technical = float(assumptions["technical_replicates"])
        units = float(assumptions["sample_units_per_replicate"])
        attrition = float(assumptions.get("expected_attrition_percent") or 0) / 100.0
        reserve = float(assumptions.get("reserve_percent") or 0) / 100.0
        base = biological * technical * units
        adjusted = base * (1 + attrition + reserve)
        return {
            "status": "preview",
            "assumptions": assumptions,
            "missing_values": [],
            "calculation_preview": {
                "base_units": base,
                "attrition_percent": attrition * 100,
                "reserve_percent": reserve * 100,
                "estimated_units": adjusted,
                "formula": "biological_replicates * technical_replicates * sample_units_per_replicate * (1 + attrition + reserve)",
            },
            "message": "Preview only. Final optimization is intentionally not implemented yet.",
        }


class GeneralExperimentService:
    """General experiment workspace repository and authorization boundary."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = SQLiteStore(settings=settings)
        self.authz = AuthorizationService(settings=settings)
        self._ensure_schema()
        self.ensure_demo_data()
        self.migrate_legacy_organoid_experiments()

    def _connect(self) -> sqlite3.Connection:
        return self.store._connect()

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS experiment_workspaces (
                    experiment_id TEXT PRIMARY KEY,
                    lab_id TEXT NOT NULL,
                    owner_user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    short_description TEXT,
                    status TEXT NOT NULL DEFAULT 'draft',
                    biological_system TEXT,
                    sample_unit_type TEXT,
                    sample_unit_label TEXT,
                    start_date TEXT,
                    nominal_day_zero TEXT,
                    expected_end_day INTEGER,
                    expected_end_date TEXT,
                    primary_protocol_id TEXT,
                    primary_protocol_version_id TEXT,
                    sort_index INTEGER,
                    archived_at TEXT,
                    archived_by TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS experiment_permissions (
                    permission_id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    principal_type TEXT NOT NULL,
                    principal_id TEXT NOT NULL,
                    access_level TEXT NOT NULL,
                    granted_by TEXT NOT NULL,
                    granted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS experiment_cohorts (
                    cohort_id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    start_day INTEGER,
                    start_date TEXT,
                    parent_cohort_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS experiment_conditions (
                    condition_id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    cohort_id TEXT,
                    name TEXT NOT NULL,
                    description TEXT,
                    condition_type TEXT NOT NULL DEFAULT 'custom',
                    replicate_count INTEGER,
                    sample_count_per_replicate INTEGER,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS experiment_interventions (
                    intervention_id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    cohort_id TEXT,
                    condition_id TEXT,
                    name TEXT NOT NULL,
                    intervention_type TEXT NOT NULL DEFAULT 'custom',
                    resource_id TEXT,
                    concentration_value REAL,
                    concentration_unit TEXT,
                    dilution TEXT,
                    dose_value REAL,
                    dose_unit TEXT,
                    duration_value REAL,
                    duration_unit TEXT,
                    route TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS experiment_events_general (
                    event_id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    cohort_id TEXT,
                    condition_id TEXT,
                    protocol_event_id TEXT,
                    event_type TEXT NOT NULL DEFAULT 'custom',
                    title TEXT NOT NULL,
                    description TEXT,
                    day INTEGER,
                    date TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    applies_to_all_conditions INTEGER NOT NULL DEFAULT 0,
                    destructive INTEGER,
                    completed_at TEXT,
                    completed_by TEXT,
                    source TEXT NOT NULL DEFAULT 'manual',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS experiment_assays (
                    assay_id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    event_id TEXT,
                    name TEXT NOT NULL,
                    assay_type TEXT NOT NULL,
                    destructive INTEGER NOT NULL DEFAULT 0,
                    sample_requirement TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS protocols_general (
                    protocol_id TEXT PRIMARY KEY,
                    lab_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    biological_system TEXT,
                    default_sample_unit TEXT,
                    current_version_id TEXT,
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS protocol_versions_general (
                    protocol_version_id TEXT PRIMARY KEY,
                    protocol_id TEXT NOT NULL,
                    version_label TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT,
                    approved_at TEXT,
                    approved_by TEXT
                );

                CREATE TABLE IF NOT EXISTS protocol_events_general (
                    protocol_event_id TEXT PRIMARY KEY,
                    protocol_version_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    day INTEGER,
                    relative_time TEXT,
                    event_type TEXT NOT NULL,
                    default_resource_id TEXT,
                    default_concentration TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS experiment_protocol_references (
                    experiment_id TEXT NOT NULL,
                    protocol_id TEXT NOT NULL,
                    protocol_version_id TEXT NOT NULL,
                    relationship TEXT NOT NULL DEFAULT 'primary',
                    inherited_events INTEGER NOT NULL DEFAULT 1,
                    added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    added_by TEXT,
                    PRIMARY KEY(experiment_id, protocol_version_id, relationship)
                );

                CREATE TABLE IF NOT EXISTS experiment_notebook_documents (
                    document_id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    document_format TEXT NOT NULL DEFAULT 'markdown',
                    content TEXT NOT NULL,
                    structured_content TEXT,
                    schema_version INTEGER NOT NULL DEFAULT 1,
                    document_version INTEGER NOT NULL DEFAULT 1,
                    original_format TEXT,
                    original_content TEXT,
                    migration_version INTEGER NOT NULL DEFAULT 0,
                    plain_text_cache TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_by TEXT
                );

                CREATE TABLE IF NOT EXISTS experiment_notebook_document_versions (
                    history_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    experiment_id TEXT NOT NULL,
                    document_version INTEGER NOT NULL,
                    document_format TEXT NOT NULL,
                    content TEXT NOT NULL,
                    structured_content TEXT,
                    plain_text_cache TEXT NOT NULL,
                    saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    saved_by TEXT
                );

                CREATE TABLE IF NOT EXISTS experiment_notebook_attachments (
                    attachment_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    attachment_type TEXT NOT NULL,
                    resource_id TEXT,
                    storage_reference TEXT,
                    display_name TEXT NOT NULL,
                    mime_type TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT
                );

                CREATE TABLE IF NOT EXISTS experiment_extraction_drafts (
                    extraction_id TEXT PRIMARY KEY,
                    experiment_id TEXT,
                    source_type TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    proposed_protocol_id TEXT,
                    proposed_protocol_version_id TEXT,
                    proposed_cohorts_json TEXT NOT NULL DEFAULT '[]',
                    proposed_conditions_json TEXT NOT NULL DEFAULT '[]',
                    proposed_interventions_json TEXT NOT NULL DEFAULT '[]',
                    proposed_events_json TEXT NOT NULL DEFAULT '[]',
                    ambiguities_json TEXT NOT NULL DEFAULT '[]',
                    warnings_json TEXT NOT NULL DEFAULT '[]',
                    confidence_by_field_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT
                );

                CREATE TABLE IF NOT EXISTS experiment_history_events (
                    history_id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    actor_user_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            for column, definition in {
                "sort_index": "INTEGER",
                "archived_at": "TEXT",
                "archived_by": "TEXT",
            }.items():
                self._ensure_column(connection, "experiment_workspaces", column, definition)
            self._backfill_experiment_order(connection)
            for column, definition in {
                "structured_content": "TEXT",
                "schema_version": "INTEGER NOT NULL DEFAULT 1",
                "document_version": "INTEGER NOT NULL DEFAULT 1",
                "original_format": "TEXT",
                "original_content": "TEXT",
                "migration_version": "INTEGER NOT NULL DEFAULT 0",
            }.items():
                self._ensure_column(connection, "experiment_notebook_documents", column, definition)
            for column, definition in {
                "experiment_id": "TEXT",
                "source_type": "TEXT NOT NULL DEFAULT 'uploaded_file'",
                "original_filename": "TEXT",
                "file_extension": "TEXT",
                "size_bytes": "INTEGER",
                "storage_path": "TEXT",
                "external_url": "TEXT",
                "description": "TEXT",
                "upload_status": "TEXT NOT NULL DEFAULT 'complete'",
                "processing_status": "TEXT NOT NULL DEFAULT 'not_started'",
                "updated_at": "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
                "checksum": "TEXT",
            }.items():
                self._ensure_column(connection, "experiment_notebook_attachments", column, definition)

    def ensure_demo_data(self) -> None:
        protocol = self.seed_protocol(
            lab_id="lab:demo",
            title="Meyer retinal organoid protocol",
            description="Generalized demo protocol for retinal organoid differentiation.",
            biological_system="retinal organoid",
            default_sample_unit="organoid",
            version_label="demo-v1",
            content="Meyer retinal organoid protocol demo. Includes BMP4 pulse on D6.",
            created_by="user:pi-owner",
            events=[
                {"title": "BMP4 on D6", "description": "Protocol-derived BMP4 event.", "day": 6, "event_type": "treatment", "default_concentration": "Needs protocol confirmation"},
            ],
        )
        experiment_id = "NK_Expt_26"
        if not self._workspace_exists(experiment_id):
            created = self._insert_workspace_if_missing(
                actor_user_id="user:researcher-a",
                lab_id="lab:demo",
                experiment_id=experiment_id,
                title="NK_Expt_26 generalized SAG timing experiment",
                short_description="Demo generalized experiment with early and late SAG cohorts.",
                status="planned",
                biological_system="retinal organoid",
                sample_unit_type="organoid",
                start_date=None,
                expected_end_day=90,
            )
            if not created:
                self.get_or_create_notebook("user:researcher-a", experiment_id)
                return
            self.link_protocol("user:researcher-a", experiment_id, protocol["protocol_id"], protocol["current_version_id"], inherit_events=True)
            early = self.add_cohort("user:researcher-a", experiment_id, {"name": "Early treatment cohort on D1", "start_day": 1})
            late = self.add_cohort("user:researcher-a", experiment_id, {"name": "Late treatment cohort on D9", "start_day": 9})
            for cohort in [early, late]:
                for name, kind in [
                    ("Untreated", "untreated"),
                    ("DMSO control", "vehicle_control"),
                    ("SAG 300 nM", "treatment"),
                    ("SAG 300 nM + GRKi 10 nM", "treatment"),
                ]:
                    condition = self.add_condition("user:researcher-a", experiment_id, {"cohort_id": cohort["cohort_id"], "name": name, "condition_type": kind})
                    if "SAG" in name:
                        self.add_intervention("user:researcher-a", experiment_id, {"cohort_id": cohort["cohort_id"], "condition_id": condition["condition_id"], "name": "SAG", "intervention_type": "compound", "concentration_value": 300, "concentration_unit": "nM"})
                    if "GRKi" in name:
                        self.add_intervention("user:researcher-a", experiment_id, {"cohort_id": cohort["cohort_id"], "condition_id": condition["condition_id"], "name": "GRKi", "intervention_type": "inhibition", "concentration_value": 10, "concentration_unit": "nM"})
            for title, day, event_type, cohort_id in [
                ("Untreated collection D1", 1, "collection", None),
                ("Early cohort collection D2", 2, "collection", early["cohort_id"]),
                ("Early cohort collection D3", 3, "collection", early["cohort_id"]),
                ("Late untreated baseline D9", 9, "collection", late["cohort_id"]),
                ("Late cohort collection D11", 11, "collection", late["cohort_id"]),
                ("Late cohort collection D13", 13, "collection", late["cohort_id"]),
                ("Imaging D16", 16, "imaging", None),
                ("Imaging D25", 25, "imaging", None),
                ("Imaging D35", 35, "imaging", None),
                ("Culture endpoint D90", 90, "endpoint", None),
            ]:
                self.add_event("user:researcher-a", experiment_id, {"title": title, "day": day, "event_type": event_type, "cohort_id": cohort_id, "applies_to_all_conditions": cohort_id is None})
            notebook = self.get_or_create_notebook("user:researcher-a", experiment_id)
            self.save_notebook(
                "user:researcher-a",
                notebook["document_id"],
                current_version=notebook["version"],
                content=(
                    "# NK_Expt_26 design\n\n"
                    "Generalized retinal organoid experiment comparing early D1 and late D9 SAG treatment windows.\n\n"
                    "## Conditions\n\n"
                    "- Untreated\n- DMSO control\n- SAG 300 nM\n- SAG 300 nM + GRKi 10 nM\n\n"
                    "Needs confirmation: likely 1:1000 final dilution for DMSO 1000x.\n"
                ),
                document_format="markdown",
            )
        else:
            self.get_or_create_notebook("user:pi-owner", experiment_id)

    def seed_protocol(self, lab_id: str, title: str, description: str, biological_system: str | None, default_sample_unit: str | None, version_label: str, content: str, created_by: str, events: list[dict[str, Any]]) -> dict[str, Any]:
        protocol_id = f"protocol:{_slug(title)}"
        version_id = f"protocol-version:{_slug(title)}:{_slug(version_label)}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO protocols_general
                    (protocol_id, lab_id, title, description, biological_system, default_sample_unit, current_version_id, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'approved')
                ON CONFLICT(protocol_id) DO UPDATE SET current_version_id = COALESCE(protocols_general.current_version_id, excluded.current_version_id)
                """,
                (protocol_id, lab_id, title, description, biological_system, default_sample_unit, version_id),
            )
            connection.execute(
                """
                INSERT INTO protocol_versions_general
                    (protocol_version_id, protocol_id, version_label, content, created_by, approved_at, approved_by)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(protocol_version_id) DO NOTHING
                """,
                (version_id, protocol_id, version_label, content, created_by, created_by),
            )
            for event in events:
                event_id = f"protocol-event:{version_id}:{_slug(str(event.get('title') or uuid.uuid4().hex))}"
                connection.execute(
                    """
                    INSERT INTO protocol_events_general
                        (protocol_event_id, protocol_version_id, title, description, day, relative_time, event_type, default_resource_id, default_concentration, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(protocol_event_id) DO NOTHING
                    """,
                    (
                        event_id,
                        version_id,
                        event.get("title"),
                        event.get("description"),
                        event.get("day"),
                        event.get("relative_time"),
                        event.get("event_type", "protocol_step"),
                        event.get("default_resource_id"),
                        event.get("default_concentration"),
                        json.dumps(event.get("metadata") or {}),
                    ),
                )
        return self.get_protocol(protocol_id) or {"protocol_id": protocol_id, "current_version_id": version_id}

    def migrate_legacy_organoid_experiments(self) -> None:
        """Compatibility wrapper for older callers/tests.

        Legacy extracted experiment rows are migrated into the notebook-first
        workspace tables. The source ``experiments`` rows remain available for
        provenance and alias resolution, but mobile/open/delete/reorder should
        operate on the generalized workspace after this runs.
        """

        for experiment in self.store.list_experiments():
            self._migrate_legacy_experiment_row(experiment)

    def create_blank_experiment(
        self,
        actor_user_id: str,
        lab_id: str,
        title: str,
        experiment_id: str | None = None,
        short_description: str | None = None,
        biological_system: str | None = None,
        sample_unit_type: str | None = None,
        start_date: str | None = None,
        expected_end_day: int | None = None,
        status: str = "draft",
    ) -> dict[str, Any]:
        self._require_lab_member(actor_user_id, lab_id)
        experiment_id = experiment_id or f"experiment:{uuid.uuid4().hex[:16]}"
        logger.info("Creating general experiment workspace", extra={"experiment_id": experiment_id, "lab_id": lab_id, "user_id": actor_user_id})
        if self._workspace_exists(experiment_id):
            raise ExperimentValidationError(f"Experiment already exists: {experiment_id}")
        created = self._insert_workspace_if_missing(
            actor_user_id=actor_user_id,
            lab_id=lab_id,
            experiment_id=experiment_id,
            title=title,
            short_description=short_description,
            status=status,
            biological_system=biological_system,
            sample_unit_type=sample_unit_type or "sample",
            start_date=start_date,
            expected_end_day=expected_end_day,
        )
        if not created:
            raise ExperimentValidationError(f"Experiment already exists: {experiment_id}")
        self.get_or_create_notebook(actor_user_id, experiment_id)
        workspace = self.get_workspace(experiment_id, actor_user_id)
        assert workspace is not None
        logger.info("Created general experiment workspace", extra={"experiment_id": experiment_id, "user_id": actor_user_id})
        return workspace["experiment"]

    def _insert_workspace_if_missing(
        self,
        *,
        actor_user_id: str,
        lab_id: str,
        experiment_id: str,
        title: str,
        short_description: str | None = None,
        status: str = "draft",
        biological_system: str | None = None,
        sample_unit_type: str | None = None,
        start_date: str | None = None,
        expected_end_day: int | None = None,
    ) -> bool:
        with self._connect() as connection:
            next_sort_index = self._next_sort_index(connection, lab_id)
            cursor = connection.execute(
                """
                INSERT INTO experiment_workspaces
                    (experiment_id, lab_id, owner_user_id, title, short_description, status, biological_system, sample_unit_type, start_date, nominal_day_zero, expected_end_day, sort_index)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(experiment_id) DO NOTHING
                """,
                (experiment_id, lab_id, actor_user_id, title, short_description, status, biological_system, sample_unit_type or "sample", start_date, start_date, expected_end_day, next_sort_index),
            )
            created = cursor.rowcount > 0
            if created:
                self._history(connection, experiment_id, actor_user_id, "experiment.created", {"status": status})
            return created

    def list_experiments(self, user_id: str, lab_id: str | None = None) -> list[dict[str, Any]]:
        """Return accessible generalized experiment workspaces newest first."""

        with self._connect() as connection:
            if lab_id:
                rows = connection.execute(
                    """
                    SELECT * FROM experiment_workspaces
                    WHERE lab_id = ? AND archived_at IS NULL
                    ORDER BY COALESCE(sort_index, 2147483647), updated_at DESC, created_at DESC
                    """,
                    (lab_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM experiment_workspaces
                    WHERE archived_at IS NULL
                    ORDER BY COALESCE(sort_index, 2147483647), updated_at DESC, created_at DESC
                    """
                ).fetchall()
        experiments = [_decode(row) for row in rows]
        accessible = [experiment for experiment in experiments if self.can_access(user_id, str(experiment.get("experiment_id")), "view")]
        logger.debug("Listed general experiment workspaces", extra={"count": len(accessible), "user_id": user_id, "lab_id": lab_id})
        return accessible

    def create_from_protocol(self, actor_user_id: str, protocol_id: str, protocol_version_id: str, title: str, lab_id: str = "lab:demo", experiment_id: str | None = None) -> dict[str, Any]:
        protocol = self.get_protocol(protocol_id)
        version = self.get_protocol_version(protocol_version_id)
        if protocol is None or version is None or version["protocol_id"] != protocol_id:
            raise ExperimentValidationError("Protocol version not found.")
        experiment = self.create_blank_experiment(
            actor_user_id=actor_user_id,
            lab_id=lab_id,
            title=title,
            experiment_id=experiment_id,
            biological_system=protocol.get("biological_system"),
            sample_unit_type=protocol.get("default_sample_unit") or "sample",
            status="planned",
        )
        self.link_protocol(actor_user_id, experiment["experiment_id"], protocol_id, protocol_version_id, inherit_events=True)
        return self.get_workspace(experiment["experiment_id"], actor_user_id)["experiment"]

    def link_protocol(self, actor_user_id: str, experiment_id: str, protocol_id: str, protocol_version_id: str, relationship: str = "primary", inherit_events: bool = True) -> dict[str, Any]:
        self._require_access(actor_user_id, experiment_id, "edit")
        protocol = self.get_protocol(protocol_id)
        version = self.get_protocol_version(protocol_version_id)
        if protocol is None or version is None:
            raise ExperimentValidationError("Protocol or version not found.")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO experiment_protocol_references
                    (experiment_id, protocol_id, protocol_version_id, relationship, inherited_events, added_by)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (experiment_id, protocol_id, protocol_version_id, relationship, 1 if inherit_events else 0, actor_user_id),
            )
            connection.execute(
                """
                UPDATE experiment_workspaces
                SET primary_protocol_id = ?, primary_protocol_version_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE experiment_id = ? AND ? = 'primary'
                """,
                (protocol_id, protocol_version_id, experiment_id, relationship),
            )
            self._history(connection, experiment_id, actor_user_id, "protocol.linked", {"protocol_id": protocol_id, "protocol_version_id": protocol_version_id})
            if inherit_events:
                for row in connection.execute("SELECT * FROM protocol_events_general WHERE protocol_version_id = ?", (protocol_version_id,)).fetchall():
                    event_id = f"event:{uuid.uuid4().hex}"
                    connection.execute(
                        """
                        INSERT INTO experiment_events_general
                            (event_id, experiment_id, protocol_event_id, event_type, title, description, day, source, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'protocol', ?)
                        """,
                        (
                            event_id,
                            experiment_id,
                            row["protocol_event_id"],
                            row["event_type"],
                            row["title"],
                            row["description"],
                            row["day"],
                            json.dumps({"protocol_version_id": protocol_version_id, "inherited": True}),
                        ),
                    )
                    self._history(connection, experiment_id, actor_user_id, "protocol_event.inherited", {"protocol_event_id": row["protocol_event_id"]})
        return {"experiment_id": experiment_id, "protocol_id": protocol_id, "protocol_version_id": protocol_version_id, "inherited_events": inherit_events}

    def update_experiment_title(self, actor_user_id: str, experiment_id: str, title: str) -> dict[str, Any]:
        experiment_id = self.resolve_experiment_id(experiment_id) or experiment_id
        self._require_access(actor_user_id, experiment_id, "edit")
        resolved_title = title.strip() or "Untitled Experiment"
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE experiment_workspaces
                SET title = ?, updated_at = CURRENT_TIMESTAMP
                WHERE experiment_id = ?
                """,
                (resolved_title, experiment_id),
            )
            self._history(connection, experiment_id, actor_user_id, "experiment.title_updated", {"title": resolved_title})
        experiment = self._experiment(experiment_id)
        if experiment is None:
            raise ExperimentValidationError("Experiment not found.")
        return experiment

    def delete_experiment(self, actor_user_id: str, experiment_id: str) -> dict[str, Any]:
        experiment_id = self.resolve_experiment_id(experiment_id) or experiment_id
        experiment = self._experiment(experiment_id)
        if experiment is None or experiment.get("archived_at"):
            raise ExperimentValidationError("Experiment not found.")
        if not self.can_access(actor_user_id, experiment_id, "manage"):
            raise ExperimentAuthorizationError("Experiment deletion requires manage access.")
        archived_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE experiment_workspaces
                SET status = 'archived',
                    archived_at = ?,
                    archived_by = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE experiment_id = ? AND archived_at IS NULL
                """,
                (archived_at, actor_user_id, experiment_id),
            )
            self._history(connection, experiment_id, actor_user_id, "experiment.archived", {"deletion_behavior": "soft_delete"})
        return {
            "deleted": True,
            "archived": True,
            "experiment_id": experiment_id,
            "archived_at": archived_at,
            "attachment_policy": "retained",
        }

    def reorder_experiments(self, actor_user_id: str, ordered_experiment_ids: list[str]) -> list[dict[str, Any]]:
        if not ordered_experiment_ids:
            raise ExperimentValidationError("At least one experiment id is required.")
        requested_ids = [str(item).strip() for item in ordered_experiment_ids if str(item).strip()]
        if len(requested_ids) != len(ordered_experiment_ids):
            raise ExperimentValidationError("Experiment ids must be non-empty.")
        normalized_ids = [self.resolve_experiment_id(item) or item for item in requested_ids]
        if len(set(normalized_ids)) != len(normalized_ids):
            raise ExperimentValidationError("Duplicate experiment ids are not allowed.")
        target_lab_id: str | None = None
        with self._connect() as connection:
            placeholders = ",".join("?" for _ in normalized_ids)
            rows = connection.execute(
                f"""
                SELECT * FROM experiment_workspaces
                WHERE experiment_id IN ({placeholders}) AND archived_at IS NULL
                """,
                normalized_ids,
            ).fetchall()
            experiments = [_decode(row) for row in rows]
            if len(experiments) != len(normalized_ids):
                raise ExperimentValidationError("Unknown experiment id in reorder request.")
            lab_ids = {str(experiment.get("lab_id") or "") for experiment in experiments}
            if len(lab_ids) != 1:
                raise ExperimentValidationError("Experiments must belong to the same lab.")
            target_lab_id = next(iter(lab_ids))
        for experiment_id in normalized_ids:
            if not self.can_access(actor_user_id, experiment_id, "manage"):
                raise ExperimentAuthorizationError("Experiment reorder requires manage access.")
        with self._connect() as connection:
            for index, experiment_id in enumerate(normalized_ids):
                connection.execute(
                    """
                    UPDATE experiment_workspaces
                    SET sort_index = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE experiment_id = ?
                    """,
                    ((index + 1) * 1000, experiment_id),
                )
            for experiment_id in normalized_ids:
                self._history(connection, experiment_id, actor_user_id, "experiment.reordered", {"position_count": len(normalized_ids)})
        return self.list_experiments(actor_user_id, lab_id=target_lab_id)

    def add_cohort(self, actor_user_id: str, experiment_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_access(actor_user_id, experiment_id, "edit")
        cohort_id = payload.get("cohort_id") or f"cohort:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO experiment_cohorts
                    (cohort_id, experiment_id, name, description, start_day, start_date, parent_cohort_id, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (cohort_id, experiment_id, payload["name"], payload.get("description"), payload.get("start_day"), payload.get("start_date"), payload.get("parent_cohort_id"), json.dumps(payload.get("metadata") or {})),
            )
            self._history(connection, experiment_id, actor_user_id, "cohort.added", {"cohort_id": cohort_id})
        return self._row_by_id("experiment_cohorts", "cohort_id", cohort_id)

    def add_condition(self, actor_user_id: str, experiment_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_access(actor_user_id, experiment_id, "edit")
        condition_id = payload.get("condition_id") or f"condition:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO experiment_conditions
                    (condition_id, experiment_id, cohort_id, name, description, condition_type, replicate_count, sample_count_per_replicate, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (condition_id, experiment_id, payload.get("cohort_id"), payload["name"], payload.get("description"), payload.get("condition_type", "custom"), payload.get("replicate_count"), payload.get("sample_count_per_replicate"), json.dumps(payload.get("metadata") or {})),
            )
            self._history(connection, experiment_id, actor_user_id, "condition.added", {"condition_id": condition_id})
        return self._row_by_id("experiment_conditions", "condition_id", condition_id)

    def add_intervention(self, actor_user_id: str, experiment_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_access(actor_user_id, experiment_id, "edit")
        intervention_id = payload.get("intervention_id") or f"intervention:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO experiment_interventions
                    (intervention_id, experiment_id, cohort_id, condition_id, name, intervention_type, resource_id, concentration_value, concentration_unit, dilution, dose_value, dose_unit, duration_value, duration_unit, route, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intervention_id,
                    experiment_id,
                    payload.get("cohort_id"),
                    payload.get("condition_id"),
                    payload["name"],
                    payload.get("intervention_type", "custom"),
                    payload.get("resource_id"),
                    payload.get("concentration_value"),
                    payload.get("concentration_unit"),
                    payload.get("dilution"),
                    payload.get("dose_value"),
                    payload.get("dose_unit"),
                    payload.get("duration_value"),
                    payload.get("duration_unit"),
                    payload.get("route"),
                    payload.get("notes"),
                ),
            )
            self._history(connection, experiment_id, actor_user_id, "intervention.added", {"intervention_id": intervention_id})
        return self._row_by_id("experiment_interventions", "intervention_id", intervention_id)

    def add_event(self, actor_user_id: str, experiment_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_access(actor_user_id, experiment_id, "edit")
        event_id = payload.get("event_id") or f"event:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO experiment_events_general
                    (event_id, experiment_id, cohort_id, condition_id, protocol_event_id, event_type, title, description, day, date, start_time, end_time, applies_to_all_conditions, destructive, source, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    experiment_id,
                    payload.get("cohort_id"),
                    payload.get("condition_id"),
                    payload.get("protocol_event_id"),
                    payload.get("event_type", "custom"),
                    payload["title"],
                    payload.get("description"),
                    payload.get("day"),
                    payload.get("date"),
                    payload.get("start_time"),
                    payload.get("end_time"),
                    1 if payload.get("applies_to_all_conditions") else 0,
                    None if payload.get("destructive") is None else 1 if payload.get("destructive") else 0,
                    payload.get("source", "manual"),
                    json.dumps(payload.get("metadata") or {}),
                ),
            )
            action = "event.added" if payload.get("source") != "protocol_override" else "protocol_event.overridden"
            self._history(connection, experiment_id, actor_user_id, action, {"event_id": event_id, "protocol_event_id": payload.get("protocol_event_id")})
        return self._row_by_id("experiment_events_general", "event_id", event_id)

    def get_workspace(self, experiment_id: str, user_id: str) -> dict[str, Any] | None:
        experiment_id = self.resolve_experiment_id(experiment_id) or experiment_id
        if not self.can_access(user_id, experiment_id, "view"):
            return None
        experiment = self._experiment(experiment_id)
        if experiment is None:
            return None
        notebook = self.get_or_create_notebook(user_id, experiment_id)
        attachments = self.list_attachments(user_id, experiment_id)
        return {
            "experiment": experiment,
            "overview": self._overview(experiment),
            "notebook": notebook,
            "attachments": attachments,
            "design": {
                "cohorts": self._rows("experiment_cohorts", experiment_id),
                "conditions": self._rows("experiment_conditions", experiment_id),
                "interventions": self._rows("experiment_interventions", experiment_id),
                "assays": self._rows("experiment_assays", experiment_id),
                "protocol_references": self._protocol_references(experiment_id),
            },
            "timeline": self.timeline(experiment_id, user_id),
            "sample_planning": SamplePlanningService().preview({"biological_replicates": None, "technical_replicates": None, "sample_units_per_replicate": None}),
            "sections": ["Overview", "Notebook", "Design", "Timeline", "Conditions", "Samples", "Plate Layout", "Tasks", "Data", "Chat", "History"],
            "layout": {
                "primary_surface": "notebook",
                "tools_open_as": "side_panel_or_bottom_sheet",
                "notebook_remains_visible": True,
            },
            "tool_palette": [
                {"tool_id": "copilot", "label": "Experiment Copilot", "icon": "auto_awesome", "mode": "panel"},
                {"tool_id": "protocols", "label": "Protocols", "icon": "description", "mode": "panel"},
                {"tool_id": "spreadsheet", "label": "Spreadsheet Import", "icon": "table_chart", "mode": "panel"},
                {"tool_id": "voice", "label": "Voice", "icon": "mic", "mode": "panel"},
                {"tool_id": "images", "label": "Images", "icon": "photo_camera", "mode": "panel"},
                {"tool_id": "attachments", "label": "Attachments", "icon": "attach_file", "mode": "panel"},
                {"tool_id": "timeline", "label": "Timeline", "icon": "event", "mode": "panel"},
                {"tool_id": "conditions", "label": "Conditions", "icon": "science", "mode": "panel"},
                {"tool_id": "samples", "label": "Samples", "icon": "blur_circular", "mode": "panel"},
                {"tool_id": "inventory", "label": "Inventory", "icon": "inventory_2", "mode": "panel"},
                {"tool_id": "chat", "label": "Chat", "icon": "chat", "mode": "panel"},
                {"tool_id": "analysis", "label": "Analysis", "icon": "analytics", "mode": "panel"},
                {"tool_id": "literature", "label": "Literature", "icon": "menu_book", "mode": "panel"},
                {"tool_id": "memory", "label": "Scientific Memory", "icon": "psychology", "mode": "panel"},
                {"tool_id": "whiteboard", "label": "Whiteboard", "icon": "view_quilt", "mode": "panel"},
            ],
            "empty_states": {
                "plate_layout": "Plate layouts are optional and only needed for plate-based experiments.",
                "tasks": "Task integration is future-ready.",
                "data": "Attach data assets as they are generated.",
                "chat": "Use Lab Chat to discuss this experiment with authorized collaborators.",
            },
        }

    def timeline(self, experiment_id: str, user_id: str) -> dict[str, Any]:
        self._require_access(user_id, experiment_id, "view")
        events = self._rows("experiment_events_general", experiment_id)
        events.sort(key=lambda item: (item.get("day") if item.get("day") is not None else 10**9, str(item.get("date") or ""), str(item.get("created_at") or "")))
        return {
            "experiment_id": experiment_id,
            "events": events,
            "export_interfaces": ["csv", "ics"],
            "ui_capabilities": ["horizontal_scroll", "event_details", "cohort_filter", "condition_filter", "add_event", "edit_event", "duplicate_event", "mark_complete"],
        }

    def get_or_create_notebook(self, user_id: str, experiment_id: str) -> dict[str, Any]:
        self._require_access(user_id, experiment_id, "view")
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM experiment_notebook_documents WHERE experiment_id = ? ORDER BY version DESC LIMIT 1", (experiment_id,)).fetchone()
            if row:
                return self._notebook_payload(connection, dict(row))
            document_id = f"experiment-notebook:{experiment_id}"
            experiment = self._experiment(experiment_id) or {}
            title = str(experiment.get("title") or experiment_id)
            content = canonical_notebook_delta_json("")
            connection.execute(
                """
                INSERT INTO experiment_notebook_documents
                    (document_id, experiment_id, title, document_format, content, structured_content,
                     plain_text_cache, original_format, original_content, migration_version, updated_by)
                VALUES (?, ?, ?, 'rich_text_delta_json', ?, ?, ?, '', '', ?, ?)
                """,
                (
                    document_id,
                    experiment_id,
                    title,
                    content,
                    content,
                    "",
                    NOTEBOOK_MIGRATION_VERSION,
                    user_id,
                ),
            )
            row = connection.execute("SELECT * FROM experiment_notebook_documents WHERE document_id = ?", (document_id,)).fetchone()
            assert row is not None
            return self._notebook_payload(connection, dict(row))

    def save_notebook(self, user_id: str, document_id: str, current_version: int, content: str, document_format: str = "markdown", title: str | None = None) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM experiment_notebook_documents WHERE document_id = ?", (document_id,)).fetchone()
            if row is None:
                raise ExperimentValidationError("Notebook document not found.")
            document = dict(row)
            self._require_access(user_id, str(document["experiment_id"]), "edit")
            if int(document["version"]) != current_version:
                raise ExperimentConflictError("Notebook has changed since it was loaded.")
            if len(content.encode("utf-8")) > 2_000_000:
                raise ExperimentValidationError("Notebook document is too large for this preview build.")
            normalized_format = _normalize_document_format(document_format)
            structured_content = canonical_notebook_delta_json(content=content, document_format=normalized_format)
            content_to_store = structured_content
            plain_text = _plain_text_from_document(structured_content, "rich_text_delta_json")
            connection.execute(
                """
                INSERT INTO experiment_notebook_document_versions
                    (history_id, document_id, experiment_id, document_version, document_format,
                     content, structured_content, plain_text_cache, saved_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"notebook-version:{uuid.uuid4().hex[:16]}",
                    document_id,
                    str(document["experiment_id"]),
                    int(document.get("version") or 1),
                    str(document.get("document_format") or "markdown"),
                    str(document.get("content") or ""),
                    document.get("structured_content"),
                    str(document.get("plain_text_cache") or ""),
                    user_id,
                ),
            )
            connection.execute(
                """
                UPDATE experiment_notebook_documents
                SET title = COALESCE(?, title), document_format = ?, content = ?,
                    structured_content = ?, plain_text_cache = ?, schema_version = ?,
                    migration_version = ?,
                    document_version = version + 1, version = version + 1,
                    updated_at = CURRENT_TIMESTAMP, updated_by = ?
                WHERE document_id = ?
                """,
                (
                    title,
                    "rich_text_delta_json",
                    content_to_store,
                    structured_content,
                    plain_text,
                    NOTEBOOK_SCHEMA_VERSION,
                    NOTEBOOK_MIGRATION_VERSION,
                    user_id,
                    document_id,
                ),
            )
            self._history(connection, str(document["experiment_id"]), user_id, "notebook.edited", {"document_id": document_id, "new_version": current_version + 1})
            updated = connection.execute("SELECT * FROM experiment_notebook_documents WHERE document_id = ?", (document_id,)).fetchone()
            assert updated is not None
            return self._notebook_payload(connection, dict(updated))

    def add_notebook_attachment(self, user_id: str, document_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            doc = connection.execute("SELECT * FROM experiment_notebook_documents WHERE document_id = ?", (document_id,)).fetchone()
            if doc is None:
                raise ExperimentValidationError("Notebook document not found.")
            self._require_access(user_id, str(doc["experiment_id"]), "edit")
            self._check_attachment_access(user_id, payload)
            attachment_id = f"notebook-attachment:{uuid.uuid4().hex[:16]}"
            connection.execute(
                """
                INSERT INTO experiment_notebook_attachments
                    (attachment_id, document_id, experiment_id, attachment_type, source_type, resource_id, storage_reference,
                     display_name, mime_type, metadata_json, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attachment_id,
                    document_id,
                    doc["experiment_id"],
                    payload.get("attachment_type"),
                    payload.get("source_type") or "researchos_resource",
                    payload.get("resource_id"),
                    payload.get("storage_reference"),
                    payload.get("display_name") or payload.get("resource_id") or "Attachment",
                    payload.get("mime_type"),
                    json.dumps(payload.get("metadata") or {}),
                    user_id,
                ),
            )
            self._history(connection, str(doc["experiment_id"]), user_id, "attachment.added", {"attachment_id": attachment_id, "attachment_type": payload.get("attachment_type")})
        return self._row_by_id("experiment_notebook_attachments", "attachment_id", attachment_id)

    def record_uploaded_attachment(self, user_id: str, experiment_id: str, stored: dict[str, Any], display_name: str | None = None, description: str | None = None, attachment_type: str | None = None) -> dict[str, Any]:
        self._require_access(user_id, experiment_id, "edit")
        notebook = self.get_or_create_notebook(user_id, experiment_id)
        resolved_type = attachment_type or classify_attachment_type(str(stored.get("original_filename") or stored.get("safe_filename") or ""), stored.get("mime_type"))
        metadata = self._attachment_processing_metadata(str(stored.get("file_extension") or ""), int(stored.get("size_bytes") or 0))
        attachment_id = f"experiment-attachment:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO experiment_notebook_attachments
                    (attachment_id, document_id, experiment_id, attachment_type, source_type, storage_reference, storage_path,
                     display_name, original_filename, mime_type, file_extension, size_bytes, description, upload_status,
                     processing_status, checksum, metadata_json, created_by, updated_at)
                VALUES (?, ?, ?, ?, 'uploaded_file', ?, ?, ?, ?, ?, ?, ?, ?, 'complete', ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    attachment_id,
                    notebook["document_id"],
                    experiment_id,
                    resolved_type,
                    stored.get("storage_path"),
                    stored.get("storage_path"),
                    display_name or stored.get("original_filename") or "Attachment",
                    stored.get("original_filename"),
                    stored.get("mime_type"),
                    stored.get("file_extension"),
                    stored.get("size_bytes"),
                    description,
                    metadata["processing_status"],
                    stored.get("checksum"),
                    json.dumps(metadata),
                    user_id,
                ),
            )
            self._history(connection, experiment_id, user_id, "attachment.uploaded", {"attachment_id": attachment_id, "attachment_type": resolved_type})
        logger.info("Stored experiment attachment metadata", extra={"experiment_id": experiment_id, "attachment_id": attachment_id, "user_id": user_id})
        return self.get_attachment(user_id, attachment_id)

    def create_link_attachment(self, user_id: str, experiment_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_access(user_id, experiment_id, "edit")
        url = str(payload.get("external_url") or payload.get("url") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ExperimentValidationError("Attachment link must be a valid HTTP or HTTPS URL.")
        notebook = self.get_or_create_notebook(user_id, experiment_id)
        provider = _link_provider(url)
        attachment_type = str(payload.get("attachment_type") or provider.get("attachment_type") or "external_link")
        display_name = str(payload.get("display_name") or provider.get("display_name") or parsed.netloc)
        attachment_id = f"experiment-attachment:{uuid.uuid4().hex[:16]}"
        metadata = {"provider": provider.get("provider"), "host": parsed.netloc}
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO experiment_notebook_attachments
                    (attachment_id, document_id, experiment_id, attachment_type, source_type, display_name, external_url,
                     description, upload_status, processing_status, metadata_json, created_by, updated_at)
                VALUES (?, ?, ?, ?, 'external_link', ?, ?, ?, 'complete', 'not_started', ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    attachment_id,
                    notebook["document_id"],
                    experiment_id,
                    attachment_type,
                    display_name,
                    url,
                    payload.get("description"),
                    json.dumps(metadata),
                    user_id,
                ),
            )
            self._history(connection, experiment_id, user_id, "attachment.link_added", {"attachment_id": attachment_id, "provider": provider.get("provider")})
        logger.info("Created experiment link attachment", extra={"experiment_id": experiment_id, "attachment_id": attachment_id, "provider": provider.get("provider")})
        return self.get_attachment(user_id, attachment_id)

    def list_attachments(self, user_id: str, experiment_id: str) -> list[dict[str, Any]]:
        self._require_access(user_id, experiment_id, "view")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM experiment_notebook_attachments
                WHERE (experiment_id = ? OR document_id IN (SELECT document_id FROM experiment_notebook_documents WHERE experiment_id = ?))
                  AND COALESCE(upload_status, 'complete') != 'deleted'
                ORDER BY created_at DESC
                """,
                (experiment_id, experiment_id),
            ).fetchall()
        return [_decode(row) for row in rows]

    def get_attachment(self, user_id: str, attachment_id: str) -> dict[str, Any]:
        attachment = self._row_by_id("experiment_notebook_attachments", "attachment_id", attachment_id)
        experiment_id = str(attachment.get("experiment_id") or "")
        if not experiment_id:
            with self._connect() as connection:
                doc = connection.execute(
                    "SELECT experiment_id FROM experiment_notebook_documents WHERE document_id = ?",
                    (attachment.get("document_id"),),
                ).fetchone()
                experiment_id = str(doc["experiment_id"]) if doc else ""
        self._require_access(user_id, experiment_id, "view")
        return attachment | {"experiment_id": experiment_id}

    def update_attachment(self, user_id: str, attachment_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        attachment = self.get_attachment(user_id, attachment_id)
        experiment_id = str(attachment["experiment_id"])
        self._require_access(user_id, experiment_id, "edit")
        display_name = payload.get("display_name")
        description = payload.get("description")
        if display_name is not None and not str(display_name).strip():
            raise ExperimentValidationError("Display name cannot be empty.")
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE experiment_notebook_attachments
                SET display_name = COALESCE(?, display_name),
                    description = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE attachment_id = ?
                """,
                (str(display_name).strip() if display_name is not None else None, description, attachment_id),
            )
            self._history(connection, experiment_id, user_id, "attachment.updated", {"attachment_id": attachment_id})
        return self.get_attachment(user_id, attachment_id)

    def delete_attachment(self, user_id: str, attachment_id: str) -> dict[str, Any]:
        attachment = self.get_attachment(user_id, attachment_id)
        experiment_id = str(attachment["experiment_id"])
        self._require_access(user_id, experiment_id, "edit")
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE experiment_notebook_attachments
                SET upload_status = 'deleted', updated_at = CURRENT_TIMESTAMP
                WHERE attachment_id = ?
                """,
                (attachment_id,),
            )
            self._history(connection, experiment_id, user_id, "attachment.deleted", {"attachment_id": attachment_id})
        return {"attachment_id": attachment_id, "deleted": True, "storage_path": attachment.get("storage_path") or attachment.get("storage_reference")}

    def create_extraction_draft(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        provider = DeterministicExperimentExtractionProvider()
        source_text = str(payload.get("source_text") or "")
        result = provider.extract_from_text(source_text)
        extraction_id = f"extraction:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO experiment_extraction_drafts
                    (extraction_id, experiment_id, source_type, source_text, proposed_protocol_id, proposed_protocol_version_id,
                     proposed_cohorts_json, proposed_conditions_json, proposed_interventions_json, proposed_events_json,
                     ambiguities_json, warnings_json, confidence_by_field_json, status, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'awaiting_confirmation', ?)
                """,
                (
                    extraction_id,
                    payload.get("experiment_id"),
                    payload.get("source_type", "typed_text"),
                    source_text,
                    payload.get("proposed_protocol_id"),
                    payload.get("proposed_protocol_version_id"),
                    json.dumps(result.proposed_cohorts),
                    json.dumps(result.proposed_conditions),
                    json.dumps(result.proposed_interventions),
                    json.dumps(result.proposed_events),
                    json.dumps(result.ambiguities),
                    json.dumps(result.warnings),
                    json.dumps(result.confidence_by_field),
                    user_id,
                ),
            )
        return self._row_by_id("experiment_extraction_drafts", "extraction_id", extraction_id)

    def list_protocols(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [_decode(row) for row in connection.execute("SELECT * FROM protocols_general ORDER BY updated_at DESC").fetchall()]

    def get_protocol(self, protocol_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM protocols_general WHERE protocol_id = ?", (protocol_id,)).fetchone()
            if not row:
                return None
            payload = _decode(row)
            payload["versions"] = [_decode(item) for item in connection.execute("SELECT * FROM protocol_versions_general WHERE protocol_id = ? ORDER BY created_at DESC", (protocol_id,)).fetchall()]
            return payload

    def get_protocol_version(self, protocol_version_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM protocol_versions_general WHERE protocol_version_id = ?", (protocol_version_id,)).fetchone()
            if not row:
                return None
            payload = _decode(row)
            payload["events"] = [_decode(item) for item in connection.execute("SELECT * FROM protocol_events_general WHERE protocol_version_id = ? ORDER BY day", (protocol_version_id,)).fetchall()]
            return payload

    def create_protocol_version(self, actor_user_id: str, protocol_id: str, version_label: str, content: str, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        protocol = self.get_protocol(protocol_id)
        if protocol is None:
            raise ExperimentValidationError("Protocol not found.")
        version_id = f"protocol-version:{_slug(protocol_id)}:{_slug(version_label)}:{uuid.uuid4().hex[:8]}"
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO protocol_versions_general (protocol_version_id, protocol_id, version_label, content, created_by) VALUES (?, ?, ?, ?, ?)",
                (version_id, protocol_id, version_label, content, actor_user_id),
            )
            connection.execute("UPDATE protocols_general SET current_version_id = ?, updated_at = CURRENT_TIMESTAMP WHERE protocol_id = ?", (version_id, protocol_id))
            for event in events or []:
                connection.execute(
                    """
                    INSERT INTO protocol_events_general
                        (protocol_event_id, protocol_version_id, title, description, day, event_type, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (f"protocol-event:{uuid.uuid4().hex[:16]}", version_id, event.get("title"), event.get("description"), event.get("day"), event.get("event_type", "protocol_step"), json.dumps(event.get("metadata") or {})),
                )
        version = self.get_protocol_version(version_id)
        assert version is not None
        return version

    def can_access(self, user_id: str, experiment_id: str, access_level: str = "view") -> bool:
        experiment_id = self.resolve_experiment_id(experiment_id) or experiment_id
        experiment = self._experiment(experiment_id)
        if experiment is None:
            return False
        if experiment.get("archived_at"):
            return False
        if experiment["owner_user_id"] == user_id:
            return True
        lab_access = self.authz.user_access(user_id, str(experiment["lab_id"]))
        if access_level in {"edit", "manage"} and lab_access["role"] in {"owner", "admin"}:
            return True
        if "lab.notebooks.view_all" in lab_access["permissions"] and access_level == "view":
            return True
        required = EXPERIMENT_ACCESS_ORDER[access_level]
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM experiment_permissions WHERE experiment_id = ?", (experiment_id,)).fetchall()
        for row in rows:
            grant = dict(row)
            if EXPERIMENT_ACCESS_ORDER.get(grant["access_level"], 0) < required:
                continue
            if grant["principal_type"] == "user" and grant["principal_id"] == user_id:
                return True
            if grant["principal_type"] == "role" and grant["principal_id"] == lab_access["role"]:
                return True
        return False

    def grant_access(self, actor_user_id: str, experiment_id: str, principal_type: str, principal_id: str, access_level: str) -> dict[str, Any]:
        self._require_access(actor_user_id, experiment_id, "manage")
        permission_id = f"experiment-permission:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO experiment_permissions (permission_id, experiment_id, principal_type, principal_id, access_level, granted_by) VALUES (?, ?, ?, ?, ?, ?)",
                (permission_id, experiment_id, principal_type, principal_id, access_level, actor_user_id),
            )
        return self._row_by_id("experiment_permissions", "permission_id", permission_id)

    def _require_access(self, user_id: str, experiment_id: str, access_level: str) -> None:
        if not self.can_access(user_id, experiment_id, access_level):
            raise ExperimentAuthorizationError("Experiment not found or access denied.")

    def _require_lab_member(self, user_id: str, lab_id: str) -> None:
        if not self.authz.membership(user_id, lab_id):
            raise ExperimentAuthorizationError("Active lab membership required.")

    def _experiment(self, experiment_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM experiment_workspaces WHERE experiment_id = ?", (experiment_id,)).fetchone()
            return _decode(row) if row else None

    def _workspace_exists(self, experiment_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM experiment_workspaces WHERE experiment_id = ?",
                (experiment_id,),
            ).fetchone()
            return row is not None

    def resolve_experiment_id(self, identifier: str) -> str | None:
        candidate = str(identifier or "").strip()
        if not candidate:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT experiment_id FROM experiment_workspaces WHERE experiment_id = ?",
                (candidate,),
            ).fetchone()
            if row:
                return str(row["experiment_id"])
            legacy_row = self.store.get_experiment(candidate)
            if legacy_row is None:
                for legacy in self.store.list_experiments():
                    legacy_id = str(legacy.get("id") or "")
                    legacy_experiment_id = str(legacy.get("experiment_id") or "")
                    if candidate in {legacy_id, legacy_experiment_id}:
                        legacy_row = legacy
                        break
            if legacy_row is None:
                return None
            for alias in [
                str(legacy_row.get("experiment_id") or ""),
                str(legacy_row.get("id") or ""),
            ]:
                if not alias:
                    continue
                row = connection.execute(
                    "SELECT experiment_id FROM experiment_workspaces WHERE experiment_id = ?",
                    (alias,),
                ).fetchone()
                if row:
                    resolved_id = str(row["experiment_id"])
                    self._migrate_legacy_experiment_row(legacy_row)
                    return resolved_id
        return self._migrate_legacy_experiment_row(legacy_row)

    def _migrate_legacy_experiment_row(self, legacy_row: dict[str, Any]) -> str | None:
        canonical_id = str(legacy_row.get("experiment_id") or legacy_row.get("id") or "").strip()
        if not canonical_id:
            return None
        legacy_internal_id = str(legacy_row.get("id") or "").strip()
        title = str(legacy_row.get("title") or canonical_id)
        notes = str(legacy_row.get("notes") or "").strip()
        conclusions = str(legacy_row.get("conclusions") or "").strip()
        notebook_source = "\n\n".join(part for part in [notes, conclusions] if part)
        biological_system = "retinal organoid" if _mentions_organoid(legacy_row) else str(legacy_row.get("cell_line") or "experimental system")
        sample_unit_type = "organoid" if "organoid" in biological_system.lower() else "sample"
        owner_user_id = str(legacy_row.get("owner_user_id") or legacy_row.get("created_by") or "user:pi-owner")
        created_at = str(legacy_row.get("date") or legacy_row.get("extracted_at") or datetime.now(timezone.utc).isoformat())
        updated_at = str(legacy_row.get("extracted_at") or legacy_row.get("date") or created_at)
        status = str(legacy_row.get("status") or "active")
        metadata = {
            "legacy_source": "experiments",
            "legacy_internal_id": legacy_internal_id or None,
            "source_document_id": legacy_row.get("source_document_id"),
            "source_provider": legacy_row.get("source_provider"),
            "human_experiment_id": legacy_row.get("experiment_id"),
        }

        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM experiment_workspaces WHERE experiment_id = ?",
                (canonical_id,),
            ).fetchone()
            if existing is None:
                sort_index = self._next_sort_index(connection, "lab:demo")
                cursor = connection.execute(
                    """
                    INSERT INTO experiment_workspaces
                        (experiment_id, lab_id, owner_user_id, title, short_description, status,
                         biological_system, sample_unit_type, sort_index, created_at, updated_at)
                    VALUES (?, 'lab:demo', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(experiment_id) DO NOTHING
                    """,
                    (
                        canonical_id,
                        owner_user_id,
                        title,
                        notes or conclusions or None,
                        status,
                        biological_system,
                        sample_unit_type,
                        sort_index,
                        created_at,
                        updated_at,
                    ),
                )
                if cursor.rowcount > 0:
                    self._history(connection, canonical_id, owner_user_id, "experiment.legacy_migrated", metadata)
            else:
                existing_payload = _decode(existing)
                if not existing_payload.get("owner_user_id"):
                    connection.execute(
                        "UPDATE experiment_workspaces SET owner_user_id = ?, updated_at = COALESCE(updated_at, ?) WHERE experiment_id = ?",
                        (owner_user_id, updated_at, canonical_id),
                    )

            document_id = f"experiment-notebook:{canonical_id}"
            doc = connection.execute(
                "SELECT * FROM experiment_notebook_documents WHERE experiment_id = ? ORDER BY version DESC LIMIT 1",
                (canonical_id,),
            ).fetchone()
            if doc is None:
                structured_content = canonical_notebook_delta_json(notebook_source)
                plain_text = _plain_text_from_document(structured_content, "rich_text_delta_json")
                connection.execute(
                    """
                    INSERT INTO experiment_notebook_documents
                        (document_id, experiment_id, title, document_format, content, structured_content,
                         schema_version, original_format, original_content, migration_version,
                         plain_text_cache, created_at, updated_at, updated_by)
                    VALUES (?, ?, ?, 'rich_text_delta_json', ?, ?, ?, 'legacy_plain_text',
                            ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        canonical_id,
                        title,
                        structured_content,
                        structured_content,
                        NOTEBOOK_SCHEMA_VERSION,
                        notebook_source,
                        NOTEBOOK_MIGRATION_VERSION,
                        plain_text,
                        created_at,
                        updated_at,
                        owner_user_id,
                    ),
                )
            else:
                doc_payload = _decode(doc)
                canonical = canonical_notebook_delta_json(
                    content=doc_payload.get("content"),
                    structured_content=doc_payload.get("structured_content"),
                    document_format=str(doc_payload.get("document_format") or "markdown"),
                )
                plain_text = _plain_text_from_document(canonical, "rich_text_delta_json")
                needs_repair = (
                    doc_payload.get("document_format") != "rich_text_delta_json"
                    or doc_payload.get("content") != canonical
                    or doc_payload.get("structured_content") != canonical
                    or doc_payload.get("plain_text_cache") != plain_text
                    or int(doc_payload.get("migration_version") or 0) < NOTEBOOK_MIGRATION_VERSION
                )
                if needs_repair:
                    connection.execute(
                        """
                        UPDATE experiment_notebook_documents
                        SET document_format = 'rich_text_delta_json',
                            content = ?,
                            structured_content = ?,
                            plain_text_cache = ?,
                            schema_version = ?,
                            migration_version = ?,
                            original_format = COALESCE(original_format, ?),
                            original_content = COALESCE(original_content, ?)
                        WHERE document_id = ?
                        """,
                        (
                            canonical,
                            canonical,
                            plain_text,
                            NOTEBOOK_SCHEMA_VERSION,
                            NOTEBOOK_MIGRATION_VERSION,
                            str(doc_payload.get("document_format") or "markdown"),
                            str(doc_payload.get("content") or ""),
                            doc_payload["document_id"],
                        ),
                    )
            aliases = [alias for alias in {canonical_id, legacy_internal_id} if alias]
            if aliases:
                placeholders = ",".join("?" for _ in aliases)
                connection.execute(
                    f"""
                    UPDATE assets
                    SET experiment_id = ?,
                        owner_user_id = COALESCE(owner_user_id, ?),
                        created_by = COALESCE(created_by, ?),
                        workspace_id = COALESCE(workspace_id, 'workspace:demo-lab'),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE experiment_id IN ({placeholders})
                    """,
                    (canonical_id, owner_user_id, owner_user_id, *aliases),
                )
        return canonical_id

    def _next_sort_index(self, connection: sqlite3.Connection, lab_id: str) -> int:
        row = connection.execute(
            "SELECT COALESCE(MAX(sort_index), 0) AS max_sort FROM experiment_workspaces WHERE lab_id = ?",
            (lab_id,),
        ).fetchone()
        return int(row["max_sort"] or 0) + 1000

    def _backfill_experiment_order(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT experiment_id, lab_id
            FROM experiment_workspaces
            WHERE sort_index IS NULL
            ORDER BY lab_id, updated_at DESC, created_at DESC
            """
        ).fetchall()
        positions: dict[str, int] = {}
        for row in rows:
            lab_id = str(row["lab_id"])
            positions[lab_id] = positions.get(lab_id, 0) + 1000
            connection.execute(
                "UPDATE experiment_workspaces SET sort_index = ? WHERE experiment_id = ?",
                (positions[lab_id], row["experiment_id"]),
            )

    def _rows(self, table: str, experiment_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [_decode(row) for row in connection.execute(f"SELECT * FROM {table} WHERE experiment_id = ? ORDER BY created_at", (experiment_id,)).fetchall()]

    def _protocol_references(self, experiment_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [_decode(row) for row in connection.execute("SELECT * FROM experiment_protocol_references WHERE experiment_id = ? ORDER BY added_at", (experiment_id,)).fetchall()]

    def _notebook_payload(self, connection: sqlite3.Connection, row: dict[str, Any]) -> dict[str, Any]:
        attachments = [_decode(item) for item in connection.execute("SELECT * FROM experiment_notebook_attachments WHERE document_id = ? AND COALESCE(upload_status, 'complete') != 'deleted' ORDER BY created_at", (row["document_id"],)).fetchall()]
        payload = _decode(row)
        original_content = str(payload.get("content") or "")
        original_structured_content = payload.get("structured_content")
        original_plain_text = str(payload.get("plain_text_cache") or "")
        document_format = _normalize_document_format(str(payload.get("document_format") or "markdown"))
        structured_content = canonical_notebook_delta_json(
            content=original_content,
            structured_content=original_structured_content,
            document_format=document_format,
        )
        content = structured_content
        plain_text_cache = _plain_text_from_document(structured_content, "rich_text_delta_json")
        if (
            payload.get("document_format") != "rich_text_delta_json"
            or original_content != content
            or original_structured_content != structured_content
            or original_plain_text != plain_text_cache
            or int(payload.get("schema_version") or 0) < NOTEBOOK_SCHEMA_VERSION
            or int(payload.get("migration_version") or 0) < NOTEBOOK_MIGRATION_VERSION
        ):
            connection.execute(
                """
                UPDATE experiment_notebook_documents
                SET document_format = 'rich_text_delta_json',
                    content = ?,
                    structured_content = ?,
                    plain_text_cache = ?,
                    schema_version = ?,
                    migration_version = ?,
                    original_format = COALESCE(original_format, ?),
                    original_content = COALESCE(original_content, ?)
                WHERE document_id = ?
                """,
                (
                    content,
                    structured_content,
                    plain_text_cache,
                    NOTEBOOK_SCHEMA_VERSION,
                    NOTEBOOK_MIGRATION_VERSION,
                    document_format,
                    original_content,
                    payload["document_id"],
                ),
            )
            payload.update(
                {
                    "document_format": "rich_text_delta_json",
                    "content": content,
                    "structured_content": structured_content,
                    "plain_text_cache": plain_text_cache,
                    "schema_version": NOTEBOOK_SCHEMA_VERSION,
                    "migration_version": NOTEBOOK_MIGRATION_VERSION,
                }
            )
        document_format = "rich_text_delta_json"
        migration = {
            "source_format": "markdown_legacy" if _normalize_document_format(str(row.get("document_format") or "markdown")) in {"markdown", "html"} else document_format,
            "migration_version": int(payload.get("migration_version") or NOTEBOOK_MIGRATION_VERSION),
            "idempotent": True,
            "original_source_preserved": bool(payload.get("original_content") or original_content),
        }
        return payload | {
            "document_format": document_format,
            "content": content,
            "structured_content": structured_content,
            "schema_version": int(payload.get("schema_version") or NOTEBOOK_SCHEMA_VERSION),
            "document_version": int(payload.get("document_version") or payload.get("version") or 1),
            "plain_text_cache": plain_text_cache,
            "migration": migration,
            "attachments": attachments,
            "editor_capabilities": [
                "headings",
                "paragraphs",
                "bold",
                "italic",
                "underline",
                "strikethrough",
                "lists",
                "checklists",
                "quotes",
                "links",
                "attachments",
                "resource_links",
                "zoom",
            ],
        }

    def repair_notebook_delta_records(self, dry_run: bool = True, create_backup: bool = True) -> dict[str, Any]:
        """Repair locally stored notebook Delta records without exposing content."""

        repaired_ids: list[str] = []
        backup_path: str | None = None
        with self._connect() as connection:
            rows = [dict(row) for row in connection.execute("SELECT * FROM experiment_notebook_documents").fetchall()]
            repairs: list[tuple[dict[str, Any], str, str]] = []
            for row in rows:
                original_content = str(row.get("content") or "")
                original_structured = row.get("structured_content")
                canonical = canonical_notebook_delta_json(
                    content=original_content,
                    structured_content=original_structured,
                    document_format=str(row.get("document_format") or "markdown"),
                )
                plain_text = _plain_text_from_document(canonical, "rich_text_delta_json")
                needs_repair = (
                    row.get("document_format") != "rich_text_delta_json"
                    or original_content != canonical
                    or original_structured != canonical
                    or str(row.get("plain_text_cache") or "") != plain_text
                    or int(row.get("migration_version") or 0) < NOTEBOOK_MIGRATION_VERSION
                )
                if needs_repair:
                    repairs.append((row, canonical, plain_text))
                    repaired_ids.append(str(row["document_id"]))
            if repairs and not dry_run:
                if create_backup:
                    backup_path = self._backup_database_for_notebook_repair()
                for row, canonical, plain_text in repairs:
                    connection.execute(
                        """
                        UPDATE experiment_notebook_documents
                        SET document_format = 'rich_text_delta_json',
                            content = ?,
                            structured_content = ?,
                            plain_text_cache = ?,
                            schema_version = ?,
                            migration_version = ?,
                            original_format = COALESCE(original_format, ?),
                            original_content = COALESCE(original_content, ?)
                        WHERE document_id = ?
                        """,
                        (
                            canonical,
                            canonical,
                            plain_text,
                            NOTEBOOK_SCHEMA_VERSION,
                            NOTEBOOK_MIGRATION_VERSION,
                            str(row.get("document_format") or "markdown"),
                            str(row.get("content") or ""),
                            row["document_id"],
                        ),
                    )
        return {
            "dry_run": dry_run,
            "records_needing_repair": repaired_ids,
            "repaired_count": 0 if dry_run else len(repaired_ids),
            "backup_path": backup_path,
        }

    def _backup_database_for_notebook_repair(self) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = self.store.path.with_name(f"{self.store.path.stem}.notebook-repair-{timestamp}{self.store.path.suffix}.bak")
        shutil.copy2(self.store.path, backup_path)
        return str(backup_path)

    def _ensure_column(self, connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _attachment_processing_metadata(self, extension: str, size_bytes: int) -> dict[str, Any]:
        extension = extension.lower()
        metadata: dict[str, Any] = {"future_ai_actions": ["summarize_spreadsheet", "inspect_columns", "generate_experimental_design", "compare_experiments", "suggest_statistical_analyses", "generate_plots"]}
        if extension in SPREADSHEET_EXTENSIONS:
            metadata["file_format"] = extension.lstrip(".")
            metadata["spreadsheet_ready"] = True
            metadata["sheet_names"] = []
            metadata["row_count"] = None
            metadata["column_count"] = None
            metadata["processing_status_message"] = "Original spreadsheet retained; lightweight parsing is future-ready."
            processing_status = "metadata_pending"
        else:
            metadata["file_format"] = extension.lstrip(".") or "unknown"
            metadata["spreadsheet_ready"] = False
            processing_status = "not_applicable"
        metadata["size_bytes"] = size_bytes
        metadata["processing_status"] = processing_status
        return metadata

    def _row_by_id(self, table: str, key: str, value: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(f"SELECT * FROM {table} WHERE {key} = ?", (value,)).fetchone()
            if row is None:
                raise ExperimentValidationError(f"Missing row: {table}.{key}={value}")
            return _decode(row)

    def _overview(self, experiment: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": experiment.get("title"),
            "owner_user_id": experiment.get("owner_user_id"),
            "status": experiment.get("status"),
            "biological_system": experiment.get("biological_system"),
            "sample_unit_type": experiment.get("sample_unit_type"),
            "linked_protocol": experiment.get("primary_protocol_id"),
            "current_experimental_day": None,
            "alerts": [],
            "quick_actions": ["Write notes", "Open tools", "Attach data", "Ask Copilot"],
        }

    def _check_attachment_access(self, user_id: str, payload: dict[str, Any]) -> None:
        attachment_type = str(payload.get("attachment_type") or "")
        resource_id = payload.get("resource_id")
        if attachment_type == "notebook" and resource_id and not self.authz.can_user(user_id, "view", "notebook", str(resource_id)).allowed:
            raise ExperimentAuthorizationError("Attached notebook is not visible to this user.")
        if attachment_type == "experiment" and resource_id and not self.can_access(user_id, str(resource_id), "view"):
            raise ExperimentAuthorizationError("Attached experiment is not visible to this user.")

    def _history(self, connection: sqlite3.Connection, experiment_id: str, actor_user_id: str, action: str, metadata: dict[str, Any]) -> None:
        connection.execute(
            """
            INSERT INTO experiment_history_events (history_id, experiment_id, actor_user_id, action, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (f"history:{uuid.uuid4().hex[:16]}", experiment_id, actor_user_id, action, json.dumps(metadata)),
        )


def _decode(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    for key in list(payload):
        if key.endswith("_json"):
            target = key.removesuffix("_json")
            try:
                payload[target] = json.loads(payload[key] or "{}")
            except json.JSONDecodeError:
                payload[target] = payload[key]
    return payload


def _plain_text(content: str) -> str:
    return content.replace("#", "").replace("*", "").replace("|", " ")


def _normalize_document_format(value: str) -> str:
    normalized = (value or "markdown").strip().lower()
    if normalized in {"rich_text_json", "quill_delta", "delta", "rich_text_delta_json"}:
        return "rich_text_delta_json"
    if normalized == "html":
        return "html"
    return "markdown"


def _markdown_to_delta_json(markdown: str) -> str:
    repaired = _delta_json_from_text(markdown)
    if repaired is not None:
        return repaired
    ops: list[dict[str, Any]] = []
    lines = markdown.splitlines()
    if not lines:
        return CANONICAL_BLANK_DELTA_JSON
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("### "):
            ops.append({"insert": stripped[4:]})
            ops.append({"insert": "\n", "attributes": {"header": 3}})
        elif stripped.startswith("## "):
            ops.append({"insert": stripped[3:]})
            ops.append({"insert": "\n", "attributes": {"header": 2}})
        elif stripped.startswith("# "):
            ops.append({"insert": stripped[2:]})
            ops.append({"insert": "\n", "attributes": {"header": 1}})
        elif stripped.startswith("- ") or stripped.startswith("* "):
            ops.append({"insert": stripped[2:]})
            ops.append({"insert": "\n", "attributes": {"list": "bullet"}})
        else:
            ops.extend(_line_to_delta_ops(line))
            ops.append({"insert": "\n"})
    return _canonical_delta_json_from_ops(ops)


def _line_to_delta_ops(line: str) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    remaining = line
    while remaining:
        starts = [idx for idx in [remaining.find("http://"), remaining.find("https://")] if idx >= 0]
        if not starts:
            ops.append({"insert": remaining})
            break
        url_start = min(starts)
        if url_start:
            ops.append({"insert": remaining[:url_start]})
        tail = remaining[url_start:]
        parts = tail.split(maxsplit=1)
        url = parts[0]
        ops.append({"insert": url, "attributes": {"link": url}})
        remaining = parts[1] if len(parts) > 1 else ""
    return ops


def _plain_text_from_document(content: str, document_format: str) -> str:
    if _normalize_document_format(document_format) != "rich_text_delta_json":
        repaired = _delta_json_from_text(content)
        if repaired is None:
            return _plain_text(content)
        content = repaired
    decoded = _delta_ops_from_json_text(content)
    if decoded is None:
        return _plain_text(content)
    pieces: list[str] = []
    for op in decoded:
        if not isinstance(op, dict):
            continue
        inserted = op.get("insert")
        if isinstance(inserted, str):
            pieces.append(inserted)
        elif isinstance(inserted, dict):
            label = inserted.get("display_label") or inserted.get("source") or inserted.get("embed_type")
            if label:
                pieces.append(str(label))
    return " ".join("".join(pieces).split())


def _structured_delta_json_from_legacy(content: str, document_format: str) -> str:
    return canonical_notebook_delta_json(content=content, document_format=document_format)


def canonical_notebook_delta_json(
    content: Any = "",
    document_format: str = "markdown",
    structured_content: Any | None = None,
) -> str:
    """Return one canonical Quill Delta JSON document for notebook storage.

    The function is intentionally conservative: it unwraps nested JSON only when
    the complete value validates as a Quill Delta document. Ordinary JSON prose
    remains prose and is converted to a plain paragraph.
    """

    candidates: list[Any] = []
    if structured_content not in (None, ""):
        candidates.append(structured_content)
    if content not in (None, ""):
        candidates.append(content)
    if not candidates:
        return CANONICAL_BLANK_DELTA_JSON
    for candidate in candidates:
        ops = _delta_ops_from_value(candidate, depth=0)
        if ops is not None:
            return _canonical_delta_json_from_ops(ops)
        if isinstance(candidate, str):
            repaired = _delta_json_from_text(candidate)
            if repaired is not None:
                return _canonical_delta_json_from_ops(json.loads(repaired))
    fallback = content if content not in (None, "") else structured_content
    normalized_format = _normalize_document_format(document_format)
    if normalized_format in {"markdown", "html"}:
        return _markdown_to_delta_json(str(fallback or ""))
    return _markdown_to_delta_json(str(fallback or ""))


def append_markdown_to_notebook_delta(existing_content: Any, markdown: str) -> str:
    """Append readable Markdown/plain text to an existing canonical Delta."""

    append_text = (markdown or "").strip()
    if not append_text:
        return canonical_notebook_delta_json(existing_content, "rich_text_delta_json")
    existing_ops = json.loads(canonical_notebook_delta_json(existing_content, "rich_text_delta_json"))
    append_ops = json.loads(_markdown_to_delta_json(append_text))
    if existing_ops == [{"insert": "\n"}]:
        merged = append_ops
    else:
        merged = list(existing_ops)
        last_insert = merged[-1].get("insert") if merged else None
        if isinstance(last_insert, str) and not last_insert.endswith("\n"):
            merged.append({"insert": "\n"})
        merged.extend(append_ops)
    return _canonical_delta_json_from_ops(merged)


def _delta_json_from_text(content: str) -> str | None:
    stripped = (content or "").strip()
    if not stripped:
        return CANONICAL_BLANK_DELTA_JSON
    ops = _delta_ops_from_json_text(stripped)
    if ops is not None:
        return _canonical_delta_json_from_ops(ops)
    split = _extract_json_prefix(stripped)
    if split is None:
        return None
    prefix, trailing = split
    ops = _delta_ops_from_json_text(prefix)
    if ops is None:
        return None
    if trailing.strip():
        ops.append({"insert": f"\n{trailing.strip()}\n"})
    return _canonical_delta_json_from_ops(ops)


def _delta_ops_from_json_text(content: str) -> list[dict[str, Any]] | None:
    return _delta_ops_from_json_text_at_depth(content, 0)


def _delta_ops_from_json_text_at_depth(content: str, depth: int) -> list[dict[str, Any]] | None:
    if depth > 4:
        return None
    current: Any = content
    decoded: Any = None
    for _ in range(4):
        try:
            decoded = json.loads(current)
        except (json.JSONDecodeError, TypeError):
            return None
        if isinstance(decoded, str):
            current = decoded
            continue
        break
    return _delta_ops_from_value(decoded, depth)


def _delta_ops_from_value(value: Any, depth: int) -> list[dict[str, Any]] | None:
    if depth > 4:
        return None
    decoded = value
    if isinstance(decoded, str):
        return _delta_ops_from_json_text_at_depth(decoded, depth)
    if isinstance(decoded, dict) and isinstance(decoded.get("ops"), list):
        decoded = decoded["ops"]
    if not isinstance(decoded, list):
        return None
    ops: list[dict[str, Any]] = []
    for op in decoded:
        if not isinstance(op, dict) or "insert" not in op:
            return None
        normalized_op = dict(op)
        inserted = normalized_op.get("insert")
        if isinstance(inserted, str):
            nested = _nested_delta_ops_from_insert(inserted, depth + 1)
            if nested is not None:
                ops.extend(nested)
                continue
        ops.append(normalized_op)
    return _normalize_delta_ops(ops)


def _nested_delta_ops_from_insert(inserted: str, depth: int) -> list[dict[str, Any]] | None:
    if depth > 4:
        return None
    trimmed = inserted.strip()
    if not trimmed or trimmed[0] not in "[{":
        return None
    return _delta_ops_from_json_text_at_depth(trimmed, depth)


def _normalize_delta_ops(ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not ops:
        return [{"insert": "\n"}]
    normalized = [dict(op) for op in ops]
    while len(normalized) > 1:
        last = normalized[-1]
        previous = normalized[-2]
        if set(last.keys()) == {"insert"} and last.get("insert") == "\n":
            previous_insert = previous.get("insert")
            if isinstance(previous_insert, str) and previous_insert.endswith("\n"):
                normalized.pop()
                continue
        break
    last_insert = normalized[-1].get("insert")
    if isinstance(last_insert, str):
        if not last_insert.endswith("\n"):
            normalized.append({"insert": "\n"})
    else:
        normalized.append({"insert": "\n"})
    return normalized


def _canonical_delta_json_from_ops(ops: list[dict[str, Any]]) -> str:
    return json.dumps(_normalize_delta_ops(ops), ensure_ascii=False, separators=(",", ":"))


def _extract_json_prefix(content: str) -> tuple[str, str] | None:
    stripped = content.lstrip()
    if not stripped or stripped[0] not in "[{":
        return None
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(stripped):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        if depth == 0:
            return stripped[: index + 1], stripped[index + 1 :]
    return None


class RichNotebookContextService:
    """Convert rich notebooks into backend-safe context for search and AI."""

    def extract_plain_text(self, document: dict[str, Any]) -> str:
        return _plain_text_from_document(
            str(document.get("content") or document.get("structured_content") or ""),
            str(document.get("document_format") or "markdown"),
        )

    def enumerate_references(self, document: dict[str, Any]) -> list[dict[str, Any]]:
        return self._enumerate_embeds(document, embed_type="research_object")

    def enumerate_attachments(self, document: dict[str, Any]) -> list[dict[str, Any]]:
        return self._enumerate_embeds(document, embed_type="attachment")

    def build_authorized_ai_context(self, document: dict[str, Any], user: str) -> dict[str, Any]:
        return {
            "user_id": user,
            "plain_text": self.extract_plain_text(document),
            "references": self.enumerate_references(document),
            "attachments": self.enumerate_attachments(document),
            "structure": self.summarize_document_structure(document),
        }

    def summarize_document_structure(self, document: dict[str, Any]) -> dict[str, Any]:
        content = str(document.get("content") or document.get("structured_content") or "")
        try:
            decoded = json.loads(content)
        except json.JSONDecodeError:
            decoded = []
        if isinstance(decoded, dict):
            decoded = decoded.get("ops") or []
        headings = 0
        embeds = 0
        if isinstance(decoded, list):
            for op in decoded:
                if not isinstance(op, dict):
                    continue
                attrs = op.get("attributes") if isinstance(op.get("attributes"), dict) else {}
                if "header" in attrs:
                    headings += 1
                if isinstance(op.get("insert"), dict):
                    embeds += 1
        return {"headings": headings, "embeds": embeds, "schema_version": document.get("schema_version") or 1}

    def _enumerate_embeds(self, document: dict[str, Any], embed_type: str) -> list[dict[str, Any]]:
        content = str(document.get("content") or document.get("structured_content") or "")
        try:
            decoded = json.loads(content)
        except json.JSONDecodeError:
            return []
        if isinstance(decoded, dict):
            decoded = decoded.get("ops") or []
        embeds: list[dict[str, Any]] = []
        if isinstance(decoded, list):
            for op in decoded:
                if not isinstance(op, dict):
                    continue
                inserted = op.get("insert")
                if isinstance(inserted, dict) and inserted.get("embed_type") == embed_type:
                    embeds.append(inserted)
        return embeds


def _link_provider(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if "docs.google.com" in host and "/spreadsheets/" in path:
        return {"provider": "Google Sheets", "attachment_type": "google_sheet", "display_name": "Google Sheet"}
    if "drive.google.com" in host or "docs.google.com" in host:
        return {"provider": "Google Drive", "attachment_type": "google_drive", "display_name": "Google Drive file"}
    if "sharepoint.com" in host:
        return {"provider": "SharePoint", "attachment_type": "sharepoint", "display_name": "SharePoint file"}
    if "onedrive.live.com" in host or "1drv.ms" in host:
        return {"provider": "OneDrive", "attachment_type": "onedrive", "display_name": "OneDrive file"}
    if "dropbox.com" in host:
        return {"provider": "Dropbox", "attachment_type": "dropbox", "display_name": "Dropbox file"}
    return {"provider": "External Link", "attachment_type": "external_link", "display_name": host or "External link"}


def _slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")[:80] or uuid.uuid4().hex[:8]


def _mentions_organoid(experiment: dict[str, Any]) -> bool:
    text = " ".join(str(value) for value in experiment.values() if value).lower()
    return "organoid" in text
