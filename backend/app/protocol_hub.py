"""Structured, versioned scientific protocol hub for ResearchOS."""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from app.config import Settings
from app.general_experiments import GeneralExperimentService, _decode, _slug
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
                """
            )

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
                "events": [
                    {"title": "Aggregate cells", "relative_day": 0, "event_type": "protocol_step", "description": "Start aggregation."},
                    {"title": "BMP4", "relative_day": 6, "event_type": "compound", "default_concentration": "protocol-defined", "description": "BMP4 pulse."},
                    {"title": "Attach organoids", "relative_day": 9, "event_type": "protocol_step"},
                    {"title": "QC morphology", "relative_day": 16, "event_type": "qc"},
                ],
                "materials": [{"name": "BMP4", "vendor": "Demo Vendor", "concentration": "protocol-defined"}],
                "expected": [{"day": 16, "stage_label": "D16", "title": "Early retinal neuroepithelium", "markers": ["VSX2"]}],
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
                description=f"Structured demo protocol: {demo['title']}.",
                category=demo["category"],
                biological_system=demo.get("biological_system"),
                sample_unit=demo.get("sample_unit"),
                version_number="1.0",
                summary_of_changes="Initial structured demo version.",
                content=f"# {demo['title']}\n\nStructured protocol notebook foundation.",
                events=demo.get("events", []),
                materials=demo.get("materials", []),
                expected_results=demo.get("expected", []),
                troubleshooting=[
                    {
                        "issue": "Low reproducibility",
                        "possible_causes": ["Timing deviation", "Reagent lot change"],
                        "possible_solutions": ["Review timeline", "Check inventory lot metadata"],
                    }
                ],
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
                    updated_at = CURRENT_TIMESTAMP
                """,
                (protocol_id, lab_id, title, short_name, description, category, biological_system, sample_unit, actor_user_id, version_id, status),
            )
            connection.execute(
                """
                INSERT INTO protocol_versions_general
                    (protocol_version_id, protocol_id, version_label, version_number, summary_of_changes,
                     content, created_by, approved_by, approved_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(protocol_version_id) DO NOTHING
                """,
                (version_id, protocol_id, version_number, version_number, summary_of_changes, content, actor_user_id, actor_user_id, status),
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
        return protocol | {
            "material_count": len(self.materials(current_version_id)) if current_version_id else 0,
            "event_count": len(self.events(current_version_id)) if current_version_id else 0,
            "expected_result_count": len(self.expected_results(current_version_id)) if current_version_id else 0,
            "usage_statistics": self.usage_statistics(protocol_id),
        }

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
