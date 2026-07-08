"""Tests for the generic ResearchOS Workflow Engine."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.dashboard_service import DashboardService
from app.events.event_bus import EventBus
from app.events.event_models import EventType, ResearchOSEvent
from app.experiment_workspace import build_experiment_workspace
from app.experiments import Experiment
from app.main import _experiment_timeline
from app.research_copilot import ResearchCopilotService
from app.research_document import DocumentChunk, ResearchDocument
from app.storage import SQLiteStore
from app.workflow_engine import WorkflowEngine, experiment_workflow_id


class WorkflowEngineTests(unittest.TestCase):
    """Workflow state should orchestrate experiments without provider coupling."""

    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def _seed(self, store: SQLiteStore) -> dict[str, object]:
        document = ResearchDocument(
            id="doc:workflow",
            provider="markdown",
            source_id="workflow.md",
            title="Workflow note",
            content="NK_Expt_31 used SAG and SIX6 imaging.",
            metadata={"entities": {"compound": ["SAG"], "marker": ["SIX6"]}},
        )
        store.upsert_document(
            document,
            [DocumentChunk(id="chunk:workflow", document_id=document.id, chunk_index=0, text=document.content, token_estimate=8)],
        )
        experiment = Experiment(
            id="experiment:workflow",
            source_document_id=document.id,
            source_provider="markdown",
            title="Workflow SAG experiment",
            experiment_id="NK_Expt_31",
            compounds=["SAG"],
            markers=["SIX6"],
        )
        store.upsert_experiment(experiment)
        stored = store.get_experiment(experiment.id)
        assert stored is not None
        return stored

    def test_workflow_creation_and_valid_transition(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(settings=self._settings(tmpdir))
            experiment = self._seed(store)
            engine = WorkflowEngine(store)
            workflow = engine.workflow_for_experiment(experiment)
            transitioned = engine.transition(str(workflow["workflow_id"]), "Approved", actor="PI")

        self.assertEqual(workflow["current_stage"], "Planning")
        self.assertEqual(transitioned["current_stage"], "Approved")
        self.assertEqual(transitioned["workflow_type"], "experiment")
        self.assertTrue(transitioned["history"])

    def test_invalid_transition_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(settings=self._settings(tmpdir))
            experiment = self._seed(store)
            workflow = WorkflowEngine(store).workflow_for_experiment(experiment)

            with self.assertRaises(ValueError):
                WorkflowEngine(store).transition(str(workflow["workflow_id"]), "Published")

    def test_workflow_note_and_timeline_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(settings=self._settings(tmpdir))
            experiment = self._seed(store)
            engine = WorkflowEngine(store)
            workflow = engine.workflow_for_experiment(experiment)
            engine.add_note(str(workflow["workflow_id"]), "Planning note.", actor="Nathan")
            engine.transition(str(workflow["workflow_id"]), "Approved", reason="Reviewed.")
            timeline = _experiment_timeline(store, experiment)
            note_count = len(store.workflow_notes(str(workflow["workflow_id"])))

        self.assertEqual(note_count, 1)
        self.assertTrue(any(event["event_type"] == "workflow_transition" for event in timeline["events"]))

    def test_dashboard_and_workspace_use_workflow_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            experiment = self._seed(store)
            workflow = WorkflowEngine(store).workflow_for_experiment(experiment)
            WorkflowEngine(store).transition(str(workflow["workflow_id"]), "Approved")
            dashboard = DashboardService(settings=settings, store=store).build(use_ai=False)
            workspace = build_experiment_workspace("NK_Expt_31", {"experiment_id": experiment["id"], "title": "Timeline", "events": []}, settings=settings, use_ai=False)

        sections = {section["id"]: section for section in dashboard["sections"]}
        self.assertIn("Approved", " ".join(item["title"] for item in sections["workflow_stages"]["items"]))
        self.assertIsNotNone(workspace)
        assert workspace is not None
        self.assertEqual(workspace["workflow"]["current_stage"], "Approved")

    def test_event_bus_receives_workflow_transition_event(self) -> None:
        bus = EventBus()
        seen: list[str] = []
        bus.subscribe(EventType.WORKFLOW_TRANSITIONED, lambda event: seen.append(event.event_type.value))
        bus.publish(ResearchOSEvent(event_type=EventType.WORKFLOW_TRANSITIONED, source="test", payload={"workflow_id": "workflow:test"}))

        self.assertEqual(seen, ["WorkflowTransitioned"])

    def test_copilot_uses_workflow_blocking_issues(self) -> None:
        workflow_id = experiment_workflow_id("experiment:workflow")
        workspace = {
            "experiment": {"id": "experiment:workflow", "experiment_id": "NK_Expt_31", "title": "Workflow SAG"},
            "workflow": {
                "workflow_id": workflow_id,
                "current_stage": "Statistics",
                "recommended_next_actions": ["Run GraphPad/statistics interpretation."],
                "blocking_issues": ["No parsed statistics are linked."],
                "history": [{"to_stage": "Statistics"}],
            },
            "microscopy": [{"asset_id": "asset:image"}],
            "graphpad": [],
            "statistics": [],
            "literature": [],
            "provenance": [{"fact": "workflow", "source": "workflow_engine", "provider": "ResearchOS"}],
        }

        copilot = ResearchCopilotService(settings=Settings(ai_provider="none")).build(workspace, use_ai=False)
        concerns = " ".join(item["text"] for item in copilot["sections"]["potential_concerns"])
        suggestions = " ".join(item["text"] for item in copilot["sections"]["suggested_follow_up_experiments"])

        self.assertIn("No parsed statistics", concerns)
        self.assertIn("Run GraphPad analysis", suggestions)


if __name__ == "__main__":
    unittest.main()
