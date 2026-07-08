"""Tests for experiment lifecycle rules, storage, timelines, and workspace output."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.dashboard_service import DashboardService
from app.experiment_lifecycle import recommended_actions_for_experiment, validate_transition
from app.experiment_workspace import build_experiment_workspace
from app.experiments import Experiment
from app.main import _experiment_timeline, _lifecycle_payload
from app.research_document import DocumentChunk, ResearchDocument
from app.storage import SQLiteStore
from app.workflow_engine import WorkflowEngine


class ExperimentLifecycleTests(unittest.TestCase):
    """Lifecycle state should be deterministic and provenance-visible."""

    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def _seed_experiment(self, store: SQLiteStore) -> dict[str, object]:
        document = ResearchDocument(
            id="doc:lifecycle",
            provider="markdown",
            source_id="lifecycle.md",
            title="Lifecycle note",
            content="NK_Expt_31 lifecycle note with SAG and SIX6.",
            metadata={"entities": {"compound": ["SAG"], "marker": ["SIX6"]}},
        )
        store.upsert_document(
            document,
            [DocumentChunk(id="chunk:lifecycle", document_id=document.id, chunk_index=0, text=document.content, token_estimate=8)],
        )
        experiment = Experiment(
            id="experiment:lifecycle",
            source_document_id=document.id,
            source_provider="markdown",
            title="Lifecycle SAG experiment",
            experiment_id="NK_Expt_31",
            compounds=["SAG"],
            markers=["SIX6"],
        )
        store.upsert_experiment(experiment)
        stored = store.get_experiment(experiment.id)
        assert stored is not None
        return stored

    def test_valid_and_invalid_transitions(self) -> None:
        self.assertEqual(validate_transition("Planning", "Approved"), ("Planning", "Approved"))
        with self.assertRaises(ValueError):
            validate_transition("Planning", "Published")

    def test_storage_initializes_and_records_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(settings=self._settings(tmpdir))
            experiment = self._seed_experiment(store)

            initial = store.get_experiment_lifecycle(str(experiment["id"]))
            updated = store.transition_experiment_lifecycle(str(experiment["id"]), "Approved", reason="Plan reviewed.", actor="PI")

        self.assertEqual(initial["current_stage"], "Planning")
        self.assertEqual(updated["current_stage"], "Approved")
        self.assertGreaterEqual(len(updated["history"]), 2)
        self.assertEqual(updated["history"][-1]["reason"], "Plan reviewed.")

    def test_lifecycle_payload_and_recommendations_use_linked_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(settings=self._settings(tmpdir))
            experiment = self._seed_experiment(store)
            engine = WorkflowEngine(store)
            workflow = engine.workflow_for_experiment(experiment)
            engine.transition(str(workflow["workflow_id"]), "Approved")
            engine.transition(str(workflow["workflow_id"]), "Running")
            engine.transition(str(workflow["workflow_id"]), "Treatment")
            engine.transition(str(workflow["workflow_id"]), "Waiting")
            engine.transition(str(workflow["workflow_id"]), "Imaging")
            engine.transition(str(workflow["workflow_id"]), "Quantification")
            engine.transition(str(workflow["workflow_id"]), "Statistics")
            payload = _lifecycle_payload(store, experiment)
            actions_without_stats = recommended_actions_for_experiment("Analysis", experiment, [])

        self.assertEqual(payload["current_stage"], "Statistics")
        self.assertIn("Interpretation", payload["allowed_transitions"])
        self.assertIn("Complete statistics before making final claims.", actions_without_stats)
        self.assertIn("Complete statistics before making final claims.", payload["recommended_next_actions"])

    def test_timeline_contains_lifecycle_transition_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(settings=self._settings(tmpdir))
            experiment = self._seed_experiment(store)
            workflow = WorkflowEngine(store).workflow_for_experiment(experiment)
            WorkflowEngine(store).transition(str(workflow["workflow_id"]), "Approved", reason="Reviewed.")
            timeline = _experiment_timeline(store, experiment)

        event_types = [event["event_type"] for event in timeline["events"]]
        descriptions = " ".join(str(event["description"]) for event in timeline["events"])
        self.assertIn("workflow_transition", event_types)
        self.assertIn("Planning to Approved", descriptions)

    def test_workspace_includes_lifecycle_state_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            experiment = self._seed_experiment(store)
            workflow = WorkflowEngine(store).workflow_for_experiment(experiment)
            WorkflowEngine(store).transition(str(workflow["workflow_id"]), "Approved")
            timeline = _experiment_timeline(store, experiment)
            workspace = build_experiment_workspace("NK_Expt_31", timeline, settings=settings, use_ai=False)

        self.assertIsNotNone(workspace)
        assert workspace is not None
        self.assertEqual(workspace["workflow"]["current_stage"], "Approved")
        self.assertIn("Running", workspace["workflow"]["stage"]["allowed_transitions"])
        self.assertTrue(workspace["workflow"]["history"])
        self.assertEqual(workspace["notebook_entries"][0]["workflow_stage"], "Approved")

    def test_dashboard_groups_experiments_by_lifecycle_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            experiment = self._seed_experiment(store)
            workflow = WorkflowEngine(store).workflow_for_experiment(experiment)
            WorkflowEngine(store).transition(str(workflow["workflow_id"]), "Approved")
            dashboard = DashboardService(settings=settings, store=store).build(use_ai=False)

        sections = {section["id"]: section for section in dashboard["sections"]}
        workflow_text = " ".join(item["title"] for item in sections["workflow_stages"]["items"])
        self.assertIn("Approved", workflow_text)


if __name__ == "__main__":
    unittest.main()
