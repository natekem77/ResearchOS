"""Tests for the provider-agnostic global knowledge graph."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from app.config import Settings
from app.experiments import Experiment
from app.global_knowledge_graph import KnowledgeGraphService
from app.research_document import DocumentChunk, ResearchDocument
from app.storage import SQLiteStore


class GlobalKnowledgeGraphTests(unittest.TestCase):
    """The graph should merge entities and relate every provider output."""

    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def _seed_researchos_graph(self, store: SQLiteStore) -> None:
        notebook = ResearchDocument(
            id="doc:notebook",
            provider="markdown",
            source_id="notebook.md",
            title="SAG rescue notebook",
            content="SAG rescue experiment with SIX6 and BRN3B readouts.",
            metadata={
                "entities": {"compound": ["SAG"], "marker": ["SIX6", "BRN3B"]},
                "aliases": {"SAG": ["Smoothened agonist"]},
            },
        )
        literature = ResearchDocument(
            id="doc:paper",
            provider="literature",
            source_id="paper.txt",
            title="Published SAG and SIX6 retinal differentiation paper",
            content="Literature links SAG with SIX6 and BRN3B outcomes.",
            metadata={
                "entities": {"compounds": ["sag"], "genes": ["SIX6"], "markers": ["BRN3B"]},
                "year": "2026",
            },
        )
        for document in [notebook, literature]:
            store.upsert_document(
                document,
                [
                    DocumentChunk(
                        id=f"chunk:{document.id}",
                        document_id=document.id,
                        chunk_index=0,
                        text=document.content,
                        token_estimate=20,
                    )
                ],
            )

        store.upsert_experiment(
            Experiment(
                id="experiment:1",
                source_document_id="doc:notebook",
                source_provider="markdown",
                title="NK Expt 31 SAG rescue",
                experiment_id="NK_Expt_31",
                cell_line="SIX6 reporter iPSC",
                organoid_batch="RO-NK-31",
                compounds=["sag"],
                treatments=["SAG + GRKi"],
                markers=["six6", "BRN3B"],
                antibodies=["anti-BRN3B"],
            )
        )

        store.register_asset(
            asset_id="asset:image",
            asset_type="microscopy",
            experiment_id="NK_Expt_31",
            title="SIX6 BRN3B image",
            filename="NK_Expt_31_D32_SIX6_BRN3B.tif",
            provider="microscopy",
            path="samples/images/NK_Expt_31_D32_SIX6_BRN3B.tif",
            metadata={"markers": ["SIX6", "BRN3B"], "timepoint": "D32"},
        )
        store.register_asset(
            asset_id="asset:graphpad",
            asset_type="spreadsheet",
            experiment_id="NK_Expt_31",
            title="GraphPad statistics",
            filename="NK_Expt_31_SIX6_BRN3B_stats.csv",
            provider="graphpad",
            path="samples/graphpad/NK_Expt_31_SIX6_BRN3B_stats.csv",
            metadata={
                "statistics": {
                    "variables": ["SIX6", "BRN3B"],
                    "group_names": ["DMSO", "SAG"],
                    "statistical_tests": ["one-way ANOVA"],
                    "rows": [
                        {
                            "variable": "SIX6",
                            "group": "SAG",
                            "comparison": "DMSO vs SAG",
                            "mean": 45.6,
                            "n": 3,
                            "p_value": 0.006,
                            "test": "one-way ANOVA",
                        }
                    ],
                }
            },
        )
        store.register_asset(
            asset_id="asset:spreadsheet",
            asset_type="spreadsheet",
            experiment_id="NK_Expt_31",
            title="Generic spreadsheet",
            filename="NK_Expt_31_quant.csv",
            provider="spreadsheet",
            path="samples/spreadsheets/NK_Expt_31_quant.csv",
            metadata={
                "entities": {
                    "markers": ["SIX6"],
                    "treatments": ["Smoothened agonist"],
                    "unknown_scientific_terms": ["RescueIndex"],
                }
            },
        )
        store.save_pending_entry(
            title="Pending SAG notebook entry",
            experiment_id="NK_Expt_31",
            template="retinal_organoid",
            structured={"treatments": ["SAG"], "markers": ["SIX6"]},
            markdown="# Pending SAG notebook entry",
        )

    def test_merges_duplicates_case_and_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(settings=self._settings(tmpdir))
            self._seed_researchos_graph(store)
            service = KnowledgeGraphService(settings=self._settings(tmpdir), store=store)

            sag = service.entity_detail("Smoothened agonist")
            six6 = service.find_entity_case_insensitive("six6")

        self.assertIsNotNone(sag)
        assert sag is not None
        self.assertEqual(sag["entity"], "SAG")
        self.assertEqual(sag["entity_type"], "compound")
        self.assertGreaterEqual(sag["relationship_counts"]["experiment"], 1)
        self.assertIsNotNone(six6)
        self.assertEqual(six6["entity"], "SIX6")

    def test_entity_detail_includes_every_provider_relationship(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(settings=self._settings(tmpdir))
            self._seed_researchos_graph(store)
            service = KnowledgeGraphService(settings=self._settings(tmpdir), store=store)

            six6 = service.entity_detail("SIX6")

        self.assertIsNotNone(six6)
        assert six6 is not None
        self.assertTrue(six6["experiments"])
        self.assertTrue(six6["notebook_entries"])
        self.assertTrue(six6["literature"])
        self.assertTrue(six6["microscopy_assets"])
        self.assertTrue(six6["graphpad_assets"])
        self.assertTrue(six6["spreadsheet_assets"])
        self.assertTrue(six6["statistics"])
        related_names = {item["entity"] for item in six6["related_entities"]}
        self.assertIn("BRN3B", related_names)

    def test_search_type_and_unknown_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(settings=self._settings(tmpdir))
            self._seed_researchos_graph(store)
            service = KnowledgeGraphService(settings=self._settings(tmpdir), store=store)

            search = service.search("six")
            markers = service.entities_by_type("marker")
            unknown = service.find_entity("not-present")

        self.assertEqual(search[0]["entity"], "SIX6")
        self.assertIn("SIX6", {item["entity"] for item in markers})
        self.assertIsNone(unknown)

    def test_experiment_neighborhood(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(settings=self._settings(tmpdir))
            self._seed_researchos_graph(store)
            service = KnowledgeGraphService(settings=self._settings(tmpdir), store=store)

            neighborhood = service.experiment_neighborhood("NK_Expt_31")

        self.assertIsNotNone(neighborhood)
        assert neighborhood is not None
        self.assertEqual(neighborhood["experiment"]["experiment_id"], "NK_Expt_31")
        self.assertTrue(neighborhood["notebook"])
        self.assertTrue(neighborhood["images"])
        self.assertTrue(neighborhood["graphpad"])
        self.assertTrue(neighborhood["statistics"])
        self.assertTrue(neighborhood["spreadsheets"])
        self.assertIn("SIX6", neighborhood["markers"])

    def test_refresh_and_cache_invalidation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            service = KnowledgeGraphService(settings=settings, store=store)
            self.assertEqual(service.summary()["entity_count"], 0)

            store.upsert_document(
                ResearchDocument(
                    id="doc:bmp4",
                    provider="markdown",
                    source_id="bmp4.md",
                    title="BMP4 note",
                    content="BMP4 pulse.",
                    metadata={"entities": {"compound": ["BMP4"]}},
                ),
                [DocumentChunk(id="chunk:bmp4", document_id="doc:bmp4", chunk_index=0, text="BMP4", token_estimate=1)],
            )
            time.sleep(0.002)
            service.refresh()
            refreshed = service.summary()
            bmp4 = service.find_entity("bmp4")

        self.assertGreaterEqual(refreshed["entity_count"], 1)
        self.assertIsNotNone(bmp4)

    def test_large_synthetic_graph_builds_quickly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            for index in range(250):
                term = f"GENE{index % 20}"
                store.upsert_document(
                    ResearchDocument(
                        id=f"doc:{index}",
                        provider="markdown",
                        source_id=f"{index}.md",
                        title=f"Synthetic note {index}",
                        content=f"{term} synthetic evidence",
                        metadata={"entities": {"gene": [term], "sample": [f"SAMPLE{index}"]}},
                    ),
                    [
                        DocumentChunk(
                            id=f"chunk:{index}",
                            document_id=f"doc:{index}",
                            chunk_index=0,
                            text=term,
                            token_estimate=1,
                        )
                    ],
                )

            service = KnowledgeGraphService(settings=settings, store=store)
            started = time.perf_counter()
            summary = service.summary()
            elapsed = time.perf_counter() - started

        self.assertGreaterEqual(summary["entity_count"], 270)
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
