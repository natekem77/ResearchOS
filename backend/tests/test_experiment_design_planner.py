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
                layout = main.generate_experiment_design_plate_layout(
                    design.design_id,
                    main.GeneratePlateLayoutRequest(format="24-well", balanced=True),
                )
                layout_detail = main.plate_layout_detail(layout.layout_id)
                updated_layout = main.update_plate_layout(
                    layout.layout_id,
                    main.PlateLayoutRequest(
                        design_id=layout.design_id,
                        title="Updated D1 SAG layout",
                        format=layout.format,
                        rows=layout.rows,
                        columns=layout.columns,
                        wells=[main.WellAssignmentRequest(**well) for well in layout.wells],
                        warnings=layout.warnings,
                    ),
                )
                layout_csv = main.export_plate_layout_csv(layout.layout_id)
                listed_layouts = main.plate_layouts(workspace_id=None)
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
                design_templates = main.experiment_design_templates(workspace_id=None)
                builtin_template = main.experiment_design_template_detail("builtin:retinal_organoid_d1_d9_treatment")
                from_builtin = main.create_design_from_experiment_design_template(
                    "builtin:retinal_organoid_d1_d9_treatment",
                    main.TemplateCreateDesignRequest(
                        title="Template-derived retinal organoid design",
                        start_date="2026-07-08",
                        cell_line_or_model="SIX6 reporter iPSC",
                        reporters=["SIX6", "BRN3B"],
                    ),
                )
                saved_design_template = main.create_experiment_design_template(
                    main.ExperimentDesignTemplateRequest(
                        name="Saved treatment template",
                        description="Reusable treatment template",
                        experiment_type="cell culture",
                        default_conditions=[{"condition_name": "Vehicle", "treatment": "DMSO", "start_day": "D0"}],
                        default_events=[{"day": "D0", "event_type": "treatment", "title": "Treat cells", "reminder_enabled": True}],
                        tags=["test"],
                    )
                )
                updated_design_template = main.update_experiment_design_template(
                    saved_design_template.template_id,
                    main.ExperimentDesignTemplateRequest(
                        name="Updated treatment template",
                        description="Reusable treatment template",
                        experiment_type="cell culture",
                        default_conditions=[{"condition_name": "Vehicle", "treatment": "DMSO", "start_day": "D0"}],
                        default_events=[{"day": "D0", "event_type": "treatment", "title": "Treat cells", "reminder_enabled": True}],
                        tags=["test", "updated"],
                    ),
                )
                from_saved = main.create_design_from_experiment_design_template(
                    saved_design_template.template_id,
                    main.TemplateCreateDesignRequest(title="Template-derived saved design", start_date="2026-07-08"),
                )
                saved_from_design = main.save_experiment_design_as_template(
                    design.design_id,
                    main.SaveDesignAsTemplateRequest(name="Saved from current design"),
                )
                deleted_design_template = main.delete_experiment_design_template(saved_design_template.template_id)
                imported = main.import_experiment_design_csv(
                    main.DesignImportRequest(
                        csv_text="condition,day,event_type,treatment,dose,units,replicate,alert_enabled\n"
                        "BMP4 pulse,D9,treatment,BMP4,10,ng/mL,1,true\n",
                        title="Imported BMP4 design",
                    )
                )
                deleted_layout = main.delete_plate_layout(layout.layout_id)
                visual_builder = main.create_visual_experiment_builder(
                    main.VisualExperimentBuilderRequest(
                        title="Visual D1 SAG design",
                        nodes=[
                            main.VisualNodeRequest(node_id="experiment", type="experiment", label="Visual D1 SAG design", properties={"experiment_type": "retinal organoid"}),
                            main.VisualNodeRequest(node_id="cell", type="cell_line", label="SIX6 reporter iPSC"),
                            main.VisualNodeRequest(node_id="control", type="treatment", label="DMSO control", properties={"replicate_count": 3, "start_day": "D1"}),
                            main.VisualNodeRequest(node_id="sag", type="compound", label="SAG", properties={"dose": "100", "units": "nM", "replicate_count": 3, "start_day": "D1"}),
                            main.VisualNodeRequest(node_id="d32", type="timepoint", label="D32"),
                            main.VisualNodeRequest(node_id="image", type="imaging", label="Image SIX6/BRN3B"),
                        ],
                        connections=[
                            main.VisualConnectionRequest(source="experiment", target="cell"),
                            main.VisualConnectionRequest(source="experiment", target="control", relationship="branch"),
                            main.VisualConnectionRequest(source="experiment", target="sag", relationship="branch"),
                            main.VisualConnectionRequest(source="sag", target="d32", relationship="sequential"),
                            main.VisualConnectionRequest(source="d32", target="image", relationship="sequential"),
                        ],
                    )
                )
                visual_compile = main.compile_visual_experiment_builder(visual_builder.builder_id)
                visual_generated = main.generate_design_from_visual_experiment_builder(
                    visual_builder.builder_id,
                    main.VisualBuilderGenerateRequest(title="Generated visual SAG design", start_date="2026-07-08", generate_plate_layout=True, plate_format="24-well"),
                )
                visual_updated = main.update_visual_experiment_builder(
                    visual_builder.builder_id,
                    main.VisualExperimentBuilderRequest(
                        title="Visual D1 SAG design updated",
                        nodes=[main.VisualNodeRequest(**node) for node in visual_builder.nodes],
                        connections=[main.VisualConnectionRequest(**connection) for connection in visual_builder.connections],
                    ),
                )
                visual_list = main.visual_experiment_builders(workspace_id=None)
                visual_deleted = main.delete_visual_experiment_builder(visual_builder.builder_id)
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
        self.assertEqual(layout.format, "24-well")
        self.assertEqual(layout.rows, 4)
        self.assertEqual(layout.columns, 6)
        self.assertGreaterEqual(len([well for well in layout.wells if well.get("condition")]), 1)
        self.assertEqual(layout_detail.layout_id, layout.layout_id)
        self.assertEqual(updated_layout.title, "Updated D1 SAG layout")
        self.assertIn("position,condition", layout_csv.body.decode("utf-8"))
        self.assertTrue(any(item.layout_id == layout.layout_id for item in listed_layouts))
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
        self.assertTrue(any(template.template_id.startswith("builtin:") for template in design_templates))
        self.assertEqual(builtin_template.name, "Retinal organoid D1 vs D9 treatment")
        self.assertEqual(from_builtin.title, "Template-derived retinal organoid design")
        self.assertGreaterEqual(len(from_builtin.conditions), 1)
        self.assertGreaterEqual(len(from_builtin.events), 1)
        self.assertTrue(saved_design_template.template_id.startswith("design_template:"))
        self.assertEqual(updated_design_template.name, "Updated treatment template")
        self.assertEqual(from_saved.title, "Template-derived saved design")
        self.assertEqual(saved_from_design.name, "Saved from current design")
        self.assertTrue(deleted_design_template["deleted"])
        self.assertEqual(imported.title, "Imported BMP4 design")
        self.assertTrue(deleted_layout["deleted"])
        self.assertEqual(visual_compile["compiled"]["title"], "Visual D1 SAG design")
        self.assertEqual(visual_generated["design"]["title"], "Generated visual SAG design")
        self.assertIsNotNone(visual_generated["plate_layout"])
        self.assertGreaterEqual(visual_generated["timeline"]["event_count"], 1)
        self.assertEqual(visual_updated.title, "Visual D1 SAG design updated")
        self.assertTrue(any(item.builder_id == visual_builder.builder_id for item in visual_list))
        self.assertTrue(visual_deleted["deleted"])
        self.assertEqual(factorial["condition_count"], 4)
        self.assertFalse(balance["balanced_replicates"])


if __name__ == "__main__":
    unittest.main()
