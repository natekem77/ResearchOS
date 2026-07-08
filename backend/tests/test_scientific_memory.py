"""Tests for the deterministic Scientific Memory engine."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.experiments import Experiment
from app.research_document import DocumentChunk, ResearchDocument
from app.scientific_memory import ScientificMemoryService
from app.storage import SQLiteStore


class ScientificMemoryTests(unittest.TestCase):
    """Scientific Memory should rank experiments by shared scientific features."""

    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def _document(self, document_id: str, title: str, content: str) -> ResearchDocument:
        return ResearchDocument(
            id=document_id,
            provider="markdown",
            source_id=f"{document_id}.md",
            title=title,
            content=content,
            metadata={"entities": {"compound": ["SAG"], "marker": ["SIX6", "BRN3B"]}},
        )

    def _seed(self, store: SQLiteStore) -> None:
        documents = [
            self._document("doc:target", "NK Expt 31 SAG rescue", "SAG GRKi SIX6 BRN3B D32 retinal organoid rescue."),
            self._document("doc:similar", "NK Expt 32 SAG repeat", "SAG GRKi SIX6 BRN3B D32 retinal organoid repeat."),
            self._document("doc:different", "BMP4 pulse", "BMP4 D12 RAX VSX2 protocol timing."),
        ]
        for document in documents:
            store.upsert_document(
                document,
                [DocumentChunk(id=f"chunk:{document.id}", document_id=document.id, chunk_index=0, text=document.content, token_estimate=20)],
            )
        store.upsert_experiment(
            Experiment(
                id="experiment:target",
                source_document_id="doc:target",
                source_provider="markdown",
                title="NK Expt 31 SAG rescue",
                experiment_id="NK_Expt_31",
                cell_line="SIX6 reporter iPSC",
                organoid_batch="RO-31",
                compounds=["SAG"],
                treatments=["SAG + GRKi"],
                time_points=["D32"],
                markers=["SIX6", "BRN3B"],
                imaging_methods=["confocal"],
                conclusions="BRN3B increased after SAG rescue.",
            )
        )
        store.upsert_experiment(
            Experiment(
                id="experiment:similar",
                source_document_id="doc:similar",
                source_provider="markdown",
                title="NK Expt 32 SAG repeat",
                experiment_id="NK_Expt_32",
                cell_line="SIX6 reporter iPSC",
                organoid_batch="RO-32",
                compounds=["SAG"],
                treatments=["SAG + GRKi"],
                time_points=["D32"],
                markers=["SIX6", "BRN3B"],
                imaging_methods=["confocal"],
            )
        )
        store.upsert_experiment(
            Experiment(
                id="experiment:different",
                source_document_id="doc:different",
                source_provider="markdown",
                title="BMP4 pulse",
                experiment_id="BMP4-1",
                cell_line="RAX reporter iPSC",
                organoid_batch="RO-BMP4",
                compounds=["BMP4"],
                treatments=["BMP4 pulse"],
                time_points=["D12"],
                markers=["RAX", "VSX2"],
            )
        )
        store.register_asset(
            asset_id="asset:stats",
            asset_type="spreadsheet",
            experiment_id="NK_Expt_31",
            title="NK Expt 31 statistics",
            filename="NK_Expt_31_stats.csv",
            provider="spreadsheet",
            path="/tmp/NK_Expt_31_stats.csv",
            metadata={"statistics": {"variables": ["SIX6", "BRN3B"]}, "markers": ["SIX6", "BRN3B"]},
        )

    def test_similarity_ranking_prefers_shared_scientific_features(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)

            service = ScientificMemoryService(settings=settings, store=store)
            similar = service.find_similar_experiments("experiment:target", limit=2)

        self.assertEqual(similar[0]["experiment"]["id"], "experiment:similar")
        self.assertGreater(similar[0]["similarity_score"], similar[1]["similarity_score"])
        self.assertTrue(similar[0]["key_similarities"])
        self.assertTrue(similar[0]["important_differences"])

    def test_memory_payload_includes_vectors_and_related_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)

            service = ScientificMemoryService(settings=settings, store=store)
            payload = service.similar_payload("experiment:target")

        self.assertIn("memory_vector", payload["memory"])
        self.assertIn("feature_vector", payload["memory"])
        self.assertIn("similarity_vector", payload["memory"])
        self.assertTrue(payload["related_statistics"])

    def test_missing_experiment_raises_lookup_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            service = ScientificMemoryService(settings=settings, store=SQLiteStore(settings=settings))

            with self.assertRaises(LookupError):
                service.experiment_memory("missing")


if __name__ == "__main__":
    unittest.main()
