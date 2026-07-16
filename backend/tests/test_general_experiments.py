"""Tests for the generalized experiment workspace foundation."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.attachment_storage import AttachmentStorageError, LocalAttachmentStorage
from app.config import Settings
from app.experiments import Experiment
from app.general_experiments import (
    CANONICAL_BLANK_DELTA_JSON,
    ExperimentAuthorizationError,
    ExperimentConflictError,
    ExperimentValidationError,
    GeneralExperimentService,
    RichNotebookContextService,
    SamplePlanningService,
    canonical_notebook_delta_json,
)
from app.storage import SQLiteStore


class GeneralExperimentTests(unittest.TestCase):
    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def _service(self, tmpdir: str) -> GeneralExperimentService:
        return GeneralExperimentService(settings=self._settings(tmpdir))

    def test_create_blank_experiment_allows_partial_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment(
                "user:researcher-a",
                "lab:demo",
                "Generic cell culture pilot",
                biological_system="primary cells",
                sample_unit_type="dish",
            )

        self.assertEqual(experiment["status"], "draft")
        self.assertEqual(experiment["sample_unit_type"], "dish")

    def test_notebook_first_workspace_exposes_notebook_and_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment(
                "user:researcher-a",
                "lab:demo",
                "Notebook-first experiment",
            )
            workspace = service.get_workspace(experiment["experiment_id"], "user:researcher-a")

        assert workspace is not None
        self.assertEqual(workspace["layout"]["primary_surface"], "notebook")
        self.assertTrue(workspace["layout"]["notebook_remains_visible"])
        self.assertTrue(workspace["notebook"]["document_id"])
        self.assertTrue(any(tool["tool_id"] == "protocols" for tool in workspace["tool_palette"]))

    def test_new_notebook_starts_as_blank_rich_document_without_title_duplication(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment(
                "user:researcher-a",
                "lab:demo",
                "No duplicated title",
            )
            notebook = service.get_or_create_notebook("user:researcher-a", experiment["experiment_id"])

        self.assertEqual(notebook["document_format"], "rich_text_delta_json")
        self.assertEqual(notebook["plain_text_cache"], "")
        self.assertNotIn("No duplicated title", notebook["content"])

    def test_protocol_tool_attach_preserves_notebook_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment(
                "user:researcher-a",
                "lab:demo",
                "Protocol tool attach",
            )
            notebook = service.get_or_create_notebook("user:researcher-a", experiment["experiment_id"])
            service.save_notebook(
                "user:researcher-a",
                notebook["document_id"],
                notebook["version"],
                "Free-form notebook notes stay primary.",
            )
            protocol = service.get_protocol("protocol:meyer-retinal-organoid-protocol")
            assert protocol is not None
            service.link_protocol(
                "user:researcher-a",
                experiment["experiment_id"],
                protocol["protocol_id"],
                protocol["current_version_id"],
                inherit_events=True,
            )
            workspace = service.get_workspace(experiment["experiment_id"], "user:researcher-a")

        assert workspace is not None
        self.assertIn("Free-form notebook notes stay primary.", workspace["notebook"]["content"])
        self.assertTrue(workspace["design"]["protocol_references"])
        self.assertTrue(any(event["source"] == "protocol" for event in workspace["timeline"]["events"]))

    def test_update_experiment_title_persists_and_handles_empty_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment(
                "user:researcher-a",
                "lab:demo",
                "Original title",
            )
            updated = service.update_experiment_title(
                "user:researcher-a",
                experiment["experiment_id"],
                "Edited title",
            )
            fallback = service.update_experiment_title(
                "user:researcher-a",
                experiment["experiment_id"],
                "   ",
            )
            workspace = service.get_workspace(experiment["experiment_id"], "user:researcher-a")

        assert workspace is not None
        self.assertEqual(updated["title"], "Edited title")
        self.assertEqual(fallback["title"], "Untitled Experiment")
        self.assertEqual(workspace["experiment"]["title"], "Untitled Experiment")

    def test_saved_experiment_is_listed_and_reopenable_after_service_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment(
                "user:researcher-a",
                "lab:demo",
                "Attachment Persistence Test",
            )
            experiment_id = experiment["experiment_id"]
            listed = service.list_experiments("user:researcher-a", lab_id="lab:demo")
            restarted = self._service(tmpdir)
            reopened = restarted.get_workspace(experiment_id, "user:researcher-a")
            relisted = restarted.list_experiments("user:researcher-a", lab_id="lab:demo")

        self.assertTrue(any(item["experiment_id"] == experiment_id for item in listed))
        assert reopened is not None
        self.assertEqual(reopened["experiment"]["title"], "Attachment Persistence Test")
        self.assertTrue(any(item["experiment_id"] == experiment_id for item in relisted))

    def test_delete_experiment_soft_archives_and_retains_attachments(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment(
                "user:researcher-a",
                "lab:demo",
                "Delete me",
            )
            attachment = service.create_link_attachment(
                "user:researcher-a",
                experiment["experiment_id"],
                {"external_url": "https://example.com/data.csv", "display_name": "Data link"},
            )
            deleted = service.delete_experiment(
                "user:researcher-a",
                experiment["experiment_id"],
            )
            listed = service.list_experiments("user:researcher-a", lab_id="lab:demo")
            reopened = service.get_workspace(experiment["experiment_id"], "user:researcher-a")
            with service._connect() as connection:
                retained_attachment = connection.execute(
                    "SELECT * FROM experiment_notebook_attachments WHERE attachment_id = ?",
                    (attachment["attachment_id"],),
                ).fetchone()

        self.assertTrue(deleted["deleted"])
        self.assertTrue(deleted["archived"])
        self.assertEqual(deleted["attachment_policy"], "retained")
        self.assertFalse(any(item["experiment_id"] == experiment["experiment_id"] for item in listed))
        self.assertIsNone(reopened)
        self.assertIsNotNone(retained_attachment)

    def test_delete_experiment_missing_and_unauthorized_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment(
                "user:researcher-a",
                "lab:demo",
                "Private delete",
            )

            with self.assertRaises(ExperimentValidationError):
                service.delete_experiment("user:researcher-a", "experiment:missing")
            with self.assertRaises(ExperimentAuthorizationError):
                service.delete_experiment("user:guest", experiment["experiment_id"])

    def test_delete_general_experiment_api_route_matches_flutter_request(self) -> None:
        from app.main import app

        matching_routes = [
            (index, route)
            for index, route in enumerate(app.routes)
            if getattr(route, "path", None) == "/experiments/{experiment_id}/general"
        ]
        methods = set().union(*(getattr(route, "methods", set()) for _, route in matching_routes))
        delete_index = min(
            index
            for index, route in matching_routes
            if "DELETE" in getattr(route, "methods", set())
        )
        put_index = min(
            index
            for index, route in matching_routes
            if "PUT" in getattr(route, "methods", set())
        )

        self.assertIn("DELETE", methods)
        self.assertLess(delete_index, put_index)

    def test_reorder_mobile_experiments_route_precedes_dynamic_detail_route(self) -> None:
        from app.main import app

        route_entries = [
            (index, route)
            for index, route in enumerate(app.routes)
            if getattr(route, "path", None)
            in {
                "/mobile/experiments/reorder",
                "/mobile/experiments/{experiment_id}",
            }
        ]
        reorder_index = min(
            index
            for index, route in route_entries
            if getattr(route, "path", None) == "/mobile/experiments/reorder"
        )
        detail_index = min(
            index
            for index, route in route_entries
            if getattr(route, "path", None) == "/mobile/experiments/{experiment_id}"
        )
        methods = set().union(
            *(
                getattr(route, "methods", set())
                for _, route in route_entries
                if getattr(route, "path", None) == "/mobile/experiments/reorder"
            )
        )

        self.assertIn("POST", methods)
        self.assertLess(reorder_index, detail_index)

    def test_delete_general_experiment_wrong_method_returns_405(self) -> None:
        from app.main import app

        matching_routes = [
            route
            for route in app.routes
            if getattr(route, "path", None) == "/experiments/{experiment_id}/general"
        ]
        methods = set().union(*(getattr(route, "methods", set()) for route in matching_routes))

        self.assertNotIn("POST", methods)

    def test_reorder_experiments_persists_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            first = service.create_blank_experiment("user:researcher-a", "lab:demo", "Entry A")
            second = service.create_blank_experiment("user:researcher-a", "lab:demo", "Entry B")
            third = service.create_blank_experiment("user:researcher-a", "lab:demo", "Entry C")
            reordered = service.reorder_experiments(
                "user:researcher-a",
                [third["experiment_id"], first["experiment_id"], second["experiment_id"]],
            )
            restarted = self._service(tmpdir)
            relisted = restarted.list_experiments("user:researcher-a", lab_id="lab:demo")

            with self.assertRaises(ExperimentValidationError):
                service.reorder_experiments(
                    "user:researcher-a",
                    [third["experiment_id"], third["experiment_id"]],
                )
            with self.assertRaises(ExperimentValidationError):
                service.reorder_experiments(
                    "user:researcher-a",
                    [third["experiment_id"], "experiment:missing"],
                )
            with self.assertRaises(ExperimentAuthorizationError):
                service.reorder_experiments(
                    "user:guest",
                    [third["experiment_id"], first["experiment_id"], second["experiment_id"]],
                )

        reordered_ids = [item["experiment_id"] for item in reordered]
        relisted_ids = [item["experiment_id"] for item in relisted]
        for ids in [reordered_ids, relisted_ids]:
            self.assertLess(ids.index(third["experiment_id"]), ids.index(first["experiment_id"]))
            self.assertLess(ids.index(first["experiment_id"]), ids.index(second["experiment_id"]))

    def test_downward_reorder_returns_and_persists_exact_requested_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            first = service.create_blank_experiment("user:researcher-a", "lab:demo", "Entry A", experiment_id="experiment:a")
            second = service.create_blank_experiment("user:researcher-a", "lab:demo", "Entry B", experiment_id="experiment:b")
            third = service.create_blank_experiment("user:researcher-a", "lab:demo", "Entry C", experiment_id="experiment:c")
            fourth = service.create_blank_experiment("user:researcher-a", "lab:demo", "Entry D", experiment_id="experiment:d")
            requested = [first["experiment_id"], third["experiment_id"], second["experiment_id"], fourth["experiment_id"]]

            returned = service.reorder_experiments("user:researcher-a", requested)
            relisted = service.list_experiments("user:researcher-a", lab_id="lab:demo")
            with sqlite3.connect(Path(tmpdir) / "researchos.db") as connection:
                positions = connection.execute(
                    """
                    SELECT experiment_id, sort_index
                    FROM experiment_workspaces
                    WHERE experiment_id IN ('experiment:a', 'experiment:b', 'experiment:c', 'experiment:d')
                    ORDER BY sort_index ASC
                    """,
                ).fetchall()

        returned_ids = [item["experiment_id"] for item in returned]
        relisted_ids = [item["experiment_id"] for item in relisted if item["experiment_id"] in requested]
        position_ids = [row[0] for row in positions]
        position_values = [row[1] for row in positions]
        self.assertEqual(returned_ids, requested)
        self.assertEqual(relisted_ids, requested)
        self.assertEqual(position_ids, requested)
        self.assertEqual(len(position_values), len(set(position_values)))

    def test_lab_owner_can_reorder_researcher_planned_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            first = service.create_blank_experiment("user:researcher-a", "lab:demo", "Planned A", status="planned")
            second = service.create_blank_experiment("user:researcher-a", "lab:demo", "Planned B", status="planned")

            reordered = service.reorder_experiments(
                "user:pi-owner",
                [second["experiment_id"], first["experiment_id"]],
            )

        reordered_ids = [item["experiment_id"] for item in reordered]
        self.assertLess(reordered_ids.index(second["experiment_id"]), reordered_ids.index(first["experiment_id"]))

    def test_lab_owner_can_delete_researcher_planned_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment("user:researcher-a", "lab:demo", "Planned delete", status="planned")

            deleted = service.delete_experiment("user:pi-owner", experiment["experiment_id"])

        self.assertTrue(deleted["deleted"])

    def test_legacy_alias_resolves_to_canonical_experiment_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            store = SQLiteStore(settings=self._settings(tmpdir))
            store.upsert_experiment(
                Experiment(
                    id="legacy-row-1",
                    source_document_id="legacy-doc",
                    source_provider="test",
                    title="Legacy Display Title",
                    experiment_id="experiment:legacy-canonical",
                )
            )
            canonical = service.resolve_experiment_id("legacy-row-1")
            deleted = service.delete_experiment("user:pi-owner", "legacy-row-1")

        self.assertEqual(canonical, "experiment:legacy-canonical")
        self.assertEqual(deleted["experiment_id"], "experiment:legacy-canonical")

    def test_legacy_experiment_migrates_to_notebook_workspace_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            store = SQLiteStore(settings=self._settings(tmpdir))
            store.upsert_experiment(
                Experiment(
                    id="legacy-row-2",
                    source_document_id="legacy-doc",
                    source_provider="test",
                    title="Legacy Notes",
                    experiment_id="NK_Expt_Legacy",
                    cell_line="retinal organoid",
                    notes="Legacy notebook observations.",
                    conclusions="Legacy conclusion.",
                )
            )
            store.register_asset(
                asset_type="image",
                experiment_id="legacy-row-2",
                title="Legacy image",
                filename="legacy.png",
                provider="local",
                path="/tmp/legacy.png",
                asset_id="asset:legacy-image",
            )

            canonical = service.resolve_experiment_id("legacy-row-2")
            workspace = service.get_workspace("legacy-row-2", "user:pi-owner")
            migrated_assets = store.list_assets(experiment_id="NK_Expt_Legacy")
            first_count = len(service.list_experiments("user:pi-owner", lab_id="lab:demo"))
            service.migrate_legacy_organoid_experiments()
            second_count = len(service.list_experiments("user:pi-owner", lab_id="lab:demo"))
            restarted = self._service(tmpdir)
            reopened = restarted.get_workspace("NK_Expt_Legacy", "user:pi-owner")

        assert workspace is not None
        assert reopened is not None
        self.assertEqual(canonical, "NK_Expt_Legacy")
        self.assertEqual(workspace["experiment"]["title"], "Legacy Notes")
        self.assertEqual(workspace["experiment"]["sample_unit_type"], "organoid")
        self.assertIn("Legacy notebook observations.", workspace["notebook"]["plain_text_cache"])
        self.assertIn("Legacy conclusion.", workspace["notebook"]["plain_text_cache"])
        self.assertEqual([asset["asset_id"] for asset in migrated_assets], ["asset:legacy-image"])
        self.assertEqual(first_count, second_count)
        self.assertEqual(reopened["notebook"]["plain_text_cache"], workspace["notebook"]["plain_text_cache"])

    def test_legacy_experiment_aliases_can_delete_and_reorder_after_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            store = SQLiteStore(settings=self._settings(tmpdir))
            for row_id, human_id, title in [
                ("legacy-row-a", "NK_Expt_A", "Legacy A"),
                ("legacy-row-b", "NK_Expt_B", "Legacy B"),
            ]:
                store.upsert_experiment(
                    Experiment(
                        id=row_id,
                        source_document_id="legacy-doc",
                        source_provider="test",
                        title=title,
                        experiment_id=human_id,
                    )
                )
            service.resolve_experiment_id("legacy-row-a")
            service.resolve_experiment_id("legacy-row-b")

            reordered = service.reorder_experiments("user:pi-owner", ["legacy-row-b", "legacy-row-a"])
            deleted = service.delete_experiment("user:pi-owner", "legacy-row-a")
            restarted = self._service(tmpdir)
            relisted = restarted.list_experiments("user:pi-owner", lab_id="lab:demo")

        reordered_ids = [item["experiment_id"] for item in reordered]
        relisted_ids = [item["experiment_id"] for item in relisted]
        self.assertLess(reordered_ids.index("NK_Expt_B"), reordered_ids.index("NK_Expt_A"))
        self.assertEqual(deleted["experiment_id"], "NK_Expt_A")
        self.assertNotIn("NK_Expt_A", relisted_ids)
        self.assertIn("NK_Expt_B", relisted_ids)

    def test_ensure_demo_data_is_idempotent_and_preserves_existing_notebook(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            notebook = service.get_or_create_notebook("user:researcher-a", "NK_Expt_26")
            saved = service.save_notebook(
                "user:researcher-a",
                notebook["document_id"],
                notebook["version"],
                "Researcher-edited demo notebook.",
                document_format="markdown",
            )

            service.ensure_demo_data()
            service.ensure_demo_data()
            restarted = self._service(tmpdir)
            reopened = restarted.get_or_create_notebook("user:researcher-a", "NK_Expt_26")
            with sqlite3.connect(Path(tmpdir) / "researchos.db") as connection:
                count = connection.execute(
                    "SELECT COUNT(*) FROM experiment_workspaces WHERE experiment_id = 'NK_Expt_26'",
                ).fetchone()[0]

        self.assertEqual(count, 1)
        self.assertIn("Researcher-edited demo notebook.", saved["plain_text_cache"])
        self.assertEqual(reopened["plain_text_cache"], saved["plain_text_cache"])

    def test_service_construction_twice_does_not_duplicate_demo_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._service(tmpdir)
            self._service(tmpdir)
            with sqlite3.connect(Path(tmpdir) / "researchos.db") as connection:
                count = connection.execute(
                    "SELECT COUNT(*) FROM experiment_workspaces WHERE experiment_id = 'NK_Expt_26'",
                ).fetchone()[0]

        self.assertEqual(count, 1)

    def test_demo_seed_repairs_existing_workspace_notebook_without_pi_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            with sqlite3.connect(Path(tmpdir) / "researchos.db") as connection:
                connection.execute(
                    "UPDATE experiment_workspaces SET owner_user_id = 'user:researcher-b' WHERE experiment_id = 'NK_Expt_26'",
                )
                connection.execute("DELETE FROM experiment_notebook_documents WHERE experiment_id = 'NK_Expt_26'")
                connection.execute(
                    "UPDATE lab_memberships SET active = 0 WHERE lab_id = 'lab:demo' AND user_id = 'user:pi-owner'",
                )

            service.ensure_demo_data()
            with sqlite3.connect(Path(tmpdir) / "researchos.db") as connection:
                notebook = connection.execute(
                    "SELECT updated_by FROM experiment_notebook_documents WHERE experiment_id = 'NK_Expt_26'",
                ).fetchone()
                workspace_count = connection.execute(
                    "SELECT COUNT(*) FROM experiment_workspaces WHERE experiment_id = 'NK_Expt_26'",
                ).fetchone()[0]

            self.assertEqual(workspace_count, 1)
            self.assertIsNotNone(notebook)
            self.assertEqual(notebook[0], "user:researcher-b")
            self.assertFalse(service.can_access("user:guest", "NK_Expt_26", "edit"))

    def test_partially_migrated_legacy_experiment_completes_missing_notebook(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            store = SQLiteStore(settings=self._settings(tmpdir))
            store.upsert_experiment(
                Experiment(
                    id="legacy-partial-row",
                    source_document_id="legacy-doc",
                    source_provider="test",
                    title="Partial Legacy",
                    experiment_id="NK_Expt_Partial",
                    notes="Partial migration notes.",
                )
            )
            with sqlite3.connect(Path(tmpdir) / "researchos.db") as connection:
                connection.execute(
                    """
                    INSERT INTO experiment_workspaces
                        (experiment_id, lab_id, owner_user_id, title, status, sample_unit_type, sort_index)
                    VALUES ('NK_Expt_Partial', 'lab:demo', 'user:pi-owner', 'Partial Legacy', 'active', 'sample', 999)
                    """
                )

            canonical = service.resolve_experiment_id("legacy-partial-row")
            workspace = service.get_workspace("NK_Expt_Partial", "user:pi-owner")
            service.migrate_legacy_organoid_experiments()
            with sqlite3.connect(Path(tmpdir) / "researchos.db") as connection:
                workspace_count = connection.execute(
                    "SELECT COUNT(*) FROM experiment_workspaces WHERE experiment_id = 'NK_Expt_Partial'",
                ).fetchone()[0]
                notebook_count = connection.execute(
                    "SELECT COUNT(*) FROM experiment_notebook_documents WHERE experiment_id = 'NK_Expt_Partial'",
                ).fetchone()[0]
                sort_index = connection.execute(
                    "SELECT sort_index FROM experiment_workspaces WHERE experiment_id = 'NK_Expt_Partial'",
                ).fetchone()[0]

        assert workspace is not None
        self.assertEqual(canonical, "NK_Expt_Partial")
        self.assertEqual(workspace_count, 1)
        self.assertEqual(notebook_count, 1)
        self.assertEqual(sort_index, 999)
        self.assertIn("Partial migration notes.", workspace["notebook"]["plain_text_cache"])

    def test_title_is_not_treated_as_experiment_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            service.create_blank_experiment("user:researcher-a", "lab:demo", "Do Not Use Title")

            resolved = service.resolve_experiment_id("Do Not Use Title")

        self.assertIsNone(resolved)

    def test_new_experiment_receives_predictable_position(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            first = service.create_blank_experiment("user:researcher-a", "lab:demo", "Entry A")
            second = service.create_blank_experiment("user:researcher-a", "lab:demo", "Entry B")

        self.assertGreater(int(second["sort_index"]), int(first["sort_index"]))

    def test_create_from_protocol_version_inherits_linked_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            protocol = service.get_protocol("protocol:meyer-retinal-organoid-protocol")
            assert protocol is not None
            experiment = service.create_from_protocol(
                "user:researcher-a",
                protocol["protocol_id"],
                protocol["current_version_id"],
                "Protocol-derived experiment",
            )
            workspace = service.get_workspace(experiment["experiment_id"], "user:researcher-a")

        assert workspace is not None
        events = workspace["timeline"]["events"]
        self.assertTrue(any(event["source"] == "protocol" for event in events))
        self.assertTrue(any(event["protocol_event_id"] for event in events))

    def test_protocol_update_does_not_alter_historical_experiment(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            protocol = service.get_protocol("protocol:meyer-retinal-organoid-protocol")
            assert protocol is not None
            old_version = protocol["current_version_id"]
            experiment = service.create_from_protocol(
                "user:researcher-a",
                protocol["protocol_id"],
                old_version,
                "Historical protocol test",
            )
            service.create_protocol_version(
                "user:pi-owner",
                protocol["protocol_id"],
                "demo-v2",
                "Updated protocol content that must not rewrite old timelines.",
                events=[{"title": "New D10 step", "day": 10, "event_type": "protocol_step"}],
            )
            workspace = service.get_workspace(experiment["experiment_id"], "user:researcher-a")

        assert workspace is not None
        refs = workspace["design"]["protocol_references"]
        self.assertEqual(refs[0]["protocol_version_id"], old_version)
        self.assertFalse(any(event["title"] == "New D10 step" for event in workspace["timeline"]["events"]))

    def test_create_cohorts_conditions_interventions_and_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment("user:researcher-a", "lab:demo", "Assay plan")
            cohort = service.add_cohort("user:researcher-a", experiment["experiment_id"], {"name": "Cohort A"})
            condition = service.add_condition(
                "user:researcher-a",
                experiment["experiment_id"],
                {"cohort_id": cohort["cohort_id"], "name": "Vehicle", "condition_type": "vehicle_control"},
            )
            intervention = service.add_intervention(
                "user:researcher-a",
                experiment["experiment_id"],
                {"condition_id": condition["condition_id"], "name": "Media change", "intervention_type": "media_change"},
            )
            event = service.add_event(
                "user:researcher-a",
                experiment["experiment_id"],
                {"title": "Readout D35", "event_type": "assay", "day": 35},
            )

        self.assertEqual(cohort["name"], "Cohort A")
        self.assertEqual(condition["condition_type"], "vehicle_control")
        self.assertEqual(intervention["intervention_type"], "media_change")
        self.assertEqual(event["day"], 35)

    def test_unauthorized_user_cannot_view_experiment(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment("user:researcher-a", "lab:demo", "Private experiment")
            workspace = service.get_workspace(experiment["experiment_id"], "user:guest")

        self.assertIsNone(workspace)

    def test_viewer_cannot_edit_notebook_and_editor_can(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment("user:researcher-a", "lab:demo", "Notebook permissions")
            service.grant_access("user:researcher-a", experiment["experiment_id"], "user", "user:researcher-b", "view")
            notebook = service.get_or_create_notebook("user:researcher-a", experiment["experiment_id"])
            with self.assertRaises(ExperimentAuthorizationError):
                service.save_notebook("user:researcher-b", notebook["document_id"], notebook["version"], "viewer edit")
            service.grant_access("user:researcher-a", experiment["experiment_id"], "user", "user:researcher-b", "edit")
            updated = service.save_notebook("user:researcher-b", notebook["document_id"], notebook["version"], "editor edit")

        self.assertEqual(updated["version"], notebook["version"] + 1)

    def test_stale_notebook_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment("user:researcher-a", "lab:demo", "Conflict test")
            notebook = service.get_or_create_notebook("user:researcher-a", experiment["experiment_id"])
            service.save_notebook("user:researcher-a", notebook["document_id"], notebook["version"], "first save")
            with self.assertRaises(ExperimentConflictError):
                service.save_notebook("user:researcher-a", notebook["document_id"], notebook["version"], "stale save")

    def test_rich_notebook_save_retrieve_and_plain_text_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment("user:researcher-a", "lab:demo", "Rich notebook")
            notebook = service.get_or_create_notebook("user:researcher-a", experiment["experiment_id"])
            delta = json.dumps([
                {"insert": "Retinal differentiation notes"},
                {"insert": "\n", "attributes": {"header": 1}},
                {"insert": "SAG increased BRN3B in this draft note."},
                {"insert": "\n"},
            ])
            updated = service.save_notebook(
                "user:researcher-a",
                notebook["document_id"],
                notebook["version"],
                delta,
                document_format="rich_text_delta_json",
            )
            reopened = self._service(tmpdir).get_or_create_notebook("user:researcher-a", experiment["experiment_id"])

        self.assertEqual(updated["document_format"], "rich_text_delta_json")
        self.assertIn("BRN3B", updated["plain_text_cache"])
        self.assertEqual(json.loads(reopened["content"]), json.loads(delta))
        self.assertEqual(reopened["document_version"], updated["version"])

    def test_markdown_notebook_exposes_idempotent_structured_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment("user:researcher-a", "lab:demo", "Markdown migration")
            notebook = service.get_or_create_notebook("user:researcher-a", experiment["experiment_id"])
            legacy = "# Legacy heading\n\nExisting line one.\nExisting line two."
            with sqlite3.connect(Path(tmpdir) / "researchos.db") as connection:
                connection.execute(
                    """
                    UPDATE experiment_notebook_documents
                    SET document_format = 'markdown',
                        content = ?,
                        structured_content = NULL,
                        plain_text_cache = ?,
                        original_format = 'markdown',
                        original_content = ?,
                        migration_version = 1
                    WHERE document_id = ?
                    """,
                    (legacy, legacy, legacy, notebook["document_id"]),
                )
            first = service.get_or_create_notebook("user:researcher-a", experiment["experiment_id"])
            second = service.get_or_create_notebook("user:researcher-a", experiment["experiment_id"])

        self.assertEqual(json.loads(first["content"])[0]["insert"], "Legacy heading")
        self.assertIn("Existing line one.", first["plain_text_cache"])
        self.assertEqual(first["structured_content"], second["structured_content"])
        self.assertTrue(first["migration"]["idempotent"])
        self.assertTrue(first["migration"]["original_source_preserved"])

    def test_visible_delta_json_legacy_notebook_is_repaired(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment("user:researcher-a", "lab:demo", "Visible JSON repair")
            notebook = service.get_or_create_notebook("user:researcher-a", experiment["experiment_id"])
            visible_json = json.dumps([{"insert": "Recovered Delta note\n"}])
            with sqlite3.connect(Path(tmpdir) / "researchos.db") as connection:
                connection.execute(
                    """
                    UPDATE experiment_notebook_documents
                    SET document_format = 'markdown',
                        content = ?,
                        structured_content = NULL,
                        plain_text_cache = ?,
                        original_format = 'markdown',
                        original_content = ?,
                        migration_version = 1
                    WHERE document_id = ?
                    """,
                    (visible_json, visible_json, visible_json, notebook["document_id"]),
                )
            repaired = service.get_or_create_notebook("user:researcher-a", experiment["experiment_id"])

        self.assertIn("Recovered Delta note", repaired["plain_text_cache"])
        self.assertNotIn('[{"insert"', repaired["plain_text_cache"])
        self.assertEqual(json.loads(repaired["structured_content"])[0]["insert"], "Recovered Delta note\n")

    def test_double_encoded_delta_notebook_is_repaired(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment("user:researcher-a", "lab:demo", "Double JSON repair")
            notebook = service.get_or_create_notebook("user:researcher-a", experiment["experiment_id"])
            double_encoded = json.dumps(json.dumps([{"insert": "Double encoded note\n"}]))
            updated = service.save_notebook(
                "user:researcher-a",
                notebook["document_id"],
                notebook["version"],
                double_encoded,
                document_format="rich_text_delta_json",
            )

        self.assertIn("Double encoded note", updated["plain_text_cache"])
        self.assertEqual(json.loads(updated["content"])[0]["insert"], "Double encoded note\n")

    def test_corrupted_delta_prefix_preserves_later_user_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment("user:researcher-a", "lab:demo", "Mixed JSON repair")
            notebook = service.get_or_create_notebook("user:researcher-a", experiment["experiment_id"])
            mixed = '[{"insert":"Recovered note\\n"}]\nTyped beneath broken JSON'
            updated = service.save_notebook(
                "user:researcher-a",
                notebook["document_id"],
                notebook["version"],
                mixed,
                document_format="rich_text_delta_json",
            )

        self.assertIn("Recovered note", updated["plain_text_cache"])
        self.assertIn("Typed beneath broken JSON", updated["plain_text_cache"])
        self.assertNotIn('[{"insert"', updated["plain_text_cache"])

    def test_nested_delta_inside_text_insert_is_repaired(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment("user:researcher-a", "lab:demo", "Nested Delta repair")
            notebook = service.get_or_create_notebook("user:researcher-a", experiment["experiment_id"])
            nested = json.dumps([
                {
                    "insert": json.dumps([
                        {"insert": "Hello\n"},
                        {"insert": "World\n"},
                    ])
                },
                {"insert": "\n"},
            ])
            updated = service.save_notebook(
                "user:researcher-a",
                notebook["document_id"],
                notebook["version"],
                nested,
                document_format="rich_text_delta_json",
            )

        ops = json.loads(updated["content"])
        self.assertEqual(ops[0]["insert"], "Hello\n")
        self.assertEqual(ops[1]["insert"], "World\n")
        self.assertNotIn('[{"insert"', updated["plain_text_cache"])

    def test_payload_repairs_corrupted_existing_structured_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment("user:researcher-a", "lab:demo", "Payload repair")
            notebook = service.get_or_create_notebook("user:researcher-a", experiment["experiment_id"])
            nested = json.dumps([
                {"insert": json.dumps([{"insert": "Recovered from stored structured content\n"}])},
                {"insert": "\n"},
            ])
            with sqlite3.connect(Path(tmpdir) / "researchos.db") as connection:
                connection.execute(
                    """
                    UPDATE experiment_notebook_documents
                    SET document_format = 'rich_text_delta_json',
                        content = ?,
                        structured_content = ?,
                        plain_text_cache = ?
                    WHERE document_id = ?
                    """,
                    (nested, nested, nested, notebook["document_id"]),
                )
            repaired = service.get_or_create_notebook("user:researcher-a", experiment["experiment_id"])
            with sqlite3.connect(Path(tmpdir) / "researchos.db") as connection:
                stored = connection.execute(
                    "SELECT content, structured_content, plain_text_cache FROM experiment_notebook_documents WHERE document_id = ?",
                    (notebook["document_id"],),
                ).fetchone()

        self.assertEqual(json.loads(repaired["structured_content"])[0]["insert"], "Recovered from stored structured content\n")
        self.assertNotIn('[{"insert"', repaired["plain_text_cache"])
        assert stored is not None
        self.assertEqual(json.loads(stored[0])[0]["insert"], "Recovered from stored structured content\n")
        self.assertEqual(stored[0], stored[1])
        self.assertNotIn('[{"insert"', stored[2])

    def test_nested_delta_preserves_later_text_and_embed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment("user:researcher-a", "lab:demo", "Nested Delta embed")
            notebook = service.get_or_create_notebook("user:researcher-a", experiment["experiment_id"])
            nested = json.dumps([
                {"insert": json.dumps([{"insert": "Recovered text\n"}])},
                {"insert": "Later prose\n"},
                {
                    "insert": {
                        "custom": json.dumps(
                            {
                                "experiment_attachment": json.dumps(
                                    {
                                        "embed_type": "experiment_attachment",
                                        "attachment_type": "image",
                                        "attachment_id": "attachment:test",
                                        "display_name": "Recovered image",
                                    }
                                )
                            }
                        )
                    }
                },
                {"insert": "\n"},
            ])
            updated = service.save_notebook(
                "user:researcher-a",
                notebook["document_id"],
                notebook["version"],
                nested,
                document_format="rich_text_delta_json",
            )

        self.assertIn("Recovered text", updated["plain_text_cache"])
        self.assertIn("Later prose", updated["plain_text_cache"])
        self.assertIn("attachment:test", updated["content"])
        self.assertNotIn('[{"insert"', updated["plain_text_cache"])

    def test_arbitrary_json_text_is_not_unwrapped_as_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment("user:researcher-a", "lab:demo", "JSON prose")
            notebook = service.get_or_create_notebook("user:researcher-a", experiment["experiment_id"])
            prose = '{"not":"a delta document"}'
            updated = service.save_notebook(
                "user:researcher-a",
                notebook["document_id"],
                notebook["version"],
                prose,
                document_format="rich_text_delta_json",
            )

        self.assertIn(prose, updated["plain_text_cache"])

    def test_canonical_delta_normalization_cases_are_idempotent(self) -> None:
        direct = [{"insert": "Direct\n"}]
        wrapped = json.dumps({"ops": [{"insert": "Wrapped\n"}]})
        double_encoded = json.dumps(json.dumps([{"insert": "Double\n"}]))
        nested_insert = json.dumps([{"insert": json.dumps([{"insert": "Nested\n"}])}, {"insert": "\n"}])
        arbitrary_json = '{"not":"delta"}'

        self.assertEqual(json.loads(canonical_notebook_delta_json(direct))[0]["insert"], "Direct\n")
        self.assertEqual(json.loads(canonical_notebook_delta_json(wrapped))[0]["insert"], "Wrapped\n")
        self.assertEqual(json.loads(canonical_notebook_delta_json(double_encoded))[0]["insert"], "Double\n")
        self.assertEqual(json.loads(canonical_notebook_delta_json(nested_insert))[0]["insert"], "Nested\n")
        self.assertEqual(json.loads(canonical_notebook_delta_json(arbitrary_json))[0]["insert"], arbitrary_json)
        once = canonical_notebook_delta_json(nested_insert)
        twice = canonical_notebook_delta_json(once)
        self.assertEqual(once, twice)
        self.assertEqual(canonical_notebook_delta_json(""), CANONICAL_BLANK_DELTA_JSON)

    def test_notebook_delta_repair_dry_run_and_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment("user:researcher-a", "lab:demo", "Repair command")
            notebook = service.get_or_create_notebook("user:researcher-a", experiment["experiment_id"])
            nested = json.dumps([
                {"insert": json.dumps([{"insert": "Repair me\n"}])},
                {"insert": "\n"},
            ])
            with sqlite3.connect(Path(tmpdir) / "researchos.db") as connection:
                connection.execute(
                    """
                    UPDATE experiment_notebook_documents
                    SET document_format = 'rich_text_delta_json',
                        content = ?,
                        structured_content = ?,
                        plain_text_cache = ?
                    WHERE document_id = ?
                    """,
                    (nested, nested, nested, notebook["document_id"]),
                )

            dry_run = service.repair_notebook_delta_records(dry_run=True)
            self.assertEqual(dry_run["records_needing_repair"], [notebook["document_id"]])
            self.assertEqual(dry_run["repaired_count"], 0)
            self.assertIsNone(dry_run["backup_path"])

            applied = service.repair_notebook_delta_records(dry_run=False)
            self.assertEqual(applied["repaired_count"], 1)
            self.assertTrue(Path(str(applied["backup_path"])).exists())
            second = service.repair_notebook_delta_records(dry_run=True)
            self.assertEqual(second["records_needing_repair"], [])

    def test_malformed_rich_notebook_generates_safe_plain_text_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment("user:researcher-a", "lab:demo", "Malformed rich")
            notebook = service.get_or_create_notebook("user:researcher-a", experiment["experiment_id"])
            updated = service.save_notebook(
                "user:researcher-a",
                notebook["document_id"],
                notebook["version"],
                "{not valid delta json",
                document_format="rich_text_delta_json",
            )

        self.assertIn("not valid delta json", updated["plain_text_cache"])

    def test_rich_notebook_context_enumerates_embeds(self) -> None:
        delta = json.dumps([
            {"insert": "Notes before embed\n"},
            {"insert": {
                "embed_type": "research_object",
                "object_type": "protocol",
                "object_id": "protocol:test",
                "display_label": "Protocol Test",
            }},
            {"insert": "\n"},
            {"insert": {
                "embed_type": "attachment",
                "attachment_id": "attachment:test",
                "display_label": "results.xlsx",
            }},
            {"insert": "\n"},
        ])
        document = {"document_format": "rich_text_delta_json", "content": delta, "schema_version": 1}
        context = RichNotebookContextService()

        self.assertIn("Protocol Test", context.extract_plain_text(document))
        self.assertEqual(context.enumerate_references(document)[0]["object_id"], "protocol:test")
        self.assertEqual(context.enumerate_attachments(document)[0]["attachment_id"], "attachment:test")

    def test_attachment_enforces_underlying_resource_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment("user:researcher-a", "lab:demo", "Attachment test")
            service.grant_access("user:researcher-a", experiment["experiment_id"], "user", "user:researcher-b", "edit")
            notebook = service.get_or_create_notebook("user:researcher-a", experiment["experiment_id"])
            with self.assertRaises(ExperimentAuthorizationError):
                service.add_notebook_attachment(
                    "user:researcher-b",
                    notebook["document_id"],
                    {"attachment_type": "notebook", "resource_id": "notebook:researcher-a", "display_name": "A private notebook"},
                )

    def test_link_attachment_validates_and_persists_separately_from_notebook_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            experiment = service.create_blank_experiment("user:researcher-a", "lab:demo", "Link attachment test")
            with self.assertRaises(ValueError):
                service.create_link_attachment(
                    "user:researcher-a",
                    experiment["experiment_id"],
                    {"external_url": "not-a-url"},
                )
            attachment = service.create_link_attachment(
                "user:researcher-a",
                experiment["experiment_id"],
                {
                    "external_url": "https://docs.google.com/spreadsheets/d/example",
                    "display_name": "Google SAG sheet",
                    "description": "External analysis workbook",
                },
            )
            workspace = service.get_workspace(experiment["experiment_id"], "user:researcher-a")

        assert workspace is not None
        self.assertEqual(attachment["source_type"], "external_link")
        self.assertEqual(attachment["attachment_type"], "google_sheet")
        self.assertIn("Google SAG sheet", [item["display_name"] for item in workspace["attachments"]])
        self.assertNotIn("docs.google.com", workspace["notebook"]["content"])

    def test_uploaded_attachment_metadata_persists_and_delete_marks_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            service = GeneralExperimentService(settings=settings)
            experiment = service.create_blank_experiment("user:researcher-a", "lab:demo", "Upload attachment test")
            stored = LocalAttachmentStorage(settings).save(
                experiment_id=experiment["experiment_id"],
                filename="results.csv",
                data=b"group,value\ncontrol,1\n",
                mime_type="text/csv",
            )
            attachment = service.record_uploaded_attachment(
                "user:researcher-a",
                experiment["experiment_id"],
                stored.__dict__,
            )
            listed = service.list_attachments("user:researcher-a", experiment["experiment_id"])
            deleted = service.delete_attachment("user:researcher-a", attachment["attachment_id"])
            after_delete = service.list_attachments("user:researcher-a", experiment["experiment_id"])

        self.assertEqual(attachment["source_type"], "uploaded_file")
        self.assertEqual(attachment["attachment_type"], "spreadsheet")
        self.assertEqual(attachment["processing_status"], "metadata_pending")
        self.assertTrue(any(item["attachment_id"] == attachment["attachment_id"] for item in listed))
        self.assertTrue(deleted["deleted"])
        self.assertFalse(any(item["attachment_id"] == attachment["attachment_id"] for item in after_delete))

    def test_pasted_image_attachment_and_document_reference_persist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            service = GeneralExperimentService(settings=settings)
            experiment = service.create_blank_experiment("user:researcher-a", "lab:demo", "Paste image")
            notebook = service.get_or_create_notebook("user:researcher-a", experiment["experiment_id"])
            stored = LocalAttachmentStorage(settings).save(
                experiment_id=experiment["experiment_id"],
                filename="clipboard-image.png",
                data=b"\x89PNG\r\n\x1a\npasted",
                mime_type="image/png",
            )
            attachment = service.record_uploaded_attachment(
                "user:researcher-a",
                experiment["experiment_id"],
                stored.__dict__,
                display_name="OneNote paste",
                attachment_type="image",
            )
            delta = json.dumps([
                {
                    "insert": {
                        "custom": json.dumps(
                            {
                                "experiment_attachment": json.dumps(
                                    {
                                        "embed_type": "experiment_attachment",
                                        "attachment_type": "image",
                                        "attachment_id": attachment["attachment_id"],
                                        "display_name": "OneNote paste",
                                        "alt_text": None,
                                    }
                                )
                            }
                        )
                    }
                },
                {"insert": "\n"},
            ])
            service.save_notebook(
                "user:researcher-a",
                notebook["document_id"],
                notebook["version"],
                delta,
                document_format="rich_text_delta_json",
            )
            reopened = self._service(tmpdir).get_or_create_notebook("user:researcher-a", experiment["experiment_id"])

        self.assertEqual(attachment["attachment_type"], "image")
        self.assertEqual(attachment["mime_type"], "image/png")
        self.assertIn(attachment["attachment_id"], reopened["content"])

    def test_pasted_image_storage_validation_and_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            service = GeneralExperimentService(settings=settings)
            experiment = service.create_blank_experiment("user:researcher-a", "lab:demo", "Paste image validation")
            storage = LocalAttachmentStorage(settings)
            with self.assertRaises(AttachmentStorageError):
                storage.save(
                    experiment_id=experiment["experiment_id"],
                    filename="clipboard-image.bmp",
                    data=b"not supported",
                    mime_type="image/bmp",
                )
            with self.assertRaises(AttachmentStorageError):
                storage.save(
                    experiment_id=experiment["experiment_id"],
                    filename="too-large.png",
                    data=b"0" * (51 * 1024 * 1024),
                    mime_type="image/png",
                )
            stored = storage.save(
                experiment_id=experiment["experiment_id"],
                filename="clipboard-image.jpg",
                data=b"\xff\xd8\xffpasted",
                mime_type="image/jpeg",
            )
            with self.assertRaises(ExperimentAuthorizationError):
                service.record_uploaded_attachment(
                    "user:guest",
                    experiment["experiment_id"],
                    stored.__dict__,
                    attachment_type="image",
                )

    def test_legacy_organoid_experiment_migrates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            with sqlite3.connect(store.path) as connection:
                connection.execute(
                    """
                    INSERT INTO experiments
                        (id, source_document_id, source_provider, title, experiment_id, notes)
                    VALUES ('experiment:legacy', 'doc:legacy', 'markdown', 'Legacy organoid experiment', 'LEGACY-ORG', 'retinal organoid notes')
                    """
                )
            service = GeneralExperimentService(settings=settings)
            workspace = service.get_workspace("LEGACY-ORG", "user:pi-owner")

        assert workspace is not None
        self.assertEqual(workspace["experiment"]["biological_system"], "retinal organoid")
        self.assertEqual(workspace["experiment"]["sample_unit_type"], "organoid")

    def test_extraction_draft_is_deterministic_and_requires_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            draft = service.create_extraction_draft(
                "user:researcher-a",
                {"source_text": "Untreated and DMSO controls with imaging on D35", "source_type": "typed_text"},
            )

        self.assertEqual(draft["status"], "awaiting_confirmation")
        self.assertTrue(draft["warnings"])

    def test_sample_planning_preview_does_not_invent_missing_counts(self) -> None:
        preview = SamplePlanningService().preview({"biological_replicates": 3})
        complete = SamplePlanningService().preview(
            {
                "biological_replicates": 3,
                "technical_replicates": 2,
                "sample_units_per_replicate": 4,
                "expected_attrition_percent": 10,
            }
        )

        self.assertEqual(preview["status"], "incomplete")
        self.assertEqual(complete["status"], "preview")
        self.assertEqual(complete["calculation_preview"]["base_units"], 24)


if __name__ == "__main__":
    unittest.main()
