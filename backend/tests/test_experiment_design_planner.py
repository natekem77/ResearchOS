"""Tests for the experiment design planner."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app import main
from app.config import Settings


class ExperimentDesignPlannerTests(unittest.TestCase):
    """Experiment design planning should be provider-agnostic."""

    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def test_design_lifecycle_timeline_export_import_and_doe(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_settings = main.settings
            main.settings = self._settings(tmpdir)
            try:
                design = main.create_experiment_design(
                    main.ExperimentDesignRequest(
                        title="D1 SAG rescue",
                        experiment_type="organoid",
                        cell_line_or_model="SIX6 reporter iPSC",
                        reporters=["SIX6", "BRN3B"],
                        status="active",
                    )
                )
                condition = main.add_design_condition(
                    design.design_id,
                    main.DesignConditionRequest(
                        condition_name="DMSO control",
                        treatment="DMSO",
                        start_day="D1",
                        replicate_count=3,
                        sample_count=6,
                    ),
                )
                event = main.add_design_event(
                    design.design_id,
                    main.DesignEventRequest(
                        condition_id=str(condition["condition_id"]),
                        day="D1",
                        event_type="treatment",
                        title="Start treatment",
                        alert_enabled=True,
                    ),
                )
                timeline = main.experiment_design_timeline(design.design_id)
                calendar = main.experiment_design_calendar(design.design_id)
                due = main.experiment_designs_due_today(workspace_id=None)
                upcoming = main.experiment_designs_upcoming(days=7, workspace_id=None)
                exported = main.export_experiment_design_csv(design.design_id)
                preview = main.preview_experiment_design_import(
                    main.DesignImportRequest(
                        csv_text="condition,day,event_type,treatment,dose,units,replicate,alert_enabled\n"
                        "BMP4 pulse,D9,treatment,BMP4,10,ng/mL,1,true\n"
                    )
                )
                imported = main.import_experiment_design_csv(
                    main.DesignImportRequest(
                        csv_text="condition,day,event_type,treatment,dose,units,replicate,alert_enabled\n"
                        "BMP4 pulse,D9,treatment,BMP4,10,ng/mL,1,true\n",
                        title="Imported BMP4 design",
                    )
                )
                factorial = main.experiment_design_full_factorial(
                    main.FullFactorialRequest(factors={"compound": ["SAG", "BMP4"], "dose": ["low", "high"]})
                )
                balance = main.experiment_design_check_balance(
                    main.BalanceCheckRequest(
                        conditions=[
                            main.DesignConditionRequest(condition_name="DMSO control", replicate_count=3, sample_count=3),
                            main.DesignConditionRequest(condition_name="SAG", replicate_count=2, sample_count=3),
                        ]
                    )
                )
            finally:
                main.settings = original_settings

        self.assertEqual(design.status, "active")
        self.assertEqual(event["event_type"], "treatment")
        self.assertEqual(timeline["event_count"], 1)
        self.assertEqual(calendar["calendar"][0]["label"], "D1")
        self.assertGreaterEqual(due["count"], 0)
        self.assertGreaterEqual(upcoming["count"], 1)
        self.assertIn("DMSO control", exported.body.decode("utf-8"))
        self.assertEqual(preview["inferred_conditions"], ["BMP4 pulse"])
        self.assertEqual(imported.title, "Imported BMP4 design")
        self.assertEqual(factorial["condition_count"], 4)
        self.assertFalse(balance["balanced_replicates"])


if __name__ == "__main__":
    unittest.main()
