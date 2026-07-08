"""Tests for deterministic Scientific Evidence Engine."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.evidence_engine import EvidenceEngine
from app.experiments import Experiment
from app.research_document import DocumentChunk, ResearchDocument
from app.storage import SQLiteStore


class EvidenceEngineTests(unittest.TestCase):
    """Evidence synthesis must stay provenance-backed and conservative."""

    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def _seed(self, store: SQLiteStore) -> None:
        notebook = ResearchDocument(
            id="doc:sag",
            provider="markdown",
            source_id="sag.md",
            title="SAG notebook",
            content="SAG improved SIX6 staining in retinal organoids.",
            metadata={"entities": {"compound": ["SAG"], "marker": ["SIX6"]}},
        )
        literature = ResearchDocument(
            id="doc:lit",
            provider="literature",
            source_id="paper.txt",
            title="SAG retinal differentiation literature",
            content="Published report links SAG with retinal differentiation markers.",
            metadata={"entities": {"compound": ["SAG"], "marker": ["SIX6"]}},
        )
        for document in [notebook, literature]:
            store.upsert_document(
                document,
                [DocumentChunk(id=f"chunk:{document.id}", document_id=document.id, chunk_index=0, text=document.content, token_estimate=20)],
            )
        store.upsert_experiment(
            Experiment(
                id="experiment:sag-support",
                source_document_id="doc:sag",
                source_provider="markdown",
                title="SAG support experiment",
                experiment_id="NK_Expt_31",
                compounds=["SAG"],
                markers=["SIX6"],
                conclusions="SAG condition increased SIX6-positive retinal differentiation readout.",
            )
        )
        store.upsert_experiment(
            Experiment(
                id="experiment:sag-conflict",
                source_document_id="doc:sag",
                source_provider="markdown",
                title="SAG non-significant replicate",
                experiment_id="NK_Expt_32",
                compounds=["SAG"],
                markers=["SIX6"],
                conclusions="SAG showed no improvement in this replicate.",
            )
        )
        store.register_asset(
            asset_id="asset:stats-support",
            asset_type="spreadsheet",
            experiment_id="NK_Expt_31",
            title="SAG SIX6 statistics",
            filename="sag_stats.csv",
            provider="graphpad",
            path="samples/graphpad/sag_stats.csv",
            metadata={"statistics": {"variables": ["SIX6"], "rows": [{"comparison": "DMSO vs SAG", "p_value": 0.006}]}},
        )
        store.register_asset(
            asset_id="asset:stats-conflict",
            asset_type="spreadsheet",
            experiment_id="NK_Expt_32",
            title="SAG replicate statistics",
            filename="sag_replicate.csv",
            provider="graphpad",
            path="samples/graphpad/sag_replicate.csv",
            metadata={"statistics": {"variables": ["SIX6"], "rows": [{"comparison": "DMSO vs SAG", "p_value": 0.42}]}},
        )

    def test_supporting_contradictory_confidence_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)
            summary = EvidenceEngine(settings=settings, store=store).query("Does early SAG improve retinal differentiation?")

        payload = summary.as_dict()
        self.assertTrue(payload["supporting_evidence"])
        self.assertTrue(payload["contradictory_evidence"])
        self.assertTrue(payload["provenance"])
        self.assertGreater(payload["confidence"]["factors"]["experiment_count"], 0)
        self.assertGreater(payload["confidence"]["factors"]["statistical_support_count"], 0)
        self.assertIn(payload["confidence"]["level"], {"low", "moderate", "moderate-high"})

    def test_missing_evidence_when_no_providers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            summary = EvidenceEngine(settings=settings, store=store).query("Does SAG improve retinal differentiation?")

        payload = summary.as_dict()
        self.assertEqual(payload["confidence"]["level"], "insufficient")
        self.assertTrue(payload["missing_evidence"])
        self.assertEqual(payload["related_experiments"], [])
        self.assertIn("No Knowledge Graph entities", payload["summary"])


if __name__ == "__main__":
    unittest.main()
