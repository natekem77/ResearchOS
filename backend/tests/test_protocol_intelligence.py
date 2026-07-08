"""Tests for read-only protocol intelligence."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.experiments import Experiment
from app.protocol_intelligence import ProtocolService
from app.research_document import DocumentChunk, ResearchDocument
from app.storage import SQLiteStore


class ProtocolIntelligenceTests(unittest.TestCase):
    """Protocols should become first-class objects without editing sources."""

    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def _seed(self, store: SQLiteStore) -> None:
        protocol_v1 = ResearchDocument(
            id="doc:protocol-v1",
            provider="markdown",
            source_id="bmp4_protocol_v1.md",
            title="BMP4 differentiation protocol v1",
            content=(
                "# BMP4 differentiation protocol v1\n"
                "Use BMP4 at 10 ng/mL from D0 to D3 with DMSO control.\n"
                "Readouts include SIX6 and BRN3B immunostaining."
            ),
            metadata={"document_type": "protocol"},
            updated_at="2026-01-01",
        )
        protocol_v2 = ResearchDocument(
            id="doc:protocol-v2",
            provider="markdown",
            source_id="bmp4_protocol_v2.md",
            title="BMP4 differentiation protocol v2",
            content=(
                "# BMP4 differentiation protocol v2\n"
                "Use BMP4 at 20 ng/mL from D0 to D2 with DMSO control.\n"
                "Add explicit wash steps and quantify SIX6 and BRN3B immunostaining."
            ),
            metadata={"document_type": "protocol"},
            updated_at="2026-02-01",
        )
        literature = ResearchDocument(
            id="doc:literature",
            provider="literature",
            source_id="bmp4-paper.txt",
            title="BMP4 timing in retinal differentiation",
            content="BMP4 timing can affect retinal organoid differentiation and SIX6 readouts.",
            metadata={"entities": {"compound": ["BMP4"], "marker": ["SIX6"]}},
        )
        for document in [protocol_v1, protocol_v2, literature]:
            store.upsert_document(
                document,
                [DocumentChunk(id=f"chunk:{document.id}", document_id=document.id, chunk_index=0, text=document.content, token_estimate=20)],
            )
        store.upsert_experiment(
            Experiment(
                id="experiment:bmp4",
                source_document_id="doc:protocol-v2",
                source_provider="markdown",
                title="BMP4 pulse differentiation",
                experiment_id="BMP4-EXP-1",
                compounds=["BMP4"],
                treatments=["D0-D2 BMP4"],
                markers=["SIX6", "BRN3B"],
                notes="BMP4 protocol produced increased SIX6 signal.",
                conclusions="BMP4 timing improved retinal differentiation readouts.",
            )
        )
        store.upsert_experiment(
            Experiment(
                id="experiment:concern",
                source_document_id="doc:other",
                source_provider="markdown",
                title="BMP4 weak staining follow-up",
                experiment_id="BMP4-EXP-2",
                compounds=["BMP4"],
                markers=["BRN3B"],
                notes="BMP4 protocol had weak BRN3B staining and background issue.",
                conclusions="Concern requires protocol review.",
            )
        )
        store.register_asset(
            asset_id="asset:bmp4-stats",
            asset_type="spreadsheet",
            experiment_id="BMP4-EXP-1",
            title="BMP4 statistics",
            filename="bmp4_stats.csv",
            provider="graphpad",
            path="samples/graphpad/bmp4_stats.csv",
            metadata={"statistics": {"variables": ["SIX6"], "rows": [{"p_value": 0.02}]}},
        )

    def test_protocols_are_detected_and_linked_to_experiments(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)
            service = ProtocolService(settings=settings, store=store)
            protocols = service.list_protocols()

        self.assertEqual(len(protocols), 2)
        self.assertTrue(all(protocol["id"].startswith("protocol:") for protocol in protocols))
        self.assertTrue(any(protocol["linked_experiment_count"] >= 1 for protocol in protocols))
        self.assertTrue(all("success_metrics" in protocol for protocol in protocols))

    def test_protocol_workspace_contains_history_metrics_and_copilot_guardrail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)
            service = ProtocolService(settings=settings, store=store)
            protocol_id = service.list_protocols()[0]["id"]
            workspace = service.get_protocol(protocol_id)

        self.assertIsNotNone(workspace)
        assert workspace is not None
        self.assertGreaterEqual(len(workspace["history"]), 2)
        self.assertGreaterEqual(workspace["usage_statistics"]["experiment_count"], 1)
        self.assertGreaterEqual(workspace["success_metrics"]["positive_outcome_count"], 1)
        self.assertIn("never automatically edits", workspace["research_copilot"]["guardrail"])
        self.assertTrue(workspace["timeline"])

    def test_protocol_comparison_detects_version_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)
            service = ProtocolService(settings=settings, store=store)
            protocols = sorted(service.list_protocols(), key=lambda item: item["version"])
            comparison = service.compare(protocols[0]["id"], protocols[1]["id"])

        self.assertIsNotNone(comparison)
        assert comparison is not None
        self.assertTrue(comparison["summary"]["changed"])
        self.assertGreater(comparison["summary"]["added_count"], 0)
        self.assertTrue(any("wash" in line.lower() for line in comparison["changes"]["added"]))

    def test_unknown_protocol_returns_empty_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ProtocolService(settings=self._settings(tmpdir))
            self.assertEqual(service.list_protocols(), [])
            self.assertIsNone(service.get_protocol("protocol:missing"))
            self.assertEqual(service.history("protocol:missing"), [])
            self.assertIsNone(service.compare("protocol:missing", "protocol:other"))


if __name__ == "__main__":
    unittest.main()
