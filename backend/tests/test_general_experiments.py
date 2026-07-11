"""Tests for the generalized experiment workspace foundation."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.general_experiments import (
    ExperimentAuthorizationError,
    ExperimentConflictError,
    GeneralExperimentService,
    SamplePlanningService,
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
