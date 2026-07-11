"""Tests for Experiment Design Copilot Phase 1."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.experiment_design_copilot import DEMO_NARRATIVE, ExperimentDesignCopilot


class ExperimentDesignCopilotTests(unittest.TestCase):
    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def test_demo_narrative_extraction_with_evidence_and_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ExperimentDesignCopilot(settings=self._settings(tmpdir))
            draft = service.create_draft("user:researcher-a", DEMO_NARRATIVE)

        payload = draft["draft"]
        self.assertEqual(payload["biological_system"], "retinal organoid")
        self.assertEqual(payload["sample_unit"], "organoid")
        self.assertTrue(payload["protocol"])
        self.assertIn("Meyer", payload["protocol"]["title"])
        self.assertTrue(any(c["name"].startswith("Early") for c in payload["cohorts"]))
        self.assertTrue(any(c["name"].startswith("Late") for c in payload["cohorts"]))
        self.assertTrue(any(c["name"] == "SAG 300 nM + GRKi 10 nM" for c in payload["conditions"]))
        self.assertTrue(any(i["name"] == "SAG" and i["concentration_value"] == 300.0 for i in payload["interventions"]))
        self.assertTrue(any(i["name"] == "GRKi" and i["concentration_value"] == 10.0 for i in payload["interventions"]))
        self.assertTrue(any(e["event_type"] == "imaging" and e["day"] == 35 for e in payload["events"]))
        self.assertEqual(payload["expected_duration"], 90)
        self.assertTrue(payload["evidence"])
        self.assertIn("biological_system", payload["confidence"])

    def test_ambiguities_and_clarifications_are_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ExperimentDesignCopilot(settings=self._settings(tmpdir))
            draft = service.create_draft("user:researcher-a", DEMO_NARRATIVE)
            questions = draft["draft"]["clarification_questions"]

        ids = {question["question_id"] for question in questions}
        self.assertIn("replicates", ids)
        self.assertIn("sample_counts", ids)
        self.assertIn("protocol_version", ids)
        self.assertEqual(draft["status"], "awaiting_clarification")
        self.assertEqual(draft["draft"]["sample_planning"]["status"], "incomplete")

    def test_clarification_answers_enable_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ExperimentDesignCopilot(settings=self._settings(tmpdir))
            draft = service.create_draft("user:researcher-a", DEMO_NARRATIVE)
            updated = service.answer_clarifications(
                "user:researcher-a",
                draft["session_id"],
                {
                    "replicates": "3 biological replicates",
                    "sample_counts": "6 organoids per replicate",
                    "protocol_version": "Use current Meyer structured demo version",
                },
            )

        self.assertEqual(updated["status"], "awaiting_approval")
        self.assertTrue(all(not q["required"] or q["status"] == "answered" for q in updated["draft"]["clarification_questions"]))
        self.assertEqual(updated["draft"]["conditions"][0]["replicate_count"], 3)
        self.assertEqual(updated["draft"]["conditions"][0]["sample_count_per_replicate"], 6)

    def test_approval_creates_draft_experiment_only_after_required_answers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ExperimentDesignCopilot(settings=self._settings(tmpdir))
            draft = service.create_draft("user:researcher-a", DEMO_NARRATIVE)
            with self.assertRaises(Exception):
                service.approve_draft("user:researcher-a", draft["session_id"])
            service.answer_clarifications(
                "user:researcher-a",
                draft["session_id"],
                {"replicates": "3", "sample_counts": "6", "protocol_version": "current"},
            )
            approved = service.approve_draft("user:researcher-a", draft["session_id"], experiment_id="COPILOT_NK_26")

        self.assertTrue(approved["created_new"])
        self.assertEqual(approved["experiment"]["experiment_id"], "COPILOT_NK_26")
        self.assertTrue(approved["workspace"]["design"]["conditions"])
        self.assertTrue(approved["workspace"]["timeline"]["events"])

    def test_unknown_fields_remain_unknown_not_hallucinated(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ExperimentDesignCopilot(settings=self._settings(tmpdir))
            draft = service.create_draft("user:researcher-a", "Test a new cell line with a treatment later.")

        payload = draft["draft"]
        self.assertIsNone(payload["protocol"])
        self.assertIsNone(payload["expected_duration"])
        self.assertIn("Biological system is missing.", payload["ambiguities"])


if __name__ == "__main__":
    unittest.main()
