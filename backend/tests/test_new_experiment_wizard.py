"""Tests for the New Experiment Wizard."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from app import main
from app.config import Settings
from app.experiment_workspace import build_experiment_workspace
from app.storage import SQLiteStore


class NewExperimentWizardTests(unittest.TestCase):
    """Wizard creation should produce standard ResearchOS objects."""

    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def _request(self, experiment_id: str = "WIZARD-81") -> main.NewExperimentWizardRequest:
        return main.NewExperimentWizardRequest(
            title="Early SAG plus GRKi rescue",
            experiment_id=experiment_id,
            project="Retinal organoids",
            researcher="Nathan",
            protocol_mode="create_new",
            protocol_title="SAG rescue planning protocol",
            cell_line="SIX6 reporter iPSC",
            organoid_batch="Batch D32",
            compounds=["SAG", "GRKi"],
            concentrations=["100 nM", "250 nM"],
            timepoints=["D1", "D32"],
            replicates="n=3 biological replicates",
            controls=["DMSO"],
            readouts=["microscopy", "quantification"],
            markers=["SIX6", "BRN3B"],
            microscopy=True,
            graphpad=True,
            milestones=[
                main.WizardMilestoneRequest(label="Treatment", detail="Apply SAG plus GRKi."),
                main.WizardMilestoneRequest(label="Imaging", detail="Image SIX6 and BRN3B."),
            ],
            create_notebook_draft=True,
            start_session=True,
        )

    def test_mobile_wizard_creates_experiment_workflow_draft_session_and_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_settings = main.settings
            main.settings = self._settings(tmpdir)
            try:
                response = main.mobile_create_experiment(self._request())
                store = SQLiteStore(settings=main.settings)
                experiment = store.find_experiment_by_reference("WIZARD-81")
                assert experiment is not None
                timeline = main._experiment_timeline(store, experiment)
                workspace = build_experiment_workspace(
                    "WIZARD-81",
                    timeline,
                    settings=main.settings,
                    use_ai=False,
                )
                sessions = store.list_sessions()
                entries = store.list_pending_entries()
            finally:
                main.settings = original_settings

        self.assertEqual(response["experiment"]["human_experiment_id"], "WIZARD-81")
        self.assertEqual(response["workflow"]["current_stage"], "Planning")
        self.assertIsNotNone(response["pending_entry"])
        self.assertIsNotNone(response["session"])
        self.assertFalse(response["onenote"]["save_to_onenote_enabled"])
        self.assertTrue(any(event["event_type"] == "workflow_transition" for event in timeline["events"]))
        self.assertIsNotNone(workspace)
        assert workspace is not None
        self.assertEqual(workspace["experiment"]["experiment_id"], "WIZARD-81")
        self.assertEqual(len(entries), 1)
        self.assertEqual(len(sessions), 1)

    def test_wizard_rejects_duplicate_human_experiment_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_settings = main.settings
            main.settings = self._settings(tmpdir)
            try:
                main.mobile_create_experiment(self._request("WIZARD-DUP"))
                with self.assertRaises(HTTPException) as context:
                    main.mobile_create_experiment(self._request("WIZARD-DUP"))
            finally:
                main.settings = original_settings

        self.assertEqual(context.exception.status_code, 409)

    def test_wizard_validates_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_settings = main.settings
            main.settings = self._settings(tmpdir)
            try:
                with self.assertRaises(HTTPException) as context:
                    main.mobile_create_experiment(
                        main.NewExperimentWizardRequest(
                            title="",
                            experiment_id="",
                            controls=["DMSO"],
                            readouts=["microscopy"],
                        )
                    )
            finally:
                main.settings = original_settings

        self.assertEqual(context.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
