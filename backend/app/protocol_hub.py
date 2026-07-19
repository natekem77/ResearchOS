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
                """
            )
            self._ensure_column(connection, "protocol_imports", "protocol_id", "TEXT")
            self._ensure_column(connection, "protocol_imports", "safe_filename", "TEXT")
            self._ensure_column(connection, "protocol_imports", "file_extension", "TEXT")
            self._ensure_column(connection, "protocol_imports", "size_bytes", "INTEGER")
            self._ensure_column(connection, "protocol_imports", "checksum", "TEXT")
            self._ensure_column(connection, "protocol_imports", "metadata_json", "TEXT NOT NULL DEFAULT '{}'")

    def _ensure_column(self, connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

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
                     default_sample_unit, owner_user_id, current_version_id, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                (protocol_id, lab_id, title, short_name, description, category, biological_system, sample_unit, actor_user_id, version_id, status),
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
        protocols = self.general.list_protocols()
        enriched = [self._protocol_summary(protocol["protocol_id"]) for protocol in protocols]
        if query:
            q = query.lower()
            enriched = [item for item in enriched if q in json.dumps(item).lower()]
        return [item for item in enriched if item is not None]

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

    def create_version(self, actor_user_id: str, protocol_id: str, version_number: str, summary_of_changes: str, content: str, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
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
                VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'awaiting_review', ?)
                """,
                (
                    extraction_id,
                    import_id,
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
            version = self.create_version(
                actor_user_id=actor_user_id,
                protocol_id=target_protocol_id,
                version_number=version_label.strip(),
                summary_of_changes="Created from reviewed protocol import draft.",
                content=source_text,
                events=events,
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
            "proposed_materials": self._extract_materials(text, origin),
            "proposed_media": [],
            "proposed_equipment": [],
            "proposed_expected_results": [],
            "proposed_qc": [],
            "proposed_troubleshooting": [],
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
        for name in ["BMP4", "SAG", "DMSO", "GRKi"]:
            if name.lower() in lower:
                excerpt = self._excerpt_around(text, name)
                materials.append(
                    {
                        "name": name,
                        "required": True,
                        "notes": "Mentioned in source text; vendor, catalog number, lot, and concentration require review.",
                        "confidence": "medium",
                        "origin": origin,
                        "source_excerpt": excerpt,
                    }
                )
        return materials

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
