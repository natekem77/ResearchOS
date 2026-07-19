"""Tests for structured Protocol Hub 2.0."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
import json
from pathlib import Path
from unittest.mock import patch

from app.attachment_storage import AttachmentStorageError
from app.config import Settings
from app.general_experiments import GeneralExperimentService
from app.protocol_hub import ProtocolHubService, ProtocolHubValidationError


class _FakeAIProvider:
    provider_name = "fake-ai"

    def __init__(self, response: str) -> None:
        self.response = response
        self.messages: list[str] = []

    def chat(self, message: str, context: str | None = None) -> str:
        self.messages.append(message)
        return self.response


def _docx_bytes(*, paragraphs: list[str], table_rows: list[list[str]]) -> bytes:
    from io import BytesIO

    def paragraph(text: str) -> str:
        return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"

    rows = []
    for row in table_rows:
        cells = "".join(f"<w:tc><w:p><w:r><w:t>{cell}</w:t></w:r></w:p></w:tc>" for cell in row)
        rows.append(f"<w:tr>{cells}</w:tr>")
    body = "".join(paragraph(text) for text in paragraphs) + f"<w:tbl>{''.join(rows)}</w:tbl>"
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


class ProtocolHubTests(unittest.TestCase):
    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def _ai_settings(self, tmpdir: str) -> Settings:
        return Settings(
            database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}",
            ai_provider="openai-compatible",
            ai_base_url="http://example.invalid",
            ai_model="protocol-test-model",
        )

    def _service(self, tmpdir: str) -> ProtocolHubService:
        return ProtocolHubService(settings=self._settings(tmpdir))

    def test_protocol_crud_and_workspace_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            protocol = service.create_or_update_protocol(
                actor_user_id="user:pi-owner",
                lab_id="lab:demo",
                title="Biochemical assay protocol",
                short_name="Assay",
                description="General assay.",
                category="assay",
                biological_system="biochemical assay",
                sample_unit="tube",
                version_number="1.0",
                content="# Assay",
                events=[{"title": "Start reaction", "relative_day": 0, "event_type": "assay"}],
                materials=[{"name": "Buffer", "vendor": "Lab-made"}],
                media=[{"recipe": "Assay buffer", "components": ["PBS"]}],
                expected_results=[{"title": "Signal above blank", "day": 0}],
                troubleshooting=[{"issue": "Low signal", "possible_causes": ["Reagent expired"]}],
            )

        workspace = protocol["workspace"]
        self.assertEqual(protocol["short_name"], "Assay")
        self.assertEqual(len(workspace["timeline"]), 1)
        self.assertEqual(len(workspace["materials"]), 1)
        self.assertEqual(len(workspace["media"]), 1)
        self.assertEqual(len(workspace["expected_results"]), 1)
        self.assertEqual(len(workspace["troubleshooting"]), 1)

    def test_versioning_and_historical_experiment_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            hub = ProtocolHubService(settings=settings)
            general = GeneralExperimentService(settings=settings)
            protocol = hub.get_protocol("protocol:meyer-retinal-organoid-protocol")
            assert protocol is not None
            old_version = protocol["current_version_id"]
            experiment = general.create_from_protocol(
                "user:researcher-a",
                protocol["protocol_id"],
                old_version,
                "Protocol history experiment",
            )
            new_version = hub.create_version(
                "user:pi-owner",
                protocol["protocol_id"],
                "2.0",
                "Added D10 QC",
                "Updated protocol",
                events=[{"title": "D10 QC", "day": 10, "event_type": "qc"}],
            )
            workspace = general.get_workspace(experiment["experiment_id"], "user:researcher-a")

        assert workspace is not None
        self.assertNotEqual(old_version, new_version["protocol_version_id"])
        self.assertEqual(workspace["design"]["protocol_references"][0]["protocol_version_id"], old_version)
        self.assertFalse(any(event["title"] == "D10 QC" for event in workspace["timeline"]["events"]))

    def test_timeline_inheritance_from_protocol_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            hub = ProtocolHubService(settings=settings)
            general = GeneralExperimentService(settings=settings)
            protocol = hub.get_protocol("protocol:meyer-retinal-organoid-protocol")
            assert protocol is not None
            experiment = general.create_from_protocol(
                "user:researcher-a",
                protocol["protocol_id"],
                protocol["current_version_id"],
                "Timeline inheritance",
            )
            timeline = general.timeline(experiment["experiment_id"], "user:researcher-a")

        self.assertTrue(any(event["source"] == "protocol" for event in timeline["events"]))
        self.assertTrue(any(event["protocol_event_id"] for event in timeline["events"]))

    def test_inventory_material_link_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            protocol = service.create_or_update_protocol(
                actor_user_id="user:pi-owner",
                lab_id="lab:demo",
                title="Inventory linked protocol",
                short_name="Inventory protocol",
                description="Uses an inventory record.",
                category="materials",
                biological_system="general",
                sample_unit="sample",
                version_number="1.0",
                materials=[{"name": "SAG", "inventory_item_id": "inventory:sag", "vendor": "Demo"}],
            )

        material = protocol["workspace"]["materials"][0]
        self.assertEqual(material["inventory_item_id"], "inventory:sag")

    def test_protocol_search_and_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            results = service.search("BMP4")
            protocol = service.get_protocol("protocol:meyer-retinal-organoid-protocol")
            assert protocol is not None
            versions = protocol["versions"]
            new_version = service.create_version(
                "user:pi-owner",
                protocol["protocol_id"],
                "compare-test",
                "Comparison version",
                "Comparison content",
                events=[{"title": "New comparison event", "day": 12, "event_type": "qc"}],
            )
            comparison = service.compare_versions(versions[0]["protocol_version_id"], new_version["protocol_version_id"])

        self.assertTrue(results["results"])
        self.assertIn("New comparison event", comparison["timeline_differences"]["right_only"])

    def test_protocol_notebook_save_is_versioned(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            protocol = service.get_protocol("protocol:meyer-retinal-organoid-protocol")
            assert protocol is not None
            notebook = protocol["workspace"]["notebook"]
            updated = service.save_notebook("user:pi-owner", notebook["document_id"], notebook["version"], "# Updated protocol notebook")

        self.assertEqual(updated["version"], notebook["version"] + 1)

    def test_paste_text_creates_reviewable_extraction_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            draft = service.create_extraction_draft_from_text(
                actor_user_id="user:researcher-a",
                lab_id="lab:demo",
                proposed_title="Meyer notes",
                origin="pasted_text",
                source_text=(
                    "Meyer retinal organoid protocol notes.\n"
                    "Add BMP4 on D6. Attach organoids on D9. "
                    "Continue this current experiment through D90."
                ),
            )

        self.assertEqual(draft["status"], "awaiting_review")
        self.assertEqual(draft["proposed_biological_system"], "retinal organoid")
        self.assertEqual(draft["proposed_sample_unit"], "organoid")
        self.assertTrue(any(event["title"] == "BMP4" for event in draft["proposed_events"]))
        self.assertIn("Add BMP4 on D6", draft["source_text"])
        self.assertTrue(draft["extraction_evidence"])
        self.assertTrue(any("concentration" in item.lower() for item in draft["ambiguities"]))

    def test_protocol_import_metadata_and_incomplete_draft_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            imported = service.create_import(
                actor_user_id="user:researcher-a",
                lab_id="lab:demo",
                source_type="pdf",
                original_filename="meyer.pdf",
                storage_reference="attachments/protocols/meyer.pdf",
                mime_type="application/pdf",
            )
            draft = service.create_extraction_draft_from_text(
                actor_user_id="user:researcher-a",
                lab_id="lab:demo",
                source_text="Protocol text without timed events.",
                origin="document",
                import_id=imported["import_id"],
            )
            saved = service.update_extraction_draft(draft["extraction_id"], {"status": "draft"})

        self.assertEqual(imported["original_filename"], "meyer.pdf")
        self.assertEqual(draft["import_id"], imported["import_id"])
        self.assertEqual(saved["status"], "draft")
        self.assertTrue(any("No timed protocol events" in item for item in saved["ambiguities"]))

    def test_protocol_pdf_upload_persists_source_document_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            uploaded = service.upload_protocol_document(
                actor_user_id="user:researcher-a",
                lab_id="lab:demo",
                filename="Meyer Protocol.pdf",
                data=b"%PDF-1.4\nprotocol",
                mime_type="application/pdf",
                source_type="pdf",
            )
            protocol = service.get_protocol(uploaded["protocol"]["protocol_id"])
            listed = service.list_protocols()

        assert protocol is not None
        attachment = uploaded["attachment"]
        self.assertEqual(attachment["original_filename"], "Meyer Protocol.pdf")
        self.assertEqual(attachment["mime_type"], "application/pdf")
        self.assertEqual(attachment["file_extension"], ".pdf")
        self.assertEqual(attachment["size_bytes"], len(b"%PDF-1.4\nprotocol"))
        self.assertNotIn("Meyer Protocol.pdf", attachment["storage_path"])
        self.assertEqual(protocol["source_documents"][0]["import_id"], attachment["import_id"])
        self.assertEqual(protocol["source_documents"][0]["original_filename"], "Meyer Protocol.pdf")
        self.assertTrue(
            any(
                item["protocol_id"] == protocol["protocol_id"]
                and item["source_document"]["original_filename"] == "Meyer Protocol.pdf"
                for item in listed
            )
        )

    def test_protocol_docx_upload_succeeds_and_repeated_get_returns_attachment(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            uploaded = service.upload_protocol_document(
                actor_user_id="user:researcher-a",
                lab_id="lab:demo",
                filename="Protocol Source.docx",
                data=b"docx bytes",
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            first = service.get_protocol(uploaded["protocol"]["protocol_id"])
            second = service.get_protocol(uploaded["protocol"]["protocol_id"])

        assert first is not None
        assert second is not None
        self.assertEqual(first["source_document"]["attachment_type"], "docx")
        self.assertEqual(second["source_documents"][0]["original_filename"], "Protocol Source.docx")
        self.assertEqual(second["source_documents"][0]["checksum"], uploaded["attachment"]["checksum"])

    def test_uploaded_docx_extracts_paragraphs_tables_and_requires_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            uploaded = service.upload_protocol_document(
                actor_user_id="user:researcher-a",
                lab_id="lab:demo",
                filename="PLSR protocol v1 copy.docx",
                data=_docx_bytes(
                    paragraphs=[
                        "PLSR protocol v1",
                        "Timeline",
                        "Day 0 seed cells.",
                        "Day 2 change media.",
                        "Materials",
                    ],
                    table_rows=[
                        ["Reagent", "Concentration"],
                        ["BMP4", "10 ng/mL"],
                        ["Matrigel", "1x"],
                    ],
                ),
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            protocol_id = uploaded["protocol"]["protocol_id"]
            draft = service.extract_uploaded_protocol_document(
                actor_user_id="user:researcher-a",
                protocol_id=protocol_id,
            )
            before_approval = service.get_protocol(protocol_id)
            approved = service.approve_extraction_for_protocol(
                actor_user_id="user:researcher-a",
                protocol_id=protocol_id,
                version_label="extracted-review-1",
                confirmed=True,
            )
            after_approval = service.get_protocol(protocol_id)

        assert before_approval is not None
        assert after_approval is not None
        self.assertEqual(draft["status"], "awaiting_review")
        self.assertTrue(any(event["relative_day"] == 0 for event in draft["proposed_events"]))
        self.assertTrue(any(material["name"] == "BMP4" for material in draft["proposed_materials"]))
        self.assertEqual(draft["extraction_evidence"]["source_document"]["parser_version"], "protocol-extraction-hybrid-v1")
        self.assertEqual(draft["extraction_evidence"]["source_document"]["metadata"]["table_count"], 1)
        self.assertFalse(before_approval["workspace"]["materials"])
        self.assertTrue(any(material["name"] == "BMP4" for material in after_approval["workspace"]["materials"]))
        self.assertEqual(approved["draft"]["status"], "approved")

    def test_canonical_docx_structure_preserves_headings_and_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            uploaded = service.upload_protocol_document(
                actor_user_id="user:researcher-a",
                lab_id="lab:demo",
                filename="structured.docx",
                data=_docx_bytes(
                    paragraphs=["Protocol title", "Materials", "Timeline", "Day 1 incubate at 37 C."],
                    table_rows=[["Reagent", "Concentration"], ["BMP4", "10 ng/mL"]],
                ),
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            run = service.create_protocol_extraction_run(
                actor_user_id="user:researcher-a",
                protocol_id=uploaded["protocol"]["protocol_id"],
                mode="rules_only",
            )

        blocks = run["canonical_document"]["blocks"]
        self.assertTrue(any(block["type"] == "heading" and block["text"] == "Materials" for block in blocks))
        table_blocks = [block for block in blocks if block["type"] == "table_row"]
        self.assertEqual(table_blocks[1]["columns"]["Reagent"], "BMP4")
        self.assertEqual(run["mode"], "rules_only")
        self.assertTrue(run["items"])

    def test_ai_assisted_extraction_uses_valid_provider_output(self) -> None:
        ai_payload = {
            "protocol_title": "AI classified protocol",
            "timeline": [
                {
                    "source_ids": ["p-4"],
                    "day_or_time": "D1",
                    "step_title": "Incubate cells",
                    "instructions": "Incubate cells at 37 C.",
                    "duration": None,
                    "temperature": "37 C",
                    "incubation": True,
                    "notes": None,
                    "confidence": "high",
                }
            ],
            "materials": [
                {
                    "source_ids": ["table-1-row-2"],
                    "name": "BMP4",
                    "supplier": None,
                    "catalog_number": None,
                    "stock_concentration": None,
                    "working_concentration": "10 ng/mL",
                    "amount": None,
                    "unit": None,
                    "storage": None,
                    "notes": None,
                    "confidence": "high",
                }
            ],
            "media_recipes": [],
            "expected_results_qc": [],
            "troubleshooting": [],
            "unclassified_notes": [],
        }
        fake = _FakeAIProvider(json.dumps(ai_payload))
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ProtocolHubService(settings=self._ai_settings(tmpdir))
            uploaded = service.upload_protocol_document(
                actor_user_id="user:researcher-a",
                lab_id="lab:demo",
                filename="ai.docx",
                data=_docx_bytes(
                    paragraphs=["Protocol title", "Materials", "Timeline", "Day 1 incubate cells at 37 C."],
                    table_rows=[["Reagent", "Concentration"], ["BMP4", "10 ng/mL"]],
                ),
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            with patch("app.protocol_ai_extraction.get_ai_provider", return_value=fake):
                run = service.create_protocol_extraction_run(
                    actor_user_id="user:researcher-a",
                    protocol_id=uploaded["protocol"]["protocol_id"],
                    mode="ai_assisted",
                    user_instruction="Treat D entries as timeline events.",
                )

        self.assertEqual(run["provider"], "fake-ai")
        self.assertEqual(run["model"], "protocol-test-model")
        self.assertEqual(run["user_instruction"], "Treat D entries as timeline events.")
        self.assertEqual(run["draft"]["proposed_title"], "AI classified protocol")
        self.assertTrue(any(item["origin"] == "ai" for item in run["items"]))
        self.assertIn("Treat D entries", fake.messages[0])

    def test_malformed_ai_output_falls_back_to_rules_only_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ProtocolHubService(settings=self._ai_settings(tmpdir))
            uploaded = service.upload_protocol_document(
                actor_user_id="user:researcher-a",
                lab_id="lab:demo",
                filename="fallback.docx",
                data=_docx_bytes(
                    paragraphs=["Fallback protocol", "Timeline", "Day 2 change media."],
                    table_rows=[["Reagent", "Concentration"], ["SAG", "300 nM"]],
                ),
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            with patch("app.protocol_ai_extraction.get_ai_provider", return_value=_FakeAIProvider("{bad json")):
                run = service.create_protocol_extraction_run(
                    actor_user_id="user:researcher-a",
                    protocol_id=uploaded["protocol"]["protocol_id"],
                    mode="ai_assisted",
                )

        self.assertEqual(run["mode"], "ai_assisted")
        self.assertIsNotNone(run["error"])
        self.assertTrue(any("rules-only extraction was used" in warning for warning in run["draft"]["warnings"]))
        self.assertTrue(any(event["relative_day"] == 2 for event in run["draft"]["proposed_events"]))

    def test_unknown_ai_source_ids_are_rejected(self) -> None:
        bad_payload = {
            "protocol_title": None,
            "timeline": [{"source_ids": ["missing"], "step_title": "Invented", "confidence": "high"}],
            "materials": [],
            "media_recipes": [],
            "expected_results_qc": [],
            "troubleshooting": [],
            "unclassified_notes": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ProtocolHubService(settings=self._ai_settings(tmpdir))
            uploaded = service.upload_protocol_document(
                actor_user_id="user:researcher-a",
                lab_id="lab:demo",
                filename="bad-source.docx",
                data=_docx_bytes(paragraphs=["Timeline", "Day 3 collect."], table_rows=[]),
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            with patch("app.protocol_ai_extraction.get_ai_provider", return_value=_FakeAIProvider(json.dumps(bad_payload))):
                run = service.create_protocol_extraction_run(
                    actor_user_id="user:researcher-a",
                    protocol_id=uploaded["protocol"]["protocol_id"],
                    mode="ai_assisted",
                )

        self.assertIn("referenced no valid source IDs", run["error"])
        self.assertFalse(any(item["normalized"].get("title") == "Invented" for item in run["items"]))

    def test_extraction_reruns_create_separate_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            uploaded = service.upload_protocol_document(
                actor_user_id="user:researcher-a",
                lab_id="lab:demo",
                filename="rerun.docx",
                data=_docx_bytes(paragraphs=["Timeline", "Day 0 seed."], table_rows=[]),
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            first = service.create_protocol_extraction_run(
                actor_user_id="user:researcher-a",
                protocol_id=uploaded["protocol"]["protocol_id"],
                mode="rules_only",
            )
            second = service.create_protocol_extraction_run(
                actor_user_id="user:researcher-a",
                protocol_id=uploaded["protocol"]["protocol_id"],
                mode="rules_only",
                user_instruction="Second pass.",
            )
            runs = service.list_protocol_extraction_runs(uploaded["protocol"]["protocol_id"])

        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertEqual(len(runs), 2)
        self.assertEqual(second["user_instruction"], "Second pass.")

    def test_mobile_protocol_extractions_route_matches_flutter_request(self) -> None:
        from app.main import app

        matching_routes = [
            route
            for route in app.routes
            if getattr(route, "path", None) == "/mobile/protocols/{protocol_id}/extractions"
        ]
        methods = set().union(*(getattr(route, "methods", set()) for route in matching_routes))

        self.assertIn("POST", methods)

    def test_protocol_delete_removes_structured_data_and_owned_import(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            uploaded = service.upload_protocol_document(
                actor_user_id="user:researcher-a",
                lab_id="lab:demo",
                filename="delete-me.docx",
                data=_docx_bytes(
                    paragraphs=["Timeline", "Day 0 seed.", "Materials"],
                    table_rows=[["Reagent", "Concentration"], ["BMP4", "10 ng/mL"]],
                ),
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            protocol_id = uploaded["protocol"]["protocol_id"]
            service.extract_uploaded_protocol_document(
                actor_user_id="user:researcher-a",
                protocol_id=protocol_id,
            )
            imported = service.imports_for_protocol(protocol_id)[0]
            stored_path = service.import_file_path(str(imported["import_id"]))
            self.assertTrue(stored_path.exists())

            deleted = service.delete_protocol("user:researcher-a", protocol_id)

            self.assertTrue(deleted["deleted"])
            self.assertIsNone(service.get_protocol(protocol_id))
            self.assertFalse(stored_path.exists())
            with self.assertRaisesRegex(ProtocolHubValidationError, "not found"):
                service.delete_protocol("user:researcher-a", protocol_id)

    def test_protocol_reorder_persists_and_normalizes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            first = service.create_blank_protocol("user:researcher-a", "lab:demo", "Protocol A")
            second = service.create_blank_protocol("user:researcher-a", "lab:demo", "Protocol B")
            third = service.create_blank_protocol("user:researcher-a", "lab:demo", "Protocol C")
            fourth = service.create_blank_protocol("user:researcher-a", "lab:demo", "Protocol D")

            moved_to_top = service.reorder_protocols(
                "user:researcher-a",
                [
                    fourth["protocol_id"],
                    first["protocol_id"],
                    second["protocol_id"],
                    third["protocol_id"],
                ],
            )
            moved_down = service.reorder_protocols(
                "user:researcher-a",
                [
                    fourth["protocol_id"],
                    first["protocol_id"],
                    third["protocol_id"],
                    second["protocol_id"],
                ],
            )
            relisted = [
                item
                for item in service.list_protocols()
                if item["protocol_id"]
                in {
                    first["protocol_id"],
                    second["protocol_id"],
                    third["protocol_id"],
                    fourth["protocol_id"],
                }
            ]

        self.assertEqual(
            [item["protocol_id"] for item in moved_to_top],
            [fourth["protocol_id"], first["protocol_id"], second["protocol_id"], third["protocol_id"]],
        )
        self.assertEqual(
            [item["protocol_id"] for item in moved_down],
            [fourth["protocol_id"], first["protocol_id"], third["protocol_id"], second["protocol_id"]],
        )
        self.assertEqual(
            [item["protocol_id"] for item in relisted],
            [fourth["protocol_id"], first["protocol_id"], third["protocol_id"], second["protocol_id"]],
        )
        self.assertEqual([item["sort_index"] for item in moved_down], [1000, 2000, 3000, 4000])

    def test_protocol_reorder_rejects_duplicate_and_unknown_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            protocol = service.create_blank_protocol("user:researcher-a", "lab:demo", "Protocol A")
            with self.assertRaisesRegex(ProtocolHubValidationError, "Duplicate"):
                service.reorder_protocols("user:researcher-a", [protocol["protocol_id"], protocol["protocol_id"]])
            with self.assertRaisesRegex(ProtocolHubValidationError, "Unknown"):
                service.reorder_protocols("user:researcher-a", [protocol["protocol_id"], "protocol:missing"])

    def test_existing_protocol_null_sort_indexes_are_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            protocol = service.create_blank_protocol("user:researcher-a", "lab:demo", "Protocol A")
            with service._connect() as connection:
                connection.execute(
                    "UPDATE protocols_general SET sort_index = NULL WHERE protocol_id = ?",
                    (protocol["protocol_id"],),
                )

            reloaded = self._service(tmpdir)
            listed = [
                item
                for item in reloaded.list_protocols()
                if item["protocol_id"] == protocol["protocol_id"]
            ]

        self.assertIsNotNone(listed[0]["sort_index"])
        self.assertEqual(int(listed[0]["sort_index"]) % 1000, 0)

    def test_image_only_pdf_reports_ocr_required(self) -> None:
        from pypdf import PdfWriter

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "image_only.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            with pdf_path.open("wb") as handle:
                writer.write(handle)
            service = self._service(tmpdir)
            uploaded = service.upload_protocol_document(
                actor_user_id="user:researcher-a",
                lab_id="lab:demo",
                filename="image_only.pdf",
                data=pdf_path.read_bytes(),
                mime_type="application/pdf",
            )
            draft = service.extract_uploaded_protocol_document(
                actor_user_id="user:researcher-a",
                protocol_id=uploaded["protocol"]["protocol_id"],
            )

        self.assertTrue(any("OCR is required" in warning for warning in draft["warnings"]))
        self.assertEqual(draft["extraction_evidence"]["source_document"]["metadata"]["ocr_required"], True)

    def test_csv_extraction_preserves_table_source_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            uploaded = service.upload_protocol_document(
                actor_user_id="user:researcher-a",
                lab_id="lab:demo",
                filename="materials.csv",
                data=b"Material,Concentration\nSAG,300 nM\nDMSO,1x\n",
                mime_type="text/csv",
            )
            draft = service.extract_uploaded_protocol_document(
                actor_user_id="user:researcher-a",
                protocol_id=uploaded["protocol"]["protocol_id"],
            )

        tables = draft["extraction_evidence"]["source_document"]["tables"]
        self.assertEqual(tables[0]["rows"][1], ["SAG", "300 nM"])
        self.assertTrue(any(material["name"] == "SAG" for material in draft["proposed_materials"]))

    def test_protocol_upload_rejects_unsupported_or_oversized_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            with self.assertRaisesRegex(AttachmentStorageError, "Unsupported"):
                service.upload_protocol_document(
                    actor_user_id="user:researcher-a",
                    lab_id="lab:demo",
                    filename="protocol.exe",
                    data=b"not a protocol document",
                    mime_type="application/octet-stream",
                )
            with self.assertRaisesRegex(AttachmentStorageError, "too large"):
                service.upload_protocol_document(
                    actor_user_id="user:researcher-a",
                    lab_id="lab:demo",
                    filename="large.pdf",
                    data=b"0" * (50 * 1024 * 1024 + 1),
                    mime_type="application/pdf",
                )

        storage_dir = Path(tmpdir) / "data" / "attachments"
        self.assertFalse(any(storage_dir.rglob("*.*")) if storage_dir.exists() else False)

    def test_draft_approval_requires_confirmation_and_minimum_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            draft = service.create_extraction_draft_from_text(
                actor_user_id="user:researcher-a",
                lab_id="lab:demo",
                source_text="Treatment protocol. Image on D2.",
                proposed_title="Treatment protocol",
            )
            with self.assertRaisesRegex(ValueError, "confirmation"):
                service.approve_extraction_draft(
                    actor_user_id="user:pi-owner",
                    extraction_id=draft["extraction_id"],
                    version_label="1.0",
                    confirmed=False,
                )
            approved = service.approve_extraction_draft(
                actor_user_id="user:pi-owner",
                extraction_id=draft["extraction_id"],
                version_label="1.0",
                confirmed=True,
            )

        self.assertEqual(approved["draft"]["status"], "approved")
        self.assertEqual(approved["protocol"]["status"], "approved")

    def test_import_draft_can_be_added_as_new_version_without_overwriting_existing_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            protocol = service.get_protocol("protocol:meyer-retinal-organoid-protocol")
            assert protocol is not None
            old_version = protocol["current_version_id"]
            draft = service.create_extraction_draft_from_text(
                actor_user_id="user:researcher-a",
                lab_id="lab:demo",
                source_text="Meyer source update. Image on D35.",
                proposed_title="Meyer retinal organoid protocol",
            )
            approved = service.approve_extraction_draft(
                actor_user_id="user:pi-owner",
                extraction_id=draft["extraction_id"],
                version_label="source-review-1",
                confirmed=True,
                target_protocol_id=protocol["protocol_id"],
            )
            updated = service.get_protocol(protocol["protocol_id"])

        assert updated is not None
        self.assertNotEqual(old_version, updated["current_version_id"])
        self.assertEqual(approved["draft"]["protocol_id"], protocol["protocol_id"])

    def test_meyer_seed_is_incomplete_and_contains_no_invented_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            protocol = service.get_protocol("protocol:meyer-retinal-organoid-protocol")
            assert protocol is not None
            workspace = protocol["workspace"]
            serialized = str(workspace).lower()

        self.assertEqual(protocol["status"], "draft")
        self.assertIn("incomplete internal working draft", serialized)
        self.assertTrue(any(event["title"] == "BMP4" for event in workspace["timeline"]))
        self.assertFalse(workspace["materials"])
        self.assertFalse(workspace["expected_results"])
        self.assertNotIn("demo vendor", serialized)
        self.assertNotIn("vsx2", serialized)
        self.assertNotIn("protocol-defined", serialized)


if __name__ == "__main__":
    unittest.main()
