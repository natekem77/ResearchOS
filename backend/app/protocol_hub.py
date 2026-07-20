"""Structured, versioned scientific protocol hub for ResearchOS."""

from __future__ import annotations

import json
import mimetypes
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.attachment_storage import StoredAttachment
from app.config import Settings
from app.general_experiments import GeneralExperimentService, _decode, _slug
from app.protocol_ai_extraction import (
    PROTOCOL_EXTRACTION_SCHEMA_VERSION,
    ai_draft_to_legacy_draft,
    ai_extraction_enabled,
    classify_protocol_with_ai,
    extraction_items_from_draft,
)
from app.protocol_document_extractor import extract_protocol_document
from app.protocol_file_storage import ProtocolFileStorage
from app.storage import SQLiteStore


class ProtocolHubValidationError(ValueError):
    """Raised for invalid protocol hub requests."""


class ProtocolHubService:
    """First-class protocol workspaces built on versioned protocol tables."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = SQLiteStore(settings=settings)
        # Ensure the shared generalized experiment/protocol schema exists.
        self.general = GeneralExperimentService(settings=settings)
        self._ensure_schema()
        self.ensure_demo_protocols()

    def _connect(self) -> sqlite3.Connection:
        return self.store._connect()

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            self._ensure_column(connection, "protocols_general", "short_name", "TEXT")
            self._ensure_column(connection, "protocols_general", "category", "TEXT")
            self._ensure_column(connection, "protocols_general", "owner_user_id", "TEXT")
            self._ensure_column(connection, "protocols_general", "sort_index", "INTEGER")
            self._ensure_column(connection, "protocols_general", "group_id", "TEXT")
            self._ensure_column(connection, "protocols_general", "archived_at", "TEXT")
            self._ensure_column(connection, "protocols_general", "archived_by", "TEXT")
            self._ensure_column(connection, "protocol_versions_general", "version_number", "TEXT")
            self._ensure_column(connection, "protocol_versions_general", "summary_of_changes", "TEXT")
            self._ensure_column(connection, "protocol_versions_general", "status", "TEXT NOT NULL DEFAULT 'draft'")
            self._ensure_column(connection, "protocol_events_general", "relative_day", "INTEGER")
            self._ensure_column(connection, "protocol_events_general", "relative_hour", "REAL")
            self._ensure_column(connection, "protocol_events_general", "default_duration", "TEXT")
            self._ensure_column(connection, "protocol_events_general", "required", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(connection, "protocol_events_general", "default_resource", "TEXT")
            self._ensure_column(connection, "protocol_events_general", "default_units", "TEXT")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS protocol_materials (
                    material_id TEXT PRIMARY KEY,
                    protocol_version_id TEXT NOT NULL,
                    inventory_item_id TEXT,
                    name TEXT NOT NULL,
                    vendor TEXT,
                    catalog_number TEXT,
                    concentration TEXT,
                    required INTEGER NOT NULL DEFAULT 1,
                    substitutions_json TEXT NOT NULL DEFAULT '[]',
                    notes TEXT
                );

                CREATE TABLE IF NOT EXISTS protocol_media (
                    media_id TEXT PRIMARY KEY,
                    protocol_version_id TEXT NOT NULL,
                    recipe TEXT NOT NULL,
                    components_json TEXT NOT NULL DEFAULT '[]',
                    preparation TEXT,
                    storage TEXT,
                    media_change_schedule TEXT
                );

                CREATE TABLE IF NOT EXISTS protocol_notebook_documents (
                    document_id TEXT PRIMARY KEY,
                    protocol_version_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    document_format TEXT NOT NULL DEFAULT 'markdown',
                    content TEXT NOT NULL,
                    plain_text_cache TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_by TEXT
                );

                CREATE TABLE IF NOT EXISTS protocol_expected_results (
                    expected_result_id TEXT PRIMARY KEY,
                    protocol_version_id TEXT NOT NULL,
                    stage_label TEXT,
                    day INTEGER,
                    title TEXT NOT NULL,
                    description TEXT,
                    markers_json TEXT NOT NULL DEFAULT '[]',
                    qc_metrics_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS protocol_troubleshooting (
                    troubleshooting_id TEXT PRIMARY KEY,
                    protocol_version_id TEXT NOT NULL,
                    issue TEXT NOT NULL,
                    possible_causes_json TEXT NOT NULL DEFAULT '[]',
                    possible_solutions_json TEXT NOT NULL DEFAULT '[]',
                    linked_papers_json TEXT NOT NULL DEFAULT '[]',
                    linked_images_json TEXT NOT NULL DEFAULT '[]'
                );

                CREATE TABLE IF NOT EXISTS protocol_linked_papers (
                    protocol_version_id TEXT NOT NULL,
                    paper_id TEXT NOT NULL,
                    relationship TEXT NOT NULL DEFAULT 'reference',
                    PRIMARY KEY(protocol_version_id, paper_id, relationship)
                );

                CREATE TABLE IF NOT EXISTS protocol_imports (
                    import_id TEXT PRIMARY KEY,
                    lab_id TEXT NOT NULL,
                    uploaded_by TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    original_filename TEXT,
                    storage_reference TEXT,
                    mime_type TEXT,
                    protocol_id TEXT,
                    safe_filename TEXT,
                    file_extension TEXT,
                    size_bytes INTEGER,
                    checksum TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    extraction_status TEXT NOT NULL DEFAULT 'uploaded',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    error_message TEXT
                );

                CREATE TABLE IF NOT EXISTS protocol_extraction_drafts (
                    extraction_id TEXT PRIMARY KEY,
                    import_id TEXT,
                    protocol_id TEXT,
                    lab_id TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    proposed_title TEXT,
                    proposed_category TEXT,
                    proposed_biological_system TEXT,
                    proposed_sample_unit TEXT,
                    proposed_duration TEXT,
                    proposed_events_json TEXT NOT NULL DEFAULT '[]',
                    proposed_materials_json TEXT NOT NULL DEFAULT '[]',
                    proposed_media_json TEXT NOT NULL DEFAULT '[]',
                    proposed_equipment_json TEXT NOT NULL DEFAULT '[]',
                    proposed_expected_results_json TEXT NOT NULL DEFAULT '[]',
                    proposed_qc_json TEXT NOT NULL DEFAULT '[]',
                    proposed_troubleshooting_json TEXT NOT NULL DEFAULT '[]',
                    proposed_references_json TEXT NOT NULL DEFAULT '[]',
                    ambiguities_json TEXT NOT NULL DEFAULT '[]',
                    warnings_json TEXT NOT NULL DEFAULT '[]',
                    confidence_by_field_json TEXT NOT NULL DEFAULT '{}',
                    extraction_evidence_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS protocol_extraction_runs (
                    run_id TEXT PRIMARY KEY,
                    protocol_id TEXT NOT NULL,
                    source_attachment_id TEXT,
                    linked_draft_id TEXT,
                    mode TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'rules',
                    model TEXT,
                    parser_version TEXT NOT NULL,
                    user_instruction TEXT,
                    status TEXT NOT NULL DEFAULT 'completed',
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at TEXT,
                    error TEXT,
                    canonical_document_json TEXT NOT NULL DEFAULT '{}',
                    deterministic_draft_json TEXT NOT NULL DEFAULT '{}',
                    ai_draft_json TEXT,
                    merged_draft_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS protocol_extraction_items (
                    item_id TEXT PRIMARY KEY,
                    extraction_run_id TEXT NOT NULL,
                    section TEXT NOT NULL,
                    source_ids_json TEXT NOT NULL DEFAULT '[]',
                    raw_source_text TEXT,
                    normalized_json TEXT NOT NULL DEFAULT '{}',
                    confidence TEXT NOT NULL DEFAULT 'unknown',
                    origin TEXT NOT NULL DEFAULT 'rules',
                    review_status TEXT NOT NULL DEFAULT 'needs_review',
                    reviewer TEXT,
                    reviewed_at TEXT,
                    FOREIGN KEY(extraction_run_id) REFERENCES protocol_extraction_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS protocol_groups (
                    group_id TEXT PRIMARY KEY,
                    lab_id TEXT NOT NULL,
                    parent_group_id TEXT,
                    name TEXT NOT NULL,
                    sort_index INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            self._ensure_column(connection, "protocol_imports", "protocol_id", "TEXT")
            self._ensure_column(connection, "protocol_imports", "safe_filename", "TEXT")
            self._ensure_column(connection, "protocol_imports", "file_extension", "TEXT")
            self._ensure_column(connection, "protocol_imports", "size_bytes", "INTEGER")
            self._ensure_column(connection, "protocol_imports", "checksum", "TEXT")
            self._ensure_column(connection, "protocol_imports", "metadata_json", "TEXT NOT NULL DEFAULT '{}'")
            self._normalize_group_order(connection)
            self._normalize_protocol_order(connection)

    def _ensure_column(self, connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _normalize_protocol_order(self, connection: sqlite3.Connection) -> None:
        scopes = connection.execute(
            """
            SELECT DISTINCT lab_id, group_id FROM protocols_general
            WHERE archived_at IS NULL
            """
        ).fetchall()
        for scope in scopes:
            group_id = scope["group_id"]
            if group_id is None:
                rows = connection.execute(
                    """
                    SELECT protocol_id FROM protocols_general
                    WHERE archived_at IS NULL AND lab_id = ? AND group_id IS NULL
                    ORDER BY COALESCE(sort_index, 2147483647), protocol_id ASC
                    """,
                    (scope["lab_id"],),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT protocol_id FROM protocols_general
                    WHERE archived_at IS NULL AND lab_id = ? AND group_id = ?
                    ORDER BY COALESCE(sort_index, 2147483647), protocol_id ASC
                    """,
                    (scope["lab_id"], group_id),
                ).fetchall()
            for index, row in enumerate(rows):
                connection.execute(
                    "UPDATE protocols_general SET sort_index = ? WHERE protocol_id = ?",
                    ((index + 1) * 1000, row["protocol_id"]),
                )

    def _normalize_group_order(self, connection: sqlite3.Connection) -> None:
        scopes = connection.execute(
            "SELECT DISTINCT lab_id, parent_group_id FROM protocol_groups"
        ).fetchall()
        for scope in scopes:
            parent_id = scope["parent_group_id"]
            if parent_id is None:
                rows = connection.execute(
                    """
                    SELECT group_id FROM protocol_groups
                    WHERE lab_id = ? AND parent_group_id IS NULL
                    ORDER BY COALESCE(sort_index, 2147483647), group_id ASC
                    """,
                    (scope["lab_id"],),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT group_id FROM protocol_groups
                    WHERE lab_id = ? AND parent_group_id = ?
                    ORDER BY COALESCE(sort_index, 2147483647), group_id ASC
                    """,
                    (scope["lab_id"], parent_id),
                ).fetchall()
            for index, row in enumerate(rows):
                connection.execute(
                    "UPDATE protocol_groups SET sort_index = ? WHERE group_id = ?",
                    ((index + 1) * 1000, row["group_id"]),
                )

    def ensure_demo_protocols(self) -> None:
        demos = [
            {
                "title": "Meyer retinal organoid protocol",
                "short_name": "Meyer organoids",
                "category": "differentiation",
                "biological_system": "retinal organoid",
                "sample_unit": "organoid",
                "description": (
                    "Incomplete internal working draft. Upload or paste the authoritative "
                    "Meyer protocol before approval."
                ),
                "status": "draft",
                "summary": "Seeded incomplete source-verification draft.",
                "content": (
                    "# Meyer Retinal Organoid Protocol\n\n"
                    "**Status:** incomplete internal working draft; needs source verification.\n\n"
                    "This draft only contains details already represented in current ResearchOS project data.\n"
                    "Upload or paste the authoritative Meyer protocol before approval.\n\n"
                    "Confirmed project context:\n"
                    "- Biological system: retinal organoid\n"
                    "- Sample unit: organoid\n"
                    "- Representative duration: through D90 in the linked NK_Expt_26 design\n"
                    "- BMP4 event on D6\n"
                    "- Attachment event on D9\n"
                    "- Related experiment: NK_Expt_26\n\n"
                    "Unknown until source verification:\n"
                    "- Reagent concentrations\n"
                    "- Media recipes and media-change schedule\n"
                    "- Cell numbers\n"
                    "- Catalog numbers\n"
                    "- Detailed procedural steps\n"
                    "- Expected markers or QC thresholds\n"
                ),
                "events": [
                    {
                        "title": "BMP4",
                        "relative_day": 6,
                        "event_type": "compound",
                        "description": "Confirmed timing only; concentration remains unknown until source verification.",
                        "metadata": {"source_status": "incomplete_internal_working_draft", "confidence": "medium"},
                    },
                    {
                        "title": "Attachment event",
                        "relative_day": 9,
                        "event_type": "protocol_step",
                        "description": "Included only as a project-supported draft event; verify against the authoritative protocol.",
                        "metadata": {"source_status": "incomplete_internal_working_draft", "confidence": "medium"},
                    },
                ],
                "materials": [],
                "expected": [],
                "troubleshooting": [],
            },
            {
                "title": "Nakano retinal organoid protocol",
                "short_name": "Nakano organoids",
                "category": "differentiation",
                "biological_system": "retinal organoid",
                "sample_unit": "organoid",
                "events": [
                    {"title": "Start differentiation", "relative_day": 0, "event_type": "protocol_step"},
                    {"title": "Optic-vesicle stage check", "relative_day": 18, "event_type": "qc"},
                ],
                "materials": [{"name": "Differentiation medium", "vendor": "Lab-made"}],
                "expected": [{"day": 35, "stage_label": "D35", "title": "Retinal cups", "markers": ["VSX2", "PAX6"]}],
            },
            {
                "title": "Simple RPE protocol",
                "short_name": "RPE",
                "category": "differentiation",
                "biological_system": "RPE",
                "sample_unit": "well",
                "events": [{"title": "Pigmentation check", "relative_day": 30, "event_type": "qc"}],
            },
            {
                "title": "Stem cell maintenance",
                "short_name": "Stem cell maintenance",
                "category": "maintenance",
                "biological_system": "stem cells",
                "sample_unit": "well",
                "events": [{"title": "Media change", "relative_day": 1, "event_type": "media_change"}],
            },
            {
                "title": "Media preparation",
                "short_name": "Media prep",
                "category": "media",
                "biological_system": None,
                "sample_unit": "batch",
                "events": [{"title": "Prepare and sterile filter", "relative_day": 0, "event_type": "custom"}],
            },
            {
                "title": "Immunostaining",
                "short_name": "IF staining",
                "category": "assay",
                "biological_system": "general",
                "sample_unit": "sample",
                "events": [{"title": "Primary antibody incubation", "relative_day": 0, "event_type": "assay"}],
            },
            {
                "title": "RNA extraction",
                "short_name": "RNA extraction",
                "category": "sequencing",
                "biological_system": "general",
                "sample_unit": "sample",
                "events": [{"title": "Lyse sample", "relative_day": 0, "event_type": "collection"}],
            },
        ]
        for demo in demos:
            self.create_or_update_protocol(
                actor_user_id="user:pi-owner",
                lab_id="lab:demo",
                title=demo["title"],
                short_name=demo["short_name"],
                description=str(demo.get("description") or f"Structured demo protocol: {demo['title']}."),
                category=demo["category"],
                biological_system=demo.get("biological_system"),
                sample_unit=demo.get("sample_unit"),
                version_number="1.0",
                summary_of_changes=str(demo.get("summary") or "Initial structured demo version."),
                content=str(demo.get("content") or f"# {demo['title']}\n\nStructured protocol notebook foundation."),
                events=demo.get("events", []),
                materials=demo.get("materials", []),
                expected_results=demo.get("expected", []),
                troubleshooting=demo.get(
                    "troubleshooting",
                    [
                        {
                            "issue": "Low reproducibility",
                            "possible_causes": ["Timing deviation", "Reagent lot change"],
                            "possible_solutions": ["Review timeline", "Check inventory lot metadata"],
                        }
                    ],
                ),
                status=str(demo.get("status") or "approved"),
            )

    def create_or_update_protocol(
        self,
        actor_user_id: str,
        lab_id: str,
        title: str,
        short_name: str | None = None,
        description: str | None = None,
        category: str | None = None,
        biological_system: str | None = None,
        sample_unit: str | None = None,
        version_number: str = "1.0",
        summary_of_changes: str | None = None,
        content: str = "",
        events: list[dict[str, Any]] | None = None,
        materials: list[dict[str, Any]] | None = None,
        media: list[dict[str, Any]] | None = None,
        expected_results: list[dict[str, Any]] | None = None,
        troubleshooting: list[dict[str, Any]] | None = None,
        status: str = "approved",
    ) -> dict[str, Any]:
        protocol_id = f"protocol:{_slug(title)}"
        version_id = f"protocol-version:{_slug(title)}:{_slug(version_number)}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO protocols_general
                    (protocol_id, lab_id, title, short_name, description, category, biological_system,
                     default_sample_unit, owner_user_id, current_version_id, status, sort_index, group_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT MAX(sort_index) + 1000 FROM protocols_general WHERE lab_id = ? AND group_id IS NULL), 1000), NULL)
                ON CONFLICT(protocol_id) DO UPDATE SET
                    short_name = excluded.short_name,
                    description = excluded.description,
                    category = excluded.category,
                    biological_system = excluded.biological_system,
                    default_sample_unit = excluded.default_sample_unit,
                    owner_user_id = COALESCE(protocols_general.owner_user_id, excluded.owner_user_id),
                    current_version_id = excluded.current_version_id,
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (protocol_id, lab_id, title, short_name, description, category, biological_system, sample_unit, actor_user_id, version_id, status, lab_id),
            )
            connection.execute(
                """
                INSERT INTO protocol_versions_general
                    (protocol_version_id, protocol_id, version_label, version_number, summary_of_changes,
                     content, created_by, approved_by, approved_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(protocol_version_id) DO NOTHING
                """,
                (
                    version_id,
                    protocol_id,
                    version_number,
                    version_number,
                    summary_of_changes,
                    content,
                    actor_user_id,
                    actor_user_id if status == "approved" else None,
                    _timestamp_sql_value(status),
                    status,
                ),
            )
            for event in events or []:
                self._insert_event(connection, version_id, event)
            for material in materials or []:
                self._insert_material(connection, version_id, material)
            for medium in media or []:
                self._insert_media(connection, version_id, medium)
            for expected in expected_results or []:
                self._insert_expected(connection, version_id, expected)
            for entry in troubleshooting or []:
                self._insert_troubleshooting(connection, version_id, entry)
            self._ensure_notebook(connection, version_id, title, content, actor_user_id)
        protocol = self.get_protocol(protocol_id)
        assert protocol is not None
        return protocol

    def list_protocols(self, query: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as connection:
            self._normalize_group_order(connection)
            self._normalize_protocol_order(connection)
            protocols = [
                _decode(row)
                for row in connection.execute(
                    """
                    SELECT * FROM protocols_general
                    WHERE archived_at IS NULL
                    ORDER BY COALESCE(group_id, ''), COALESCE(sort_index, 2147483647), protocol_id ASC
                    """
                ).fetchall()
            ]
        enriched = [self._protocol_summary(protocol["protocol_id"]) for protocol in protocols]
        if query:
            q = query.lower()
            enriched = [item for item in enriched if q in json.dumps(item).lower()]
        return [item for item in enriched if item is not None]

    def list_protocol_groups(self, lab_id: str = "lab:demo") -> list[dict[str, Any]]:
        with self._connect() as connection:
            self._normalize_group_order(connection)
            rows = connection.execute(
                """
                SELECT * FROM protocol_groups
                WHERE lab_id = ?
                ORDER BY COALESCE(parent_group_id, ''), sort_index ASC, group_id ASC
                """,
                (lab_id,),
            ).fetchall()
            return [_decode(row) for row in rows]

    def protocol_tree(self, lab_id: str = "lab:demo", query: str | None = None) -> dict[str, Any]:
        protocols = [
            item for item in self.list_protocols(query=query)
            if str(item.get("lab_id") or lab_id) == lab_id
        ]
        groups = self.list_protocol_groups(lab_id=lab_id)
        protocol_counts: dict[str, int] = {}
        for protocol in protocols:
            group_id = protocol.get("group_id")
            if group_id:
                protocol_counts[str(group_id)] = protocol_counts.get(str(group_id), 0) + 1
        children_by_parent: dict[str | None, list[dict[str, Any]]] = {}
        for group in groups:
            children_by_parent.setdefault(group.get("parent_group_id"), []).append(group)
        def subtree_count(group_id: str) -> int:
            total = protocol_counts.get(group_id, 0)
            for child in children_by_parent.get(group_id, []):
                total += subtree_count(str(child["group_id"]))
            return total
        group_payloads = []
        for group in groups:
            payload = dict(group)
            payload["item_count"] = subtree_count(str(group["group_id"]))
            group_payloads.append(payload)
        return {
            "groups": group_payloads,
            "protocols": protocols,
            "ordering": "groups_first",
        }

    def create_group(
        self,
        actor_user_id: str,
        lab_id: str,
        name: str,
        parent_group_id: str | None = None,
    ) -> dict[str, Any]:
        clean_name = name.strip()
        if not clean_name:
            raise ProtocolHubValidationError("Group name is required.")
        with self._connect() as connection:
            if parent_group_id:
                parent = self._group_row(connection, parent_group_id)
                if parent is None:
                    raise ProtocolHubValidationError("Parent group not found.")
                lab_id = str(parent["lab_id"])
            self._require_lab_manage(actor_user_id, lab_id, "Protocol group creation requires manage access.")
            group_id = f"protocol-group:{uuid.uuid4().hex[:16]}"
            sort_index = self._next_group_sort_index(connection, lab_id, parent_group_id)
            connection.execute(
                """
                INSERT INTO protocol_groups
                    (group_id, lab_id, parent_group_id, name, sort_index)
                VALUES (?, ?, ?, ?, ?)
                """,
                (group_id, lab_id, parent_group_id, clean_name, sort_index),
            )
            row = self._group_row(connection, group_id)
            assert row is not None
            return _decode(row)

    def rename_group(self, actor_user_id: str, group_id: str, name: str) -> dict[str, Any]:
        clean_name = name.strip()
        if not clean_name:
            raise ProtocolHubValidationError("Group name is required.")
        with self._connect() as connection:
            group = self._group_row(connection, group_id)
            if group is None:
                raise ProtocolHubValidationError("Protocol group not found.")
            self._require_lab_manage(actor_user_id, str(group["lab_id"]), "Protocol group rename requires manage access.")
            connection.execute(
                "UPDATE protocol_groups SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE group_id = ?",
                (clean_name, group_id),
            )
            row = self._group_row(connection, group_id)
            assert row is not None
            return _decode(row)

    def move_group(self, actor_user_id: str, group_id: str, parent_group_id: str | None) -> dict[str, Any]:
        with self._connect() as connection:
            group = self._group_row(connection, group_id)
            if group is None:
                raise ProtocolHubValidationError("Protocol group not found.")
            lab_id = str(group["lab_id"])
            self._require_lab_manage(actor_user_id, lab_id, "Protocol group move requires manage access.")
            if parent_group_id == group_id:
                raise ProtocolHubValidationError("A group cannot be its own parent.")
            if parent_group_id:
                parent = self._group_row(connection, parent_group_id)
                if parent is None:
                    raise ProtocolHubValidationError("Parent group not found.")
                if str(parent["lab_id"]) != lab_id:
                    raise ProtocolHubValidationError("Protocol groups must belong to the same lab.")
                if self._is_group_descendant(connection, parent_group_id, group_id):
                    raise ProtocolHubValidationError("A group cannot be moved into its descendant.")
            next_index = self._next_group_sort_index(connection, lab_id, parent_group_id)
            connection.execute(
                """
                UPDATE protocol_groups
                SET parent_group_id = ?, sort_index = ?, updated_at = CURRENT_TIMESTAMP
                WHERE group_id = ?
                """,
                (parent_group_id, next_index, group_id),
            )
            self._normalize_group_order(connection)
            row = self._group_row(connection, group_id)
            assert row is not None
            return _decode(row)

    def reorder_groups(self, actor_user_id: str, ordered_group_ids: list[str]) -> list[dict[str, Any]]:
        requested_ids = self._clean_order_ids(ordered_group_ids, label="group")
        with self._connect() as connection:
            placeholders = ",".join("?" for _ in requested_ids)
            rows = connection.execute(
                f"SELECT * FROM protocol_groups WHERE group_id IN ({placeholders})",
                requested_ids,
            ).fetchall()
            groups = [_decode(row) for row in rows]
            if len(groups) != len(requested_ids):
                raise ProtocolHubValidationError("Unknown protocol group id in reorder request.")
            lab_ids = {str(group.get("lab_id") or "") for group in groups}
            parent_ids = {str(group.get("parent_group_id") or "") for group in groups}
            if len(lab_ids) != 1 or len(parent_ids) != 1:
                raise ProtocolHubValidationError("Protocol groups must share one parent to reorder.")
            self._require_lab_manage(actor_user_id, next(iter(lab_ids)), "Protocol group reorder requires manage access.")
            for index, group_id in enumerate(requested_ids):
                connection.execute(
                    "UPDATE protocol_groups SET sort_index = ?, updated_at = CURRENT_TIMESTAMP WHERE group_id = ?",
                    ((index + 1) * 1000, group_id),
                )
        by_id = {str(item["group_id"]): item for item in self.list_protocol_groups(lab_id=next(iter(lab_ids)))}
        return [by_id[group_id] for group_id in requested_ids if group_id in by_id]

    def delete_group(self, actor_user_id: str, group_id: str, mode: str = "move_contents_to_parent") -> dict[str, Any]:
        with self._connect() as connection:
            group = self._group_row(connection, group_id)
            if group is None:
                raise ProtocolHubValidationError("Protocol group not found.")
            lab_id = str(group["lab_id"])
            parent_id = group["parent_group_id"]
            self._require_lab_manage(actor_user_id, lab_id, "Protocol group deletion requires manage access.")
            descendants = self._descendant_group_ids(connection, group_id)
            if mode == "move_contents_to_parent":
                next_group_index = self._next_group_sort_index(connection, lab_id, parent_id)
                direct_children = connection.execute(
                    "SELECT group_id FROM protocol_groups WHERE parent_group_id = ? ORDER BY sort_index ASC, group_id ASC",
                    (group_id,),
                ).fetchall()
                for index, child in enumerate(direct_children):
                    connection.execute(
                        "UPDATE protocol_groups SET parent_group_id = ?, sort_index = ?, updated_at = CURRENT_TIMESTAMP WHERE group_id = ?",
                        (parent_id, next_group_index + (index * 1000), child["group_id"]),
                    )
                next_protocol_index = self._next_protocol_sort_index(connection, lab_id, parent_id)
                protocols = connection.execute(
                    "SELECT protocol_id FROM protocols_general WHERE group_id = ? AND archived_at IS NULL ORDER BY sort_index ASC, protocol_id ASC",
                    (group_id,),
                ).fetchall()
                for index, protocol in enumerate(protocols):
                    connection.execute(
                        "UPDATE protocols_general SET group_id = ?, sort_index = ?, updated_at = CURRENT_TIMESTAMP WHERE protocol_id = ?",
                        (parent_id, next_protocol_index + (index * 1000), protocol["protocol_id"]),
                    )
                connection.execute("DELETE FROM protocol_groups WHERE group_id = ?", (group_id,))
            elif mode == "recursive":
                protocol_rows = connection.execute(
                    f"""
                    SELECT protocol_id FROM protocols_general
                    WHERE archived_at IS NULL AND group_id IN ({','.join('?' for _ in [group_id, *descendants])})
                    """,
                    [group_id, *descendants],
                ).fetchall()
                protocol_ids = [str(row["protocol_id"]) for row in protocol_rows]
                connection.execute(
                    f"DELETE FROM protocol_groups WHERE group_id IN ({','.join('?' for _ in [group_id, *descendants])})",
                    [group_id, *descendants],
                )
            else:
                raise ProtocolHubValidationError("Unsupported protocol group delete mode.")
            self._normalize_group_order(connection)
            self._normalize_protocol_order(connection)
        deleted_protocols = 0
        if mode == "recursive":
            for protocol_id in protocol_ids:
                self.delete_protocol(actor_user_id, protocol_id)
                deleted_protocols += 1
        return {"deleted": True, "group_id": group_id, "mode": mode, "deleted_protocol_count": deleted_protocols if mode == "recursive" else 0}

    def move_protocol_to_group(self, actor_user_id: str, protocol_id: str, group_id: str | None) -> dict[str, Any]:
        protocol = self.general.get_protocol(protocol_id)
        if protocol is None or protocol.get("archived_at"):
            raise ProtocolHubValidationError("Protocol not found.")
        if not self._can_manage_protocol(actor_user_id, protocol):
            raise PermissionError("Protocol move requires manage access.")
        lab_id = str(protocol.get("lab_id") or "lab:demo")
        with self._connect() as connection:
            if group_id:
                group = self._group_row(connection, group_id)
                if group is None:
                    raise ProtocolHubValidationError("Protocol group not found.")
                if str(group["lab_id"]) != lab_id:
                    raise ProtocolHubValidationError("Protocol and group must belong to the same lab.")
            sort_index = self._next_protocol_sort_index(connection, lab_id, group_id)
            connection.execute(
                """
                UPDATE protocols_general
                SET group_id = ?, sort_index = ?, updated_at = CURRENT_TIMESTAMP
                WHERE protocol_id = ?
                """,
                (group_id, sort_index, protocol_id),
            )
            self._normalize_protocol_order(connection)
        moved = self.get_protocol(protocol_id)
        assert moved is not None
        return moved

    def get_protocol(self, protocol_id: str) -> dict[str, Any] | None:
        summary = self._protocol_summary(protocol_id)
        if summary is None:
            return None
        version_id = str(summary.get("current_version_id") or "")
        return summary | {"workspace": self.version_workspace(version_id)}

    def version_workspace(self, protocol_version_id: str) -> dict[str, Any]:
        version = self.general.get_protocol_version(protocol_version_id)
        if version is None:
            raise ProtocolHubValidationError("Protocol version not found.")
        protocol = self.general.get_protocol(str(version["protocol_id"])) or {}
        return {
            "overview": protocol | {"current_version": version},
            "notebook": self.notebook(protocol_version_id),
            "timeline": self.events(protocol_version_id),
            "materials": self.materials(protocol_version_id),
            "media": self.media(protocol_version_id),
            "equipment": [],
            "events": self.events(protocol_version_id),
            "expected_results": self.expected_results(protocol_version_id),
            "qc": [item for item in self.events(protocol_version_id) if item.get("event_type") == "qc"],
            "troubleshooting": self.troubleshooting(protocol_version_id),
            "linked_papers": self.linked_papers(protocol_version_id),
            "version_history": self.version_history(str(version["protocol_id"])),
            "usage_statistics": self.usage_statistics(str(version["protocol_id"])),
            "related_experiments": self.related_experiments(str(version["protocol_id"])),
            "discussion": {"status": "Use Lab Chat discussion links in a future milestone."},
            "ai_foundation": {
                "interfaces": ["ExperimentDesignCopilot", "ProtocolReasoner", "TimelineMerger", "SamplePlanner"],
                "status": "interfaces only; no full AI implementation",
            },
        }

    def create_version(
        self,
        actor_user_id: str,
        protocol_id: str,
        version_number: str,
        summary_of_changes: str,
        content: str,
        events: list[dict[str, Any]] | None = None,
        materials: list[dict[str, Any]] | None = None,
        media: list[dict[str, Any]] | None = None,
        expected_results: list[dict[str, Any]] | None = None,
        troubleshooting: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        protocol = self.general.get_protocol(protocol_id)
        if protocol is None:
            raise ProtocolHubValidationError("Protocol not found.")
        version = self.general.create_protocol_version(
            actor_user_id=actor_user_id,
            protocol_id=protocol_id,
            version_label=version_number,
            content=content,
            events=events or [],
        )
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE protocol_versions_general
                SET version_number = ?, summary_of_changes = ?, status = 'draft'
                WHERE protocol_version_id = ?
                """,
                (version_number, summary_of_changes, version["protocol_version_id"]),
            )
            for event in events or []:
                event_title = str(event.get("title") or "")
                if not event_title:
                    continue
                connection.execute(
                    """
                    UPDATE protocol_events_general
                    SET relative_day = COALESCE(relative_day, day),
                        relative_hour = ?,
                        default_duration = ?,
                        required = ?,
                        default_resource = ?,
                        default_units = ?
                    WHERE protocol_version_id = ? AND title = ?
                    """,
                    (
                        event.get("relative_hour"),
                        event.get("default_duration"),
                        1 if event.get("required", True) else 0,
                        event.get("default_resource"),
                        event.get("default_units"),
                        version["protocol_version_id"],
                        event_title,
                    ),
                )
            version_id = str(version["protocol_version_id"])
            for material in materials or []:
                self._insert_material(connection, version_id, material)
            for medium in media or []:
                self._insert_media(connection, version_id, medium)
            for expected in expected_results or []:
                self._insert_expected(connection, version_id, expected)
            for item in troubleshooting or []:
                self._insert_troubleshooting(connection, version_id, item)
        refreshed = self.general.get_protocol_version(str(version["protocol_version_id"]))
        assert refreshed is not None
        return refreshed | {"summary_of_changes": summary_of_changes}

    def notebook(self, protocol_version_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM protocol_notebook_documents WHERE protocol_version_id = ?", (protocol_version_id,)).fetchone()
            if not row:
                version = self.general.get_protocol_version(protocol_version_id)
                if version is None:
                    raise ProtocolHubValidationError("Protocol version not found.")
                self._ensure_notebook(connection, protocol_version_id, str(version.get("protocol_id")), str(version.get("content") or ""), str(version.get("created_by") or "system"))
                row = connection.execute("SELECT * FROM protocol_notebook_documents WHERE protocol_version_id = ?", (protocol_version_id,)).fetchone()
            assert row is not None
            return _decode(row)

    def save_notebook(self, actor_user_id: str, document_id: str, current_version: int, content: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM protocol_notebook_documents WHERE document_id = ?", (document_id,)).fetchone()
            if row is None:
                raise ProtocolHubValidationError("Notebook not found.")
            if int(row["version"]) != current_version:
                raise ProtocolHubValidationError("Protocol notebook has changed since it was loaded.")
            connection.execute(
                """
                UPDATE protocol_notebook_documents
                SET content = ?, plain_text_cache = ?, version = version + 1,
                    updated_at = CURRENT_TIMESTAMP, updated_by = ?
                WHERE document_id = ?
                """,
                (content, content.replace("#", ""), actor_user_id, document_id),
            )
            updated = connection.execute("SELECT * FROM protocol_notebook_documents WHERE document_id = ?", (document_id,)).fetchone()
            assert updated is not None
            return _decode(updated)

    def compare_versions(self, left_version_id: str, right_version_id: str) -> dict[str, Any]:
        left = self.version_workspace(left_version_id)
        right = self.version_workspace(right_version_id)
        return {
            "left": left["overview"],
            "right": right["overview"],
            "timeline_differences": _compare_named_lists(left["timeline"], right["timeline"], "title"),
            "material_differences": _compare_named_lists(left["materials"], right["materials"], "name"),
            "media_differences": _compare_named_lists(left["media"], right["media"], "recipe"),
        }

    def search(self, query: str) -> dict[str, Any]:
        return {"query": query, "results": self.list_protocols(query=query)}

    def delete_protocol(self, actor_user_id: str, protocol_id: str) -> dict[str, Any]:
        protocol = self.general.get_protocol(protocol_id)
        if protocol is None or protocol.get("archived_at"):
            raise ProtocolHubValidationError("Protocol not found.")
        if not self._can_manage_protocol(actor_user_id, protocol):
            raise PermissionError("Protocol deletion requires manage access.")
        imports = self.imports_for_protocol(protocol_id)
        storage_refs = [str(item.get("storage_reference") or "") for item in imports if item.get("storage_reference")]
        version_ids = [str(item.get("protocol_version_id")) for item in protocol.get("versions") or []]
        with self._connect() as connection:
            if version_ids:
                placeholders = ",".join("?" for _ in version_ids)
                connection.execute(f"DELETE FROM protocol_materials WHERE protocol_version_id IN ({placeholders})", version_ids)
                connection.execute(f"DELETE FROM protocol_media WHERE protocol_version_id IN ({placeholders})", version_ids)
                connection.execute(f"DELETE FROM protocol_expected_results WHERE protocol_version_id IN ({placeholders})", version_ids)
                connection.execute(f"DELETE FROM protocol_troubleshooting WHERE protocol_version_id IN ({placeholders})", version_ids)
                connection.execute(f"DELETE FROM protocol_linked_papers WHERE protocol_version_id IN ({placeholders})", version_ids)
                connection.execute(f"DELETE FROM protocol_notebook_documents WHERE protocol_version_id IN ({placeholders})", version_ids)
                connection.execute(f"DELETE FROM protocol_events_general WHERE protocol_version_id IN ({placeholders})", version_ids)
            run_rows = connection.execute(
                "SELECT run_id FROM protocol_extraction_runs WHERE protocol_id = ?",
                (protocol_id,),
            ).fetchall()
            run_ids = [str(row["run_id"]) for row in run_rows]
            if run_ids:
                placeholders = ",".join("?" for _ in run_ids)
                connection.execute(f"DELETE FROM protocol_extraction_items WHERE extraction_run_id IN ({placeholders})", run_ids)
            connection.execute("DELETE FROM protocol_extraction_runs WHERE protocol_id = ?", (protocol_id,))
            connection.execute("DELETE FROM protocol_extraction_drafts WHERE protocol_id = ?", (protocol_id,))
            connection.execute("DELETE FROM protocol_imports WHERE protocol_id = ?", (protocol_id,))
            connection.execute("DELETE FROM protocol_versions_general WHERE protocol_id = ?", (protocol_id,))
            connection.execute("DELETE FROM protocols_general WHERE protocol_id = ?", (protocol_id,))
        storage = ProtocolFileStorage(self.settings)
        for storage_ref in storage_refs:
            storage.delete(storage_ref)
        return {"deleted": True, "protocol_id": protocol_id, "attachment_policy": "protocol_imports_deleted"}

    def reorder_protocols(self, actor_user_id: str, ordered_protocol_ids: list[str]) -> list[dict[str, Any]]:
        requested_ids = self._clean_order_ids(ordered_protocol_ids, label="protocol")
        with self._connect() as connection:
            placeholders = ",".join("?" for _ in requested_ids)
            rows = connection.execute(
                f"""
                SELECT * FROM protocols_general
                WHERE protocol_id IN ({placeholders}) AND archived_at IS NULL
                """,
                requested_ids,
            ).fetchall()
        protocols = [_decode(row) for row in rows]
        if len(protocols) != len(requested_ids):
            raise ProtocolHubValidationError("Unknown protocol id in reorder request.")
        lab_ids = {str(protocol.get("lab_id") or "") for protocol in protocols}
        if len(lab_ids) != 1:
            raise ProtocolHubValidationError("Protocols must belong to the same lab.")
        group_ids = {str(protocol.get("group_id") or "") for protocol in protocols}
        if len(group_ids) != 1:
            raise ProtocolHubValidationError("Protocols must belong to the same group to reorder.")
        for protocol in protocols:
            if not self._can_manage_protocol(actor_user_id, protocol):
                raise PermissionError("Protocol reorder requires manage access.")
        with self._connect() as connection:
            first_protocol = protocols[0]
            sibling_group_id = first_protocol.get("group_id")
            lab_id = str(first_protocol.get("lab_id") or "")
            if sibling_group_id is None:
                sibling_rows = connection.execute(
                    """
                    SELECT protocol_id FROM protocols_general
                    WHERE archived_at IS NULL AND lab_id = ? AND group_id IS NULL
                    ORDER BY COALESCE(sort_index, 2147483647), protocol_id ASC
                    """,
                    (lab_id,),
                ).fetchall()
            else:
                sibling_rows = connection.execute(
                    """
                    SELECT protocol_id FROM protocols_general
                    WHERE archived_at IS NULL AND lab_id = ? AND group_id = ?
                    ORDER BY COALESCE(sort_index, 2147483647), protocol_id ASC
                    """,
                    (lab_id, sibling_group_id),
                ).fetchall()
            requested_set = set(requested_ids)
            full_order = [
                *requested_ids,
                *[
                    str(row["protocol_id"])
                    for row in sibling_rows
                    if str(row["protocol_id"]) not in requested_set
                ],
            ]
            for index, protocol_id in enumerate(full_order):
                connection.execute(
                    """
                    UPDATE protocols_general
                    SET sort_index = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE protocol_id = ?
                    """,
                    ((index + 1) * 1000, protocol_id),
                )
        by_id = {str(item["protocol_id"]): item for item in self.list_protocols()}
        return [by_id[protocol_id] for protocol_id in requested_ids if protocol_id in by_id]

    def _can_manage_protocol(self, actor_user_id: str, protocol: dict[str, Any]) -> bool:
        if actor_user_id == str(protocol.get("owner_user_id") or ""):
            return True
        access = self.general.authz.user_access(actor_user_id, str(protocol.get("lab_id") or "lab:demo"))
        return access.get("role") == "owner"

    def _require_lab_manage(self, actor_user_id: str, lab_id: str, message: str) -> None:
        access = self.general.authz.user_access(actor_user_id, lab_id)
        if access.get("role") != "owner":
            raise PermissionError(message)

    def _clean_order_ids(self, ordered_ids: list[str], *, label: str) -> list[str]:
        if not ordered_ids:
            raise ProtocolHubValidationError(f"At least one {label} id is required.")
        requested_ids = [str(item).strip() for item in ordered_ids if str(item).strip()]
        if len(requested_ids) != len(ordered_ids):
            raise ProtocolHubValidationError(f"{label.capitalize()} ids must be non-empty.")
        if len(set(requested_ids)) != len(requested_ids):
            raise ProtocolHubValidationError(f"Duplicate {label} ids are not allowed.")
        return requested_ids

    def _group_row(self, connection: sqlite3.Connection, group_id: str) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM protocol_groups WHERE group_id = ?",
            (group_id,),
        ).fetchone()

    def _next_group_sort_index(
        self,
        connection: sqlite3.Connection,
        lab_id: str,
        parent_group_id: str | None,
    ) -> int:
        if parent_group_id is None:
            row = connection.execute(
                "SELECT COALESCE(MAX(sort_index), 0) AS max_sort FROM protocol_groups WHERE lab_id = ? AND parent_group_id IS NULL",
                (lab_id,),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT COALESCE(MAX(sort_index), 0) AS max_sort FROM protocol_groups WHERE lab_id = ? AND parent_group_id = ?",
                (lab_id, parent_group_id),
            ).fetchone()
        return int(row["max_sort"] or 0) + 1000

    def _next_protocol_sort_index(
        self,
        connection: sqlite3.Connection,
        lab_id: str,
        group_id: str | None,
    ) -> int:
        if group_id is None:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(sort_index), 0) AS max_sort
                FROM protocols_general
                WHERE lab_id = ? AND group_id IS NULL AND archived_at IS NULL
                """,
                (lab_id,),
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(sort_index), 0) AS max_sort
                FROM protocols_general
                WHERE lab_id = ? AND group_id = ? AND archived_at IS NULL
                """,
                (lab_id, group_id),
            ).fetchone()
        return int(row["max_sort"] or 0) + 1000

    def _descendant_group_ids(self, connection: sqlite3.Connection, group_id: str) -> list[str]:
        descendants: list[str] = []
        pending = [group_id]
        while pending:
            current = pending.pop()
            rows = connection.execute(
                "SELECT group_id FROM protocol_groups WHERE parent_group_id = ?",
                (current,),
            ).fetchall()
            for row in rows:
                child_id = str(row["group_id"])
                descendants.append(child_id)
                pending.append(child_id)
        return descendants

    def _is_group_descendant(self, connection: sqlite3.Connection, candidate_group_id: str, ancestor_group_id: str) -> bool:
        return candidate_group_id in set(self._descendant_group_ids(connection, ancestor_group_id))

    def protocol_templates(self) -> list[dict[str, Any]]:
        """Return section-only templates. They intentionally avoid scientific details."""

        templates = [
            ("cell-culture", "Cell Culture Protocol", "maintenance", "Cells, passaging, feeding, QC, and records."),
            ("differentiation", "Differentiation Protocol", "differentiation", "Timeline, media changes, treatments, QC, and endpoints."),
            ("treatment", "Treatment Protocol", "treatment", "Groups, compound handling, timing, controls, and readouts."),
            ("immunostaining", "Immunostaining Protocol", "assay", "Fixation, blocking, antibodies, imaging, and troubleshooting."),
            ("imaging", "Imaging Protocol", "imaging", "Sample preparation, microscope settings, channels, and file handling."),
            ("rna-extraction", "RNA Extraction Protocol", "sequencing", "Sample handling, extraction, QC, and storage."),
            ("media-preparation", "Media Preparation Protocol", "media", "Components, preparation, storage, and change schedule."),
            ("blank", "Blank Protocol", "custom", "Start with an empty protocol notebook."),
        ]
        return [
            {
                "template_id": f"protocol-template:{key}",
                "name": name,
                "category": category,
                "description": description,
                "sections": [
                    "Overview",
                    "Narrative instructions",
                    "Timeline events",
                    "Materials",
                    "Media",
                    "Equipment",
                    "Expected results",
                    "QC",
                    "Troubleshooting",
                    "References",
                ],
                "content": (
                    f"# {name}\n\n"
                    "## Overview\n\n"
                    "## Narrative instructions\n\n"
                    "## Timeline events\n\n"
                    "## Materials\n\n"
                    "## Media\n\n"
                    "## Equipment\n\n"
                    "## Expected results\n\n"
                    "## QC\n\n"
                    "## Troubleshooting\n\n"
                    "## References\n"
                ),
                "note": "Template content is structural only. Add and verify scientific details before approval.",
            }
            for key, name, category, description in templates
        ]

    def create_blank_protocol(
        self,
        actor_user_id: str,
        lab_id: str,
        title: str,
        category: str | None = None,
        biological_system: str | None = None,
        sample_unit: str | None = None,
        version_number: str = "draft-1",
        content: str | None = None,
    ) -> dict[str, Any]:
        if not title.strip():
            raise ProtocolHubValidationError("Protocol title is required.")
        notebook = content or f"# {title.strip()}\n\n## Overview\n\n## Timeline\n\n## Materials\n\n## QC\n\n## References\n"
        return self.create_or_update_protocol(
            actor_user_id=actor_user_id,
            lab_id=lab_id,
            title=title.strip(),
            category=category or "custom",
            biological_system=biological_system,
            sample_unit=sample_unit,
            version_number=version_number or "draft-1",
            summary_of_changes="Blank draft created.",
            content=notebook,
            status="draft",
        )

    def create_import(
        self,
        actor_user_id: str,
        lab_id: str,
        source_type: str,
        original_filename: str | None = None,
        storage_reference: str | None = None,
        mime_type: str | None = None,
    ) -> dict[str, Any]:
        import_id = f"protocol-import:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO protocol_imports
                    (import_id, lab_id, uploaded_by, source_type, original_filename,
                     storage_reference, mime_type, extraction_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'uploaded')
                """,
                (import_id, lab_id, actor_user_id, source_type, original_filename, storage_reference, mime_type),
            )
            row = connection.execute("SELECT * FROM protocol_imports WHERE import_id = ?", (import_id,)).fetchone()
            assert row is not None
            return _decode(row)

    def upload_protocol_document(
        self,
        *,
        actor_user_id: str,
        lab_id: str,
        filename: str,
        data: bytes,
        mime_type: str | None = None,
        source_type: str | None = None,
        extracted_text: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        if not filename.strip():
            raise ProtocolHubValidationError("A filename is required.")
        import_id = f"protocol-import:{uuid.uuid4().hex[:16]}"
        storage = ProtocolFileStorage(self.settings)
        stored = storage.save(
            import_id=import_id,
            filename=filename,
            data=data,
            mime_type=mime_type,
        )
        try:
            protocol_title = self._unique_import_title(title or Path(stored.original_filename).stem)
            inferred_source_type = source_type or _source_type_for_file(stored.original_filename, stored.mime_type)
            content = (extracted_text or "").strip()
            if not content:
                content = (
                    f"# {protocol_title}\n\n"
                    "Uploaded protocol source document retained for researcher review.\n\n"
                    "No scientific details have been extracted or approved yet.\n"
                )
            protocol = self.create_or_update_protocol(
                actor_user_id=actor_user_id,
                lab_id=lab_id,
                title=protocol_title,
                short_name=protocol_title,
                description=f"Draft protocol imported from {stored.original_filename}.",
                category=inferred_source_type,
                version_number="draft-1",
                summary_of_changes="Created from uploaded protocol document.",
                content=content,
                status="draft",
            )
            imported = self._insert_protocol_import(
                import_id=import_id,
                actor_user_id=actor_user_id,
                lab_id=lab_id,
                source_type=inferred_source_type,
                protocol_id=str(protocol["protocol_id"]),
                stored=stored,
                mime_type=mime_type,
            )
        except Exception:
            storage.delete(stored.storage_path)
            raise
        protocol = self.get_protocol(str(protocol["protocol_id"])) or protocol
        return {"protocol": protocol, "import": imported, "attachment": self._import_attachment_payload(imported)}

    def create_extraction_draft_from_text(
        self,
        actor_user_id: str,
        lab_id: str,
        source_text: str,
        origin: str = "pasted_text",
        proposed_title: str | None = None,
        proposed_category: str | None = None,
        source_citation: str | None = None,
        import_id: str | None = None,
    ) -> dict[str, Any]:
        if not source_text.strip():
            raise ProtocolHubValidationError("Protocol source text is required.")
        draft = self._extract_protocol_draft(
            source_text=source_text,
            origin=origin,
            proposed_title=proposed_title,
            proposed_category=proposed_category,
            source_citation=source_citation,
        )
        return self._create_extraction_draft_record(
            actor_user_id=actor_user_id,
            lab_id=lab_id,
            source_text=source_text,
            draft=draft,
            import_id=import_id,
        )

    def extract_uploaded_protocol_document(
        self,
        *,
        actor_user_id: str,
        protocol_id: str,
        import_id: str | None = None,
        mode: str | None = None,
        user_instruction: str | None = None,
    ) -> dict[str, Any]:
        run = self.create_protocol_extraction_run(
            actor_user_id=actor_user_id,
            protocol_id=protocol_id,
            import_id=import_id,
            mode=mode,
            user_instruction=user_instruction,
        )
        draft = dict(run["draft"])
        draft["extraction_run"] = {
            "run_id": run["run_id"],
            "mode": run["mode"],
            "provider": run["provider"],
            "model": run.get("model"),
            "parser_version": run["parser_version"],
            "status": run["status"],
            "error": run.get("error"),
            "user_instruction": run.get("user_instruction"),
        }
        draft["extraction_items"] = run["items"]
        return draft

    def create_protocol_extraction_run(
        self,
        *,
        actor_user_id: str,
        protocol_id: str,
        import_id: str | None = None,
        mode: str | None = None,
        user_instruction: str | None = None,
    ) -> dict[str, Any]:
        protocol = self.get_protocol(protocol_id)
        if protocol is None:
            raise ProtocolHubValidationError("Protocol not found.")
        imports = self.imports_for_protocol(protocol_id)
        if import_id:
            imports = [item for item in imports if item.get("import_id") == import_id]
        if not imports:
            raise ProtocolHubValidationError("Protocol has no uploaded source document to extract.")
        imported = imports[0]
        path = self.import_file_path(str(imported["import_id"]))
        extracted = extract_protocol_document(
            path,
            filename=str(imported.get("original_filename") or path.name),
            mime_type=str(imported.get("mime_type") or ""),
        )
        source_text = extracted.text.strip()
        if not source_text:
            source_text = (
                f"OCR required for {imported.get('original_filename') or 'uploaded protocol document'}. "
                "No embedded text could be extracted."
            )
        draft = self._extract_protocol_draft(
            source_text=source_text,
            origin="document",
            proposed_title=str(protocol.get("title") or ""),
            proposed_category=str(protocol.get("category") or ""),
            source_citation=str(imported.get("original_filename") or ""),
        )
        canonical_document = self._canonical_protocol_document(imported, extracted, source_text)
        resolved_mode = self._resolve_extraction_mode(mode)
        provider_name = "rules"
        model = None
        ai_draft: dict[str, Any] | None = None
        ai_error: str | None = None
        if resolved_mode in {"ai_assisted", "compare_results"} and self.settings.protocol_extraction_ai_enabled:
            ai_result = classify_protocol_with_ai(
                settings=self.settings,
                canonical_blocks=list(canonical_document.get("blocks") or []),
                deterministic_draft=draft,
                user_instruction=user_instruction,
            )
            provider_name = ai_result.provider
            model = ai_result.model
            ai_draft = ai_result.draft
            ai_error = ai_result.error
            if ai_draft is not None:
                draft = ai_draft_to_legacy_draft(
                    ai_draft=ai_draft,
                    deterministic_draft=draft,
                    canonical_blocks=list(canonical_document.get("blocks") or []),
                )
        draft["warnings"] = [
            *list(draft.get("warnings") or []),
            *extracted.warnings,
        ]
        if resolved_mode in {"ai_assisted", "compare_results"} and ai_draft is None:
            draft["warnings"].append(
                f"AI-assisted extraction was unavailable; rules-only extraction was used. {ai_error or ''}".strip()
            )
        if resolved_mode in {"ai_assisted", "compare_results"}:
            draft["warnings"].append("AI-assisted extraction may contain errors. Verify all protocol details before use.")
        draft["extraction_evidence"] = {
            **dict(draft.get("extraction_evidence") or {}),
            "source_document": {
                "import_id": imported.get("import_id"),
                "original_filename": imported.get("original_filename"),
                "mime_type": imported.get("mime_type"),
                "parser_version": PROTOCOL_EXTRACTION_SCHEMA_VERSION,
                "source_type": extracted.source_type,
                "metadata": extracted.metadata,
                "tables": extracted.tables,
                "canonical_blocks": canonical_document.get("blocks") or [],
                "confidence": "high" if extracted.text.strip() else "unknown",
            },
            "extraction_mode": resolved_mode,
            "user_instruction": user_instruction,
            "ai_provider": {"provider": provider_name, "model": model, "error": ai_error},
        }
        confidence = dict(draft.get("confidence_by_field") or {})
        confidence["source_document"] = "high" if extracted.text.strip() else "unknown"
        draft["confidence_by_field"] = confidence
        legacy_draft = self._create_extraction_draft_record(
            actor_user_id=actor_user_id,
            lab_id=str(protocol.get("lab_id") or "lab:demo"),
            source_text=source_text,
            draft=draft,
            import_id=str(imported["import_id"]),
            protocol_id=protocol_id,
        )
        run_id = f"protocol-extraction-run:{uuid.uuid4().hex[:16]}"
        items = extraction_items_from_draft(
            extraction_run_id=run_id,
            draft=legacy_draft,
            origin="ai" if ai_draft is not None else "rules",
        )
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO protocol_extraction_runs
                    (run_id, protocol_id, source_attachment_id, linked_draft_id, mode, provider, model,
                     parser_version, user_instruction, status, created_by, completed_at, error,
                     canonical_document_json, deterministic_draft_json, ai_draft_json, merged_draft_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    protocol_id,
                    str(imported["import_id"]),
                    str(legacy_draft["extraction_id"]),
                    resolved_mode,
                    provider_name,
                    model,
                    PROTOCOL_EXTRACTION_SCHEMA_VERSION,
                    user_instruction,
                    actor_user_id,
                    now,
                    ai_error,
                    json.dumps(canonical_document),
                    json.dumps(self._extract_protocol_draft(
                        source_text=source_text,
                        origin="document",
                        proposed_title=str(protocol.get("title") or ""),
                        proposed_category=str(protocol.get("category") or ""),
                        source_citation=str(imported.get("original_filename") or ""),
                    )),
                    json.dumps(ai_draft) if ai_draft is not None else None,
                    json.dumps(legacy_draft),
                ),
            )
            for item in items:
                connection.execute(
                    """
                    INSERT INTO protocol_extraction_items
                        (item_id, extraction_run_id, section, source_ids_json, raw_source_text,
                         normalized_json, confidence, origin, review_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["item_id"],
                        run_id,
                        item["section"],
                        json.dumps(item.get("source_ids") or []),
                        item.get("raw_source_text"),
                        json.dumps(item.get("normalized") or {}),
                        item.get("confidence") or "unknown",
                        item.get("origin") or "rules",
                        item.get("review_status") or "needs_review",
                    ),
                )
        return self.get_protocol_extraction_run(protocol_id, run_id) | {"draft": self.get_extraction_draft(str(legacy_draft["extraction_id"]))}

    def list_protocol_extraction_runs(self, protocol_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM protocol_extraction_runs
                WHERE protocol_id = ?
                ORDER BY created_at DESC
                """,
                (protocol_id,),
            ).fetchall()
        return [self._decode_extraction_run_row(row, include_payload=False) for row in rows]

    def get_protocol_extraction_run(self, protocol_id: str, run_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM protocol_extraction_runs WHERE protocol_id = ? AND run_id = ?",
                (protocol_id, run_id),
            ).fetchone()
            if row is None:
                raise ProtocolHubValidationError("Protocol extraction run not found.")
            item_rows = connection.execute(
                "SELECT * FROM protocol_extraction_items WHERE extraction_run_id = ? ORDER BY item_id",
                (run_id,),
            ).fetchall()
        run = self._decode_extraction_run_row(row, include_payload=True)
        run["items"] = [self._decode_extraction_item_row(item) for item in item_rows]
        run["draft"] = self.get_extraction_draft(str(run.get("linked_draft_id"))) if run.get("linked_draft_id") else run.get("merged_draft")
        return run

    def update_protocol_extraction_item(
        self,
        *,
        protocol_id: str,
        run_id: str,
        item_id: str,
        updates: dict[str, Any],
        reviewer: str | None = None,
    ) -> dict[str, Any]:
        self.get_protocol_extraction_run(protocol_id, run_id)
        assignments: list[str] = []
        values: list[Any] = []
        if "review_status" in updates:
            assignments.extend(["review_status = ?", "reviewer = ?", "reviewed_at = ?"])
            values.extend([updates["review_status"], reviewer, datetime.now(timezone.utc).replace(microsecond=0).isoformat()])
        if "normalized" in updates:
            assignments.append("normalized_json = ?")
            values.append(json.dumps(updates["normalized"]))
        if "section" in updates:
            assignments.append("section = ?")
            values.append(updates["section"])
        if assignments:
            values.extend([run_id, item_id])
            with self._connect() as connection:
                connection.execute(
                    f"UPDATE protocol_extraction_items SET {', '.join(assignments)} WHERE extraction_run_id = ? AND item_id = ?",
                    values,
                )
        return self.get_protocol_extraction_run(protocol_id, run_id)

    def approve_protocol_extraction_run(
        self,
        *,
        actor_user_id: str,
        protocol_id: str,
        run_id: str,
        version_label: str,
        confirmed: bool,
    ) -> dict[str, Any]:
        run = self.get_protocol_extraction_run(protocol_id, run_id)
        draft_id = str(run.get("linked_draft_id") or "")
        if not draft_id:
            raise ProtocolHubValidationError("Extraction run is not linked to a review draft.")
        return self.approve_extraction_draft(
            actor_user_id=actor_user_id,
            extraction_id=draft_id,
            version_label=version_label,
            confirmed=confirmed,
            target_protocol_id=protocol_id,
        )

    def latest_extraction_for_protocol(self, protocol_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM protocol_extraction_drafts
                WHERE protocol_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (protocol_id,),
            ).fetchone()
            return self._decode_draft_row(row) if row else None

    def update_extraction_for_protocol(self, protocol_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        draft = self.latest_extraction_for_protocol(protocol_id)
        if draft is None:
            raise ProtocolHubValidationError("Protocol extraction draft not found.")
        return self.update_extraction_draft(str(draft["extraction_id"]), updates)

    def approve_extraction_for_protocol(self, actor_user_id: str, protocol_id: str, version_label: str, confirmed: bool) -> dict[str, Any]:
        draft = self.latest_extraction_for_protocol(protocol_id)
        if draft is None:
            raise ProtocolHubValidationError("Protocol extraction draft not found.")
        return self.approve_extraction_draft(
            actor_user_id=actor_user_id,
            extraction_id=str(draft["extraction_id"]),
            version_label=version_label,
            confirmed=confirmed,
            target_protocol_id=protocol_id,
        )

    def _create_extraction_draft_record(
        self,
        *,
        actor_user_id: str,
        lab_id: str,
        source_text: str,
        draft: dict[str, Any],
        import_id: str | None = None,
        protocol_id: str | None = None,
    ) -> dict[str, Any]:
        extraction_id = f"protocol-extraction:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO protocol_extraction_drafts
                    (extraction_id, import_id, protocol_id, lab_id, source_text, proposed_title,
                     proposed_category, proposed_biological_system, proposed_sample_unit, proposed_duration,
                     proposed_events_json, proposed_materials_json, proposed_media_json, proposed_equipment_json,
                     proposed_expected_results_json, proposed_qc_json, proposed_troubleshooting_json,
                     proposed_references_json, ambiguities_json, warnings_json, confidence_by_field_json,
                     extraction_evidence_json, status, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'awaiting_review', ?)
                """,
                (
                    extraction_id,
                    import_id,
                    protocol_id,
                    lab_id,
                    source_text,
                    draft["proposed_title"],
                    draft["proposed_category"],
                    draft["proposed_biological_system"],
                    draft["proposed_sample_unit"],
                    draft["proposed_duration"],
                    json.dumps(draft["proposed_events"]),
                    json.dumps(draft["proposed_materials"]),
                    json.dumps(draft["proposed_media"]),
                    json.dumps(draft["proposed_equipment"]),
                    json.dumps(draft["proposed_expected_results"]),
                    json.dumps(draft["proposed_qc"]),
                    json.dumps(draft["proposed_troubleshooting"]),
                    json.dumps(draft["proposed_references"]),
                    json.dumps(draft["ambiguities"]),
                    json.dumps(draft["warnings"]),
                    json.dumps(draft["confidence_by_field"]),
                    json.dumps(draft["extraction_evidence"]),
                    actor_user_id,
                ),
            )
            if import_id:
                connection.execute(
                    "UPDATE protocol_imports SET extraction_status = 'awaiting_review' WHERE import_id = ?",
                    (import_id,),
                )
        return self.get_extraction_draft(extraction_id)

    def get_extraction_draft(self, extraction_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM protocol_extraction_drafts WHERE extraction_id = ?", (extraction_id,)).fetchone()
            if row is None:
                raise ProtocolHubValidationError("Protocol extraction draft not found.")
            return self._decode_draft_row(row)

    def update_extraction_draft(self, extraction_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        allowed_scalars = {
            "proposed_title",
            "proposed_category",
            "proposed_biological_system",
            "proposed_sample_unit",
            "proposed_duration",
            "status",
        }
        allowed_json = {
            "proposed_events": "proposed_events_json",
            "proposed_materials": "proposed_materials_json",
            "proposed_media": "proposed_media_json",
            "proposed_equipment": "proposed_equipment_json",
            "proposed_expected_results": "proposed_expected_results_json",
            "proposed_qc": "proposed_qc_json",
            "proposed_troubleshooting": "proposed_troubleshooting_json",
            "proposed_references": "proposed_references_json",
            "ambiguities": "ambiguities_json",
            "warnings": "warnings_json",
            "confidence_by_field": "confidence_by_field_json",
            "extraction_evidence": "extraction_evidence_json",
        }
        assignments: list[str] = []
        values: list[Any] = []
        for key in allowed_scalars:
            if key in updates:
                assignments.append(f"{key} = ?")
                values.append(updates[key])
        for key, column in allowed_json.items():
            if key in updates:
                assignments.append(f"{column} = ?")
                values.append(json.dumps(updates[key]))
        if assignments:
            values.append(extraction_id)
            with self._connect() as connection:
                connection.execute(
                    f"UPDATE protocol_extraction_drafts SET {', '.join(assignments)} WHERE extraction_id = ?",
                    values,
                )
        return self.get_extraction_draft(extraction_id)

    def approve_extraction_draft(
        self,
        actor_user_id: str,
        extraction_id: str,
        version_label: str,
        confirmed: bool,
        target_protocol_id: str | None = None,
    ) -> dict[str, Any]:
        if not confirmed:
            raise ProtocolHubValidationError("Explicit researcher confirmation is required before approval.")
        draft = self.get_extraction_draft(extraction_id)
        title = str(draft.get("proposed_title") or "").strip()
        if not title:
            raise ProtocolHubValidationError("Protocol title is required before approval.")
        if not version_label.strip():
            raise ProtocolHubValidationError("Protocol version label is required before approval.")
        events = list(draft.get("proposed_events") or [])
        source_text = str(draft.get("source_text") or "")
        if not source_text.strip() and not events:
            raise ProtocolHubValidationError("Approval requires narrative content or at least one structured event.")
        if target_protocol_id:
            target_protocol = self.general.get_protocol(target_protocol_id)
            if target_protocol is None:
                raise ProtocolHubValidationError("Protocol not found.")
            workspace = self.version_workspace(str(target_protocol["current_version_id"]))
            merged_events = _merge_named_items(workspace["timeline"], events, "title")
            merged_materials = _merge_named_items(workspace["materials"], list(draft.get("proposed_materials") or []), "name")
            merged_media = _merge_named_items(workspace["media"], list(draft.get("proposed_media") or []), "recipe")
            merged_expected = _merge_named_items(workspace["expected_results"], list(draft.get("proposed_expected_results") or []), "title")
            merged_troubleshooting = _merge_named_items(workspace["troubleshooting"], list(draft.get("proposed_troubleshooting") or []), "issue")
            version = self.create_version(
                actor_user_id=actor_user_id,
                protocol_id=target_protocol_id,
                version_number=version_label.strip(),
                summary_of_changes="Created from reviewed protocol import draft.",
                content=source_text,
                events=merged_events,
                materials=merged_materials,
                media=merged_media,
                expected_results=merged_expected,
                troubleshooting=merged_troubleshooting,
            )
            protocol = self.get_protocol(target_protocol_id)
        else:
            protocol = self.create_or_update_protocol(
                actor_user_id=actor_user_id,
                lab_id=str(draft["lab_id"]),
                title=title,
                description="Created from reviewed protocol import draft.",
                category=draft.get("proposed_category"),
                biological_system=draft.get("proposed_biological_system"),
                sample_unit=draft.get("proposed_sample_unit"),
                version_number=version_label.strip(),
                summary_of_changes="Approved reviewed import draft.",
                content=source_text,
                events=events,
                materials=list(draft.get("proposed_materials") or []),
                media=list(draft.get("proposed_media") or []),
                expected_results=list(draft.get("proposed_expected_results") or []),
                troubleshooting=list(draft.get("proposed_troubleshooting") or []),
                status="approved",
            )
            version = {"protocol_version_id": protocol["current_version_id"]}
        with self._connect() as connection:
            connection.execute(
                "UPDATE protocol_extraction_drafts SET protocol_id = ?, status = 'approved' WHERE extraction_id = ?",
                (protocol["protocol_id"] if protocol else target_protocol_id, extraction_id),
            )
            if draft.get("import_id"):
                connection.execute(
                    "UPDATE protocol_imports SET extraction_status = 'approved' WHERE import_id = ?",
                    (draft["import_id"],),
                )
        return {"draft": self.get_extraction_draft(extraction_id), "protocol": protocol, "version": version}

    def meyer_onboarding(self) -> dict[str, Any]:
        protocol = self.get_protocol("protocol:meyer-retinal-organoid-protocol")
        return {
            "protocol": protocol,
            "source_status": "incomplete_internal_working_draft",
            "warning": "This is an incomplete internal draft. Upload or paste the authoritative Meyer protocol before approval.",
            "action": {
                "label": "Complete from Source Document",
                "route": "/protocol-hub/imports",
            },
            "must_not_infer": [
                "reagent concentrations",
                "media recipes",
                "cell numbers",
                "catalog numbers",
                "exact media-change schedules",
                "expected markers",
                "paper citations",
            ],
        }

    def usage_statistics(self, protocol_id: str) -> dict[str, Any]:
        related = self.related_experiments(protocol_id)
        active = [item for item in related if item.get("status") == "active"]
        return {
            "experiment_count": len(related),
            "currently_active": len(active),
            "last_used": max((str(item.get("updated_at") or item.get("created_at") or "") for item in related), default=None),
            "users": sorted({str(item.get("owner_user_id")) for item in related if item.get("owner_user_id")}),
            "success_metrics": "future metric; not inferred yet",
        }

    def related_experiments(self, protocol_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [
                _decode(row)
                for row in connection.execute(
                    """
                    SELECT ew.*
                    FROM experiment_workspaces ew
                    JOIN experiment_protocol_references epr ON epr.experiment_id = ew.experiment_id
                    WHERE epr.protocol_id = ?
                    ORDER BY ew.updated_at DESC
                    """,
                    (protocol_id,),
                ).fetchall()
            ]

    def events(self, protocol_version_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [_decode(row) for row in connection.execute("SELECT * FROM protocol_events_general WHERE protocol_version_id = ? ORDER BY COALESCE(relative_day, day, 999999), relative_hour", (protocol_version_id,)).fetchall()]

    def materials(self, protocol_version_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [_decode(row) for row in connection.execute("SELECT * FROM protocol_materials WHERE protocol_version_id = ? ORDER BY name", (protocol_version_id,)).fetchall()]

    def media(self, protocol_version_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [_decode(row) for row in connection.execute("SELECT * FROM protocol_media WHERE protocol_version_id = ? ORDER BY recipe", (protocol_version_id,)).fetchall()]

    def expected_results(self, protocol_version_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [_decode(row) for row in connection.execute("SELECT * FROM protocol_expected_results WHERE protocol_version_id = ? ORDER BY day", (protocol_version_id,)).fetchall()]

    def troubleshooting(self, protocol_version_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [_decode(row) for row in connection.execute("SELECT * FROM protocol_troubleshooting WHERE protocol_version_id = ? ORDER BY issue", (protocol_version_id,)).fetchall()]

    def linked_papers(self, protocol_version_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [_decode(row) for row in connection.execute("SELECT * FROM protocol_linked_papers WHERE protocol_version_id = ?", (protocol_version_id,)).fetchall()]

    def version_history(self, protocol_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [_decode(row) for row in connection.execute("SELECT * FROM protocol_versions_general WHERE protocol_id = ? ORDER BY created_at DESC", (protocol_id,)).fetchall()]

    def _protocol_summary(self, protocol_id: str) -> dict[str, Any] | None:
        protocol = self.general.get_protocol(protocol_id)
        if protocol is None:
            return None
        if protocol.get("archived_at"):
            return None
        current_version_id = str(protocol.get("current_version_id") or "")
        imports = self.imports_for_protocol(protocol_id)
        return protocol | {
            "material_count": len(self.materials(current_version_id)) if current_version_id else 0,
            "event_count": len(self.events(current_version_id)) if current_version_id else 0,
            "expected_result_count": len(self.expected_results(current_version_id)) if current_version_id else 0,
            "usage_statistics": self.usage_statistics(protocol_id),
            "unresolved_clarification_count": self._unresolved_drafts_for_protocol(protocol_id),
            "source_documents": [self._import_attachment_payload(item) for item in imports],
            "source_document": self._import_attachment_payload(imports[0]) if imports else None,
            "can_delete": True,
            "can_reorder": True,
            "capability_reason": None,
        }

    def imports_for_protocol(self, protocol_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM protocol_imports
                WHERE protocol_id = ?
                ORDER BY created_at DESC
                """,
                (protocol_id,),
            ).fetchall()
            return [_decode(row) for row in rows]

    def import_by_id(self, import_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM protocol_imports WHERE import_id = ?", (import_id,)).fetchone()
            return _decode(row) if row else None

    def import_file_path(self, import_id: str) -> Path:
        imported = self.import_by_id(import_id)
        if imported is None:
            raise ProtocolHubValidationError("Protocol import not found.")
        storage_reference = str(imported.get("storage_reference") or "")
        if not storage_reference:
            raise ProtocolHubValidationError("Protocol import has no stored file.")
        return ProtocolFileStorage(self.settings).open(storage_reference)

    def _insert_protocol_import(
        self,
        *,
        import_id: str,
        actor_user_id: str,
        lab_id: str,
        source_type: str,
        protocol_id: str,
        stored: StoredAttachment,
        mime_type: str | None = None,
    ) -> dict[str, Any]:
        metadata = {"storage_provider": "local_development"}
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO protocol_imports
                    (import_id, lab_id, uploaded_by, source_type, original_filename,
                     storage_reference, mime_type, extraction_status, protocol_id,
                     safe_filename, file_extension, size_bytes, checksum, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'uploaded', ?, ?, ?, ?, ?, ?)
                """,
                (
                    import_id,
                    lab_id,
                    actor_user_id,
                    source_type,
                    stored.original_filename,
                    stored.storage_path,
                    stored.mime_type or mime_type or mimetypes.guess_type(stored.original_filename)[0] or "application/octet-stream",
                    protocol_id,
                    stored.safe_filename,
                    stored.file_extension,
                    stored.size_bytes,
                    stored.checksum,
                    json.dumps(metadata),
                ),
            )
            row = connection.execute("SELECT * FROM protocol_imports WHERE import_id = ?", (import_id,)).fetchone()
            assert row is not None
            return _decode(row)

    def _import_attachment_payload(self, imported: dict[str, Any] | None) -> dict[str, Any] | None:
        if not imported:
            return None
        return {
            "import_id": imported.get("import_id"),
            "attachment_id": imported.get("import_id"),
            "source_type": "uploaded_file",
            "attachment_type": imported.get("source_type") or "document",
            "display_name": imported.get("original_filename") or "Protocol document",
            "original_filename": imported.get("original_filename"),
            "mime_type": imported.get("mime_type"),
            "file_extension": imported.get("file_extension"),
            "size_bytes": imported.get("size_bytes"),
            "storage_path": imported.get("storage_reference"),
            "upload_status": imported.get("extraction_status") or "uploaded",
            "processing_status": imported.get("extraction_status") or "uploaded",
            "created_at": imported.get("created_at"),
            "created_by": imported.get("uploaded_by"),
            "checksum": imported.get("checksum"),
            "metadata": imported.get("metadata") or {},
        }

    def _unique_import_title(self, title: str) -> str:
        base = title.strip() or "Imported protocol"
        candidate = base
        suffix = 2
        while self.general.get_protocol(f"protocol:{_slug(candidate)}") is not None:
            candidate = f"{base} import {suffix}"
            suffix += 1
        return candidate

    def _unresolved_drafts_for_protocol(self, protocol_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM protocol_extraction_drafts
                WHERE protocol_id = ? AND status IN ('draft', 'awaiting_review')
                """,
                (protocol_id,),
            ).fetchone()
            return int(row["count"] if row else 0)

    def _decode_draft_row(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = _decode(row)
        json_fields = {
            "proposed_events": "proposed_events_json",
            "proposed_materials": "proposed_materials_json",
            "proposed_media": "proposed_media_json",
            "proposed_equipment": "proposed_equipment_json",
            "proposed_expected_results": "proposed_expected_results_json",
            "proposed_qc": "proposed_qc_json",
            "proposed_troubleshooting": "proposed_troubleshooting_json",
            "proposed_references": "proposed_references_json",
            "ambiguities": "ambiguities_json",
            "warnings": "warnings_json",
            "confidence_by_field": "confidence_by_field_json",
            "extraction_evidence": "extraction_evidence_json",
        }
        for exposed, stored in json_fields.items():
            payload[exposed] = _json_load(payload.pop(stored, None), [] if exposed not in {"confidence_by_field", "extraction_evidence"} else {})
        payload["clarification_questions"] = self._clarification_questions(payload)
        payload["minimum_approval_requirements"] = {
            "protocol_title": bool(str(payload.get("proposed_title") or "").strip()),
            "lab": bool(str(payload.get("lab_id") or "").strip()),
            "owner": bool(str(payload.get("created_by") or "").strip()),
            "version_label": "required at approval",
            "narrative_or_event": bool(str(payload.get("source_text") or "").strip() or payload.get("proposed_events")),
            "explicit_researcher_confirmation": "required at approval",
        }
        return payload

    def _canonical_protocol_document(
        self,
        imported: dict[str, Any],
        extracted: Any,
        source_text: str,
    ) -> dict[str, Any]:
        blocks = list(getattr(extracted, "blocks", None) or [])
        if not blocks:
            blocks = [
                {
                    "block_id": f"p-{index}",
                    "type": "paragraph",
                    "heading_path": [],
                    "text": line,
                    "order": index,
                    "metadata": {},
                }
                for index, line in enumerate([line.strip() for line in source_text.splitlines() if line.strip()], start=1)
            ]
        return {
            "schema_version": PROTOCOL_EXTRACTION_SCHEMA_VERSION,
            "source_attachment_id": imported.get("import_id"),
            "source_type": getattr(extracted, "source_type", None),
            "original_filename": imported.get("original_filename"),
            "mime_type": imported.get("mime_type"),
            "metadata": getattr(extracted, "metadata", {}) or {},
            "warnings": getattr(extracted, "warnings", []) or [],
            "blocks": blocks,
        }

    def _resolve_extraction_mode(self, requested: str | None) -> str:
        normalized = (requested or "auto").strip().lower().replace("-", "_")
        if normalized in {"rules", "rules_only", "deterministic"}:
            return "rules_only"
        if normalized in {"ai", "ai_assisted"}:
            return "ai_assisted" if ai_extraction_enabled(self.settings) and self.settings.protocol_extraction_ai_enabled else "rules_only"
        if normalized in {"compare", "compare_results"}:
            return "compare_results" if ai_extraction_enabled(self.settings) and self.settings.protocol_extraction_ai_enabled else "rules_only"
        return "ai_assisted" if ai_extraction_enabled(self.settings) and self.settings.protocol_extraction_ai_enabled else "rules_only"

    def _decode_extraction_run_row(self, row: sqlite3.Row, *, include_payload: bool) -> dict[str, Any]:
        payload = _decode(row)
        payload["canonical_document"] = _json_load(payload.pop("canonical_document_json", None), {}) if include_payload else None
        payload["deterministic_draft"] = _json_load(payload.pop("deterministic_draft_json", None), {}) if include_payload else None
        payload["ai_draft"] = _json_load(payload.pop("ai_draft_json", None), None) if include_payload else None
        payload["merged_draft"] = _json_load(payload.pop("merged_draft_json", None), {}) if include_payload else None
        if not include_payload:
            payload.pop("canonical_document_json", None)
            payload.pop("deterministic_draft_json", None)
            payload.pop("ai_draft_json", None)
            payload.pop("merged_draft_json", None)
        return payload

    def _decode_extraction_item_row(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = _decode(row)
        payload["source_ids"] = _json_load(payload.pop("source_ids_json", None), [])
        payload["normalized"] = _json_load(payload.pop("normalized_json", None), {})
        return payload

    def _extract_protocol_draft(
        self,
        source_text: str,
        origin: str,
        proposed_title: str | None = None,
        proposed_category: str | None = None,
        source_citation: str | None = None,
    ) -> dict[str, Any]:
        text = source_text.strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        title = proposed_title or self._suggest_title(lines)
        lower = text.lower()
        biological_system = "retinal organoid" if "retinal organoid" in lower else None
        sample_unit = "organoid" if re.search(r"\borganoids?\b", lower) else None
        events = self._extract_events(text, origin)
        days = [int(event["relative_day"]) for event in events if event.get("relative_day") is not None]
        duration = f"through D{max(days)}" if days else None
        refs = [{"reference": source_citation, "origin": origin, "confidence": "medium"}] if source_citation else []
        evidence: dict[str, Any] = {
            "source_text": {"confidence": "high", "origin": origin, "excerpt": text[:500]},
        }
        confidence: dict[str, str] = {"source_text": "high"}
        if title:
            evidence["proposed_title"] = {"confidence": "medium", "origin": origin, "excerpt": title}
            confidence["proposed_title"] = "medium"
        if biological_system:
            excerpt = self._excerpt_around(text, "retinal organoid")
            evidence["proposed_biological_system"] = {"confidence": "high", "origin": origin, "excerpt": excerpt}
            confidence["proposed_biological_system"] = "high"
        if sample_unit:
            excerpt = self._excerpt_around(text, "organoid")
            evidence["proposed_sample_unit"] = {"confidence": "high", "origin": origin, "excerpt": excerpt}
            confidence["proposed_sample_unit"] = "high"
        if duration:
            evidence["proposed_duration"] = {"confidence": "medium", "origin": origin, "excerpt": duration}
            confidence["proposed_duration"] = "medium"
        materials = self._extract_materials(text, origin)
        media = self._extract_media(text, origin)
        expected_results = self._extract_expected_results(text, origin)
        qc = self._extract_qc(text, origin)
        troubleshooting = self._extract_troubleshooting(text, origin)
        unclassified = self._unclassified_notes(text)
        if unclassified:
            evidence["unclassified_notes"] = {
                "confidence": "low",
                "origin": origin,
                "items": unclassified[:20],
            }
        ambiguities = []
        warnings = ["Extracted fields are proposals and require researcher review before approval."]
        if not title:
            ambiguities.append("Protocol title is missing.")
        if "bmp4" in lower and not re.search(r"bmp4[^\n.;,]*(\d+(\.\d+)?)\s*(ng/ml|nm|um|µm|ug/ml|µg/ml)", lower):
            ambiguities.append("BMP4 is mentioned, but the final concentration is not explicit.")
        if not re.search(r"\b(media change|feed|feeding|change medium)\b", lower):
            ambiguities.append("Media-change schedule is not specified.")
        if not re.search(r"\b(endpoint|end point|through d\d+|until d\d+)\b", lower):
            ambiguities.append("Expected protocol endpoint is not explicit.")
        if not events:
            ambiguities.append("No timed protocol events were detected.")
        return {
            "proposed_title": title,
            "proposed_category": proposed_category or self._suggest_category(lower),
            "proposed_biological_system": biological_system,
            "proposed_sample_unit": sample_unit,
            "proposed_duration": duration,
            "proposed_events": events,
            "proposed_materials": materials,
            "proposed_media": media,
            "proposed_equipment": [],
            "proposed_expected_results": expected_results,
            "proposed_qc": qc,
            "proposed_troubleshooting": troubleshooting,
            "proposed_references": refs,
            "ambiguities": ambiguities,
            "warnings": warnings,
            "confidence_by_field": confidence,
            "extraction_evidence": evidence,
        }

    def _suggest_title(self, lines: list[str]) -> str | None:
        for line in lines[:5]:
            cleaned = line.lstrip("# ").strip()
            if cleaned and len(cleaned) <= 120:
                return cleaned
        return None

    def _suggest_category(self, lower_text: str) -> str:
        if "immunostain" in lower_text or "antibody" in lower_text:
            return "assay"
        if "media" in lower_text:
            return "media"
        if "differentiation" in lower_text or "organoid" in lower_text:
            return "differentiation"
        if "treatment" in lower_text or "compound" in lower_text:
            return "treatment"
        return "custom"

    def _extract_events(self, text: str, origin: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        seen: set[tuple[int, str]] = set()
        for match in re.finditer(r"\bD(?:ay\s*)?(\d{1,3})\b", text, flags=re.IGNORECASE):
            day = int(match.group(1))
            excerpt = self._sentence_for_index(text, match.start())
            title = self._event_title_from_excerpt(excerpt, day)
            key = (day, title.lower())
            if key in seen:
                continue
            seen.add(key)
            events.append(
                {
                    "title": title,
                    "relative_day": day,
                    "event_type": self._event_type_from_excerpt(excerpt),
                    "description": excerpt,
                    "required": True,
                    "confidence": "medium",
                    "origin": origin,
                    "source_excerpt": excerpt,
                    "source_location": "source text",
                    "draft_status": "proposed",
                }
            )
        return events

    def _event_title_from_excerpt(self, excerpt: str, day: int) -> str:
        lower = excerpt.lower()
        if "bmp4" in lower:
            return "BMP4"
        if "attach" in lower:
            return "Attachment event"
        if "media" in lower or "feed" in lower:
            return "Media change"
        if "image" in lower or "imaging" in lower:
            return "Imaging"
        if "collect" in lower or "collection" in lower:
            return "Collection"
        if "qc" in lower:
            return "QC"
        return f"Protocol event D{day}"

    def _event_type_from_excerpt(self, excerpt: str) -> str:
        lower = excerpt.lower()
        if "media" in lower or "feed" in lower:
            return "media_change"
        if "bmp4" in lower or "compound" in lower or "treat" in lower:
            return "compound"
        if "image" in lower or "imaging" in lower:
            return "imaging"
        if "collect" in lower or "collection" in lower:
            return "collection"
        if "qc" in lower:
            return "qc"
        return "protocol_step"

    def _extract_materials(self, text: str, origin: str) -> list[dict[str, Any]]:
        lower = text.lower()
        materials: list[dict[str, Any]] = []
        seen: set[str] = set()
        for name in ["BMP4", "SAG", "DMSO", "GRKi"]:
            if name.lower() in lower:
                excerpt = self._excerpt_around(text, name)
                seen.add(name.lower())
                materials.append(
                    {
                        "name": name,
                        "required": True,
                        "concentration": _first_concentration(excerpt),
                        "notes": "Mentioned in source text; vendor, catalog number, lot, and concentration require review.",
                        "confidence": "medium",
                        "origin": origin,
                        "source_excerpt": excerpt,
                        "source_location": "source text",
                        "draft_status": "proposed",
                    }
                )
        for line in self._section_lines(text, {"materials", "material", "reagents", "reagent", "supplies"}):
            name = _material_name_from_line(line)
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            materials.append(
                {
                    "name": name,
                    "catalog_number": _first_catalog_number(line),
                    "concentration": _first_concentration(line),
                    "required": True,
                    "notes": line,
                    "confidence": "medium" if _first_concentration(line) or _first_catalog_number(line) else "low",
                    "origin": origin,
                    "source_excerpt": line,
                    "source_location": "materials/reagents section",
                    "draft_status": "proposed",
                }
            )
        return materials

    def _extract_media(self, text: str, origin: str) -> list[dict[str, Any]]:
        media: list[dict[str, Any]] = []
        for line in self._section_lines(text, {"media", "medium", "media recipe", "recipes"}):
            if not line.strip():
                continue
            media.append(
                {
                    "recipe": line[:80],
                    "components": [],
                    "preparation": line,
                    "storage": _storage_from_line(line),
                    "media_change_schedule": line if re.search(r"\b(feed|change|media change)\b", line, re.I) else None,
                    "confidence": "low",
                    "origin": origin,
                    "source_excerpt": line,
                    "source_location": "media section",
                    "draft_status": "proposed",
                }
            )
        return media

    def _extract_expected_results(self, text: str, origin: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        lines = self._section_lines(text, {"expected results", "results", "expected outcome", "morphology"})
        for line in lines:
            results.append(
                {
                    "title": line[:80],
                    "description": line,
                    "day": _first_day(line),
                    "confidence": "low",
                    "origin": origin,
                    "source_excerpt": line,
                    "source_location": "expected results section",
                    "draft_status": "proposed",
                }
            )
        return results

    def _extract_qc(self, text: str, origin: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for line in self._section_lines(text, {"qc", "quality control", "checkpoint", "acceptance criteria"}):
            items.append(
                {
                    "title": line[:80],
                    "description": line,
                    "day": _first_day(line),
                    "confidence": "low",
                    "origin": origin,
                    "source_excerpt": line,
                    "source_location": "qc section",
                    "draft_status": "proposed",
                }
            )
        return items

    def _extract_troubleshooting(self, text: str, origin: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for line in self._section_lines(text, {"troubleshooting", "problems", "problem", "failure"}):
            items.append(
                {
                    "issue": line[:80],
                    "possible_causes": [],
                    "possible_solutions": [line] if re.search(r"\b(try|use|increase|decrease|replace|check)\b", line, re.I) else [],
                    "confidence": "low",
                    "origin": origin,
                    "source_excerpt": line,
                    "source_location": "troubleshooting section",
                    "draft_status": "proposed",
                }
            )
        return items

    def _section_lines(self, text: str, headings: set[str]) -> list[str]:
        lines = [line.strip().strip("#:") for line in text.splitlines()]
        selected: list[str] = []
        active = False
        for line in lines:
            if not line:
                continue
            normalized = re.sub(r"^\d+[\).]\s*", "", line).strip().lower()
            is_heading = len(normalized) <= 48 and any(normalized == heading or normalized.startswith(f"{heading}:") for heading in headings)
            if is_heading:
                active = True
                remainder = line.split(":", 1)[1].strip() if ":" in line else ""
                if remainder:
                    selected.append(remainder)
                continue
            if active and len(normalized) <= 48 and re.match(r"^[A-Z][A-Za-z /&-]+$", line):
                active = False
            if active:
                selected.append(line)
        return selected

    def _unclassified_notes(self, text: str) -> list[str]:
        notes: list[str] = []
        for line in [line.strip() for line in text.splitlines() if line.strip()]:
            lower = line.lower()
            if re.search(r"\b(day|d\d+|materials?|reagents?|media|qc|troubleshoot|expected)\b", lower):
                continue
            if len(line) > 20:
                notes.append(line)
        return notes

    def _sentence_for_index(self, text: str, index: int) -> str:
        start_candidates = [text.rfind(".", 0, index), text.rfind("\n", 0, index), text.rfind(";", 0, index)]
        end_candidates = [pos for pos in [text.find(".", index), text.find("\n", index), text.find(";", index)] if pos != -1]
        start = max(start_candidates) + 1
        end = min(end_candidates) if end_candidates else min(len(text), index + 160)
        return text[start:end].strip()

    def _excerpt_around(self, text: str, needle: str) -> str:
        match = re.search(re.escape(needle), text, flags=re.IGNORECASE)
        if not match:
            return ""
        start = max(0, match.start() - 80)
        end = min(len(text), match.end() + 80)
        return text[start:end].strip()

    def _clarification_questions(self, draft: dict[str, Any]) -> list[dict[str, str]]:
        questions: list[dict[str, str]] = []
        ambiguities = [str(item).lower() for item in draft.get("ambiguities") or []]
        if any("title" in item for item in ambiguities):
            questions.append({"field": "proposed_title", "question": "What should this protocol be titled?"})
        if any("bmp4" in item for item in ambiguities):
            questions.append({"field": "materials.BMP4.concentration", "question": "What is the final BMP4 concentration?"})
        if any("media-change" in item or "media change" in item for item in ambiguities):
            questions.append({"field": "media.media_change_schedule", "question": "What media-change schedule should be used?"})
        if any("endpoint" in item for item in ambiguities):
            questions.append({"field": "proposed_duration", "question": "What is the expected protocol endpoint?"})
        if any("timed protocol events" in item for item in ambiguities):
            questions.append({"field": "proposed_events", "question": "What timed events should be added to the protocol timeline?"})
        if not questions:
            questions.append({"field": "review", "question": "Review each proposed field before approval."})
        return questions

    def _insert_event(self, connection: sqlite3.Connection, version_id: str, event: dict[str, Any]) -> None:
        event_id = event.get("event_id") or f"protocol-event:{version_id}:{_slug(str(event.get('title') or uuid.uuid4().hex))}"
        relative_day = event.get("relative_day", event.get("day"))
        connection.execute(
            """
            INSERT INTO protocol_events_general
                (protocol_event_id, protocol_version_id, title, description, day, relative_day, relative_hour,
                 event_type, default_resource_id, default_resource, default_concentration, default_units,
                 default_duration, required, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(protocol_event_id) DO NOTHING
            """,
            (
                event_id,
                version_id,
                event.get("title"),
                event.get("description"),
                relative_day,
                relative_day,
                event.get("relative_hour"),
                event.get("event_type", "custom"),
                event.get("default_resource_id"),
                event.get("default_resource"),
                event.get("default_concentration"),
                event.get("default_units"),
                event.get("default_duration"),
                1 if event.get("required", True) else 0,
                json.dumps(event.get("metadata") or {}),
            ),
        )

    def _insert_material(self, connection: sqlite3.Connection, version_id: str, material: dict[str, Any]) -> None:
        material_id = material.get("material_id") or f"protocol-material:{version_id}:{_slug(str(material.get('name') or uuid.uuid4().hex))}"
        connection.execute(
            """
            INSERT INTO protocol_materials
                (material_id, protocol_version_id, inventory_item_id, name, vendor, catalog_number,
                 concentration, required, substitutions_json, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(material_id) DO NOTHING
            """,
            (
                material_id,
                version_id,
                material.get("inventory_item_id"),
                material.get("name"),
                material.get("vendor"),
                material.get("catalog_number"),
                material.get("concentration"),
                1 if material.get("required", True) else 0,
                json.dumps(material.get("substitutions") or []),
                material.get("notes"),
            ),
        )

    def _insert_media(self, connection: sqlite3.Connection, version_id: str, medium: dict[str, Any]) -> None:
        media_id = medium.get("media_id") or f"protocol-media:{version_id}:{_slug(str(medium.get('recipe') or uuid.uuid4().hex))}"
        connection.execute(
            """
            INSERT INTO protocol_media
                (media_id, protocol_version_id, recipe, components_json, preparation, storage, media_change_schedule)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(media_id) DO NOTHING
            """,
            (media_id, version_id, medium.get("recipe", "Media"), json.dumps(medium.get("components") or []), medium.get("preparation"), medium.get("storage"), medium.get("media_change_schedule")),
        )

    def _insert_expected(self, connection: sqlite3.Connection, version_id: str, expected: dict[str, Any]) -> None:
        result_id = expected.get("expected_result_id") or f"protocol-expected:{version_id}:{_slug(str(expected.get('title') or uuid.uuid4().hex))}"
        connection.execute(
            """
            INSERT INTO protocol_expected_results
                (expected_result_id, protocol_version_id, stage_label, day, title, description, markers_json, qc_metrics_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(expected_result_id) DO NOTHING
            """,
            (result_id, version_id, expected.get("stage_label"), expected.get("day"), expected.get("title"), expected.get("description"), json.dumps(expected.get("markers") or []), json.dumps(expected.get("qc_metrics") or {}), json.dumps(expected.get("metadata") or {})),
        )

    def _insert_troubleshooting(self, connection: sqlite3.Connection, version_id: str, entry: dict[str, Any]) -> None:
        troubleshooting_id = entry.get("troubleshooting_id") or f"protocol-trouble:{version_id}:{_slug(str(entry.get('issue') or uuid.uuid4().hex))}"
        connection.execute(
            """
            INSERT INTO protocol_troubleshooting
                (troubleshooting_id, protocol_version_id, issue, possible_causes_json, possible_solutions_json, linked_papers_json, linked_images_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(troubleshooting_id) DO NOTHING
            """,
            (troubleshooting_id, version_id, entry.get("issue"), json.dumps(entry.get("possible_causes") or []), json.dumps(entry.get("possible_solutions") or []), json.dumps(entry.get("linked_papers") or []), json.dumps(entry.get("linked_images") or [])),
        )

    def _ensure_notebook(self, connection: sqlite3.Connection, version_id: str, title: str, content: str, actor_user_id: str) -> None:
        document_id = f"protocol-notebook:{version_id}"
        connection.execute(
            """
            INSERT INTO protocol_notebook_documents
                (document_id, protocol_version_id, title, document_format, content, plain_text_cache, updated_by)
            VALUES (?, ?, ?, 'markdown', ?, ?, ?)
            ON CONFLICT(document_id) DO NOTHING
            """,
            (document_id, version_id, title, content, content.replace("#", ""), actor_user_id),
        )


def _compare_named_lists(left: list[dict[str, Any]], right: list[dict[str, Any]], key: str) -> dict[str, list[str]]:
    left_names = {str(item.get(key) or "") for item in left}
    right_names = {str(item.get(key) or "") for item in right}
    return {
        "shared": sorted(left_names & right_names),
        "left_only": sorted(left_names - right_names),
        "right_only": sorted(right_names - left_names),
    }


def _merge_named_items(existing: list[dict[str, Any]], proposed: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = [dict(item) for item in existing]
    seen = {str(item.get(key) or "").strip().lower() for item in merged if str(item.get(key) or "").strip()}
    for item in proposed:
        name = str(item.get(key) or "").strip().lower()
        if name and name in seen:
            continue
        merged.append(dict(item))
        if name:
            seen.add(name)
    return merged


def _first_concentration(text: str) -> str | None:
    match = re.search(
        r"\b\d+(?:\.\d+)?\s*(?:nM|uM|µM|mM|M|ng/mL|ug/mL|µg/mL|mg/mL|%|x|X)\b",
        text,
        flags=re.IGNORECASE,
    )
    return match.group(0) if match else None


def _first_catalog_number(text: str) -> str | None:
    match = re.search(r"\b(?:cat(?:alog)?\.?\s*#?|SKU)\s*[:#]?\s*([A-Za-z0-9._-]+)", text, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _first_day(text: str) -> int | None:
    match = re.search(r"\bD(?:ay\s*)?(\d{1,3})\b", text, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _material_name_from_line(line: str) -> str:
    cleaned = re.sub(r"^[-*•\d\).]+\s*", "", line.strip())
    if not cleaned:
        return ""
    for separator in ["\t", ",", ";", " - ", ":"]:
        if separator in cleaned:
            cleaned = cleaned.split(separator, 1)[0].strip()
            break
    cleaned = re.sub(r"\s{2,}.*$", "", cleaned)
    return cleaned[:80]


def _storage_from_line(line: str) -> str | None:
    match = re.search(r"\b(?:store|storage|keep)\b.*", line, flags=re.IGNORECASE)
    return match.group(0)[:160] if match else None


def _timestamp_sql_value(status: str) -> str | None:
    if status != "approved":
        return None
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _source_type_for_file(filename: str, mime_type: str | None = None) -> str:
    extension = Path(filename or "").suffix.lower()
    if extension == ".pdf" or mime_type == "application/pdf":
        return "pdf"
    if extension in {".doc", ".docx", ".rtf"}:
        return "docx" if extension == ".docx" else extension.removeprefix(".")
    if extension in {".xls", ".xlsx", ".csv"}:
        return extension.removeprefix(".")
    if extension in {".txt", ".md"}:
        return "txt" if extension == ".txt" else "markdown"
    return "document"


def _json_load(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return fallback
