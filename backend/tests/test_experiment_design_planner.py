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
                        reminder_enabled=True,
                    ),
                )
                activated = main.activate_experiment_design(design.design_id)
                timeline = main.experiment_design_timeline(design.design_id)
                calendar = main.experiment_design_calendar(design.design_id)
                reminders = main.experiment_design_reminders(include_drafts=False, workspace_id=None)
                reminder_due = main.experiment_design_reminders_due_today(workspace_id=None)
                reminder_upcoming = main.experiment_design_reminders_upcoming(days=7, workspace_id=None)
                exported_ics = main.export_experiment_design_ics(design.design_id)
                exported_reminders_ics = main.export_experiment_design_reminders_ics(workspace_id=None, include_drafts=False)
                completed = main.complete_experiment_design_reminder(str(event["event_id"]))
                dismissed = main.dismiss_experiment_design_reminder(str(event["event_id"]))
                due = main.experiment_designs_due_today(workspace_id=None)
                upcoming = main.experiment_designs_upcoming(days=7, workspace_id=None)
                exported = main.export_experiment_design_csv(design.design_id)
                undated = main.create_experiment_design(main.ExperimentDesignRequest(title="Undated design"))
                with self.assertRaises(main.HTTPException) as missing_start_date:
                    main.export_experiment_design_ics(undated.design_id)
                preview = main.preview_experiment_design_import(
                    main.DesignImportRequest(
                        csv_text="condition,day,event_type,treatment,dose,units,replicate,alert_enabled\n"
                        "BMP4 pulse,D9,treatment,BMP4,10,ng/mL,1,true\n"
                    )
                )
                mapped_preview = main.preview_experiment_design_import(
                    main.DesignImportRequest(
                        csv_text="Experiment,Cell Line,Condition,Day,Event,Treatment,Replicate,Reminder\n"
                        "Mapped SAG design,SIX6 reporter,DMSO,D1,treatment,DMSO,1,true\n"
                    )
                )
                mapped = main.import_experiment_design_mapped_csv(
                    main.DesignMappedCsvImportRequest(
                        csv_text="Experiment,Cell Line,Condition,Day,Event,Treatment,Replicate,Reminder\n"
                        "Mapped SAG design,SIX6 reporter,DMSO,D1,treatment,DMSO,1,true\n"
                        "Mapped SAG design,SIX6 reporter,SAG,D9,imaging,SAG,2,true\n",
                        mapping={
                            "title": "Experiment",
                            "cell_line_or_model": "Cell Line",
                            "condition_name": "Condition",
                            "day": "Day",
                            "event_type": "Event",
                            "treatment": "Treatment",
                            "replicate": "Replicate",
                            "alert_enabled": "Reminder",
                        },
                    )
                )
                templates = main.experiment_design_import_templates(workspace_id=None)
                saved_template = main.create_experiment_design_import_template(
                    main.DesignImportTemplateRequest(
                        name="Mapped design template",
                        mapping={"condition_name": "Condition", "day": "Day", "event_type": "Event"},
                    )
                )
                deleted_template = main.delete_experiment_design_import_template(saved_template.template_id)
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
        self.assertEqual(activated.status, "active")
        self.assertEqual(event["event_type"], "treatment")
        self.assertEqual(reminders["count"], 1)
        self.assertIn("reminders", reminder_due)
        self.assertGreaterEqual(reminder_upcoming["count"], 1)
        self.assertEqual(completed["event"]["reminder_status"], "completed")
        self.assertEqual(dismissed["event"]["reminder_status"], "dismissed")
        self.assertEqual(timeline["event_count"], 1)
        self.assertEqual(calendar["calendar"][0]["label"], "D1")
        self.assertGreaterEqual(due["count"], 0)
        self.assertEqual(upcoming["count"], 0)
        self.assertIn("DMSO control", exported.body.decode("utf-8"))
        self.assertIn("BEGIN:VCALENDAR", exported_ics.body.decode("utf-8"))
        self.assertIn("D1 SAG rescue", exported_ics.body.decode("utf-8"))
        self.assertIn("BEGIN:VEVENT", exported_reminders_ics.body.decode("utf-8"))
        self.assertEqual(missing_start_date.exception.status_code, 400)
        self.assertIn("start_date", missing_start_date.exception.detail)
        self.assertEqual(preview["inferred_conditions"], ["BMP4 pulse"])
        self.assertEqual(mapped_preview["suggested_mappings"]["condition_name"], "Condition")
        self.assertEqual(mapped_preview["missing_required_fields"], [])
        self.assertEqual(mapped.title, "Mapped SAG design")
        self.assertEqual(len(mapped.conditions), 2)
        self.assertEqual(len(mapped.events), 2)
        self.assertTrue(any(template.template_id.startswith("default:") for template in templates))
        self.assertTrue(saved_template.template_id.startswith("design_import_template:"))
        self.assertTrue(deleted_template["deleted"])
        self.assertEqual(imported.title, "Imported BMP4 design")
        self.assertEqual(factorial["condition_count"], 4)
        self.assertFalse(balance["balanced_replicates"])


if __name__ == "__main__":
    unittest.main()
