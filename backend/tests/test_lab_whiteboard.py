"""Tests for the Laboratory Whiteboard API aggregation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app import main
from app.config import Settings
from app.experiments import Experiment
from app.storage import SQLiteStore


class LabWhiteboardTests(unittest.TestCase):
    """Whiteboard should return display-ready situational awareness data."""

    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def test_whiteboard_empty_lab_has_sections_and_rotation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_settings = main.settings
            main.settings = self._settings(tmpdir)
            try:
                payload = main.laboratory_whiteboard()
            finally:
                main.settings = original_settings

        self.assertIn("metrics", payload)
        self.assertIn("sections", payload)
        self.assertIn("rotation", payload)
        self.assertGreaterEqual(len(payload["sections"]), 8)
        self.assertTrue(payload["display"]["tv_friendly"])

    def test_whiteboard_includes_active_experiment_and_inventory_alert(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_settings = main.settings
            main.settings = self._settings(tmpdir)
            try:
                store = SQLiteStore(settings=main.settings)
                store.upsert_experiment(
                    Experiment(
                        id="experiment:whiteboard",
                        source_document_id="document:whiteboard",
                        source_provider="markdown",
                        title="Whiteboard SAG experiment",
                        experiment_id="NK_Expt_31",
                        compounds=["SAG"],
                        markers=["SIX6"],
                    )
                )
                store.start_session(experiment_id="NK_Expt_31", notes="Whiteboard active session.")
                store.save_inventory_item(
                    name="SAG",
                    category="compound",
                    vendor="ResearchOS",
                    quantity=0,
                    reorder_threshold=1,
                    item_id="inventory:whiteboard-sag",
                )
                payload = main.laboratory_whiteboard()
            finally:
                main.settings = original_settings

        sections = {section["id"]: section for section in payload["sections"]}
        self.assertGreater(payload["metrics"]["active_sessions"], 0)
        self.assertGreater(sections["active_experiments"]["count"], 0)
        self.assertGreater(sections["inventory_alerts"]["count"], 0)
        first_experiment = sections["active_experiments"]["cards"][0]
        self.assertEqual(first_experiment["status"], "Active session")


if __name__ == "__main__":
    unittest.main()
