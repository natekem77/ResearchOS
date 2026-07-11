"""Tests for Universal Scientific Object Linking."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.lab_chat import LabChatService
from app.research_objects import ResearchObjectService


class ResearchObjectTests(unittest.TestCase):
    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def test_autocomplete_resolves_protocol_experiment_and_compound(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ResearchObjectService(settings=self._settings(tmpdir))
            bmp4 = service.autocomplete("user:pi-owner", "@BMP4")
            meyer = service.autocomplete("user:pi-owner", "@Meyer")
            experiment = service.resolve_reference("user:pi-owner", "[[NK_Expt_26]]")

        self.assertTrue(bmp4)
        self.assertTrue(any("BMP4" in item["title"] for item in bmp4))
        self.assertTrue(any("Meyer" in item["title"] for item in meyer))
        self.assertTrue(experiment["resolved"])
        self.assertEqual(experiment["object"]["object_type"], "Experiment")

    def test_private_notebook_metadata_is_permission_filtered(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ResearchObjectService(settings=self._settings(tmpdir))
            researcher_results = service.search("user:researcher-a", "Researcher B private notebook")
            owner_results = service.search("user:pi-owner", "Researcher B private notebook")

        self.assertFalse(any(item["object_id"] == "notebook:researcher-b" for item in researcher_results))
        self.assertTrue(any(item["object_id"] == "notebook:researcher-b" for item in owner_results))

    def test_text_references_create_visible_backlinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ResearchObjectService(settings=self._settings(tmpdir))
            resolved = service.resolve_reference("user:researcher-a", "@BMP4")
            assert resolved["object"] is not None
            target_id = resolved["object"]["object_id"]
            created = service.sync_text_references(
                "user:researcher-a",
                source_object_id="notebook:researcher-a",
                source_object_type="Notebook",
                text="Planning note: compare @BMP4 with [[NK_Expt_26]].",
            )
            backlinks = service.backlinks("user:researcher-a", target_id)
            hover = service.hover_card("user:researcher-a", target_id)

        self.assertTrue(created)
        self.assertTrue(any(link["source_object_id"] == "notebook:researcher-a" for link in backlinks))
        self.assertIsNotNone(hover)
        assert hover is not None
        self.assertGreaterEqual(hover["backlink_count"], 1)

    def test_unresolved_reference_is_preserved_as_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ResearchObjectService(settings=self._settings(tmpdir))
            references = service.extract_references_from_text(
                "user:researcher-a",
                "Unknown item @DefinitelyMissingObject should not be invented.",
            )

        self.assertEqual(len(references), 1)
        self.assertFalse(references[0]["resolved"])
        self.assertEqual(references[0]["candidates"], [])

    def test_private_chat_objects_do_not_leak_to_non_members(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            chat = LabChatService(settings=settings)
            message = chat.send_message("user:researcher-a", "chat:private-ab", "Private @SAG note for B only")
            service = ResearchObjectService(settings=settings)
            service.sync_text_references(
                "user:researcher-a",
                source_object_id=message["message_id"],
                source_object_type="Chat Message",
                text="Private @SAG note for B only",
            )
            member_results = service.search("user:researcher-b", "Private SAG note")
            owner_results = service.search("user:pi-owner", "Private SAG note")

        self.assertTrue(any(item["object_type"] == "Chat Message" for item in member_results))
        self.assertFalse(any(item["object_type"] == "Chat Message" for item in owner_results))


if __name__ == "__main__":
    unittest.main()
