"""Tests for the generalized experiment workspace foundation."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.attachment_storage import LocalAttachmentStorage
from app.config import Settings
from app.general_experiments import (
    ExperimentAuthorizationError,
    ExperimentConflictError,
    GeneralExperimentService,
    RichNotebookContextService,
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
        self.assertEqual(reopened["content"], delta)
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

        self.assertEqual(first["content"], legacy)
        self.assertIn("Existing line one.", first["plain_text_cache"])
        self.assertEqual(first["structured_content"], second["structured_content"])
        self.assertTrue(first["migration"]["idempotent"])
        self.assertTrue(first["migration"]["original_source_preserved"])

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
