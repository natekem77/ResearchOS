"""Tests for structured Protocol Hub 2.0."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.general_experiments import GeneralExperimentService
from app.protocol_hub import ProtocolHubService


class ProtocolHubTests(unittest.TestCase):
    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

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


if __name__ == "__main__":
    unittest.main()
