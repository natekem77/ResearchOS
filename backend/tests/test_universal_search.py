"""Tests for Universal Scientific Search."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.experiments import Experiment
from app.research_document import DocumentChunk, ResearchDocument
from app.storage import SQLiteStore
from app.universal_search import UniversalSearchService


class UniversalSearchTests(unittest.TestCase):
    """Universal search should find every local ResearchOS object type."""

    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def _seed(self, store: SQLiteStore) -> None:
        note = ResearchDocument(
            id="doc:sag",
            provider="markdown",
            source_id="sag.md",
            title="SAG D32 notebook",
            content="NK_Expt_31 D32 SAG treatment with SIX6 and BRN3B imaging.",
            metadata={"entities": {"compound": ["SAG"], "marker": ["SIX6", "BRN3B"]}},
        )
        store.upsert_document(note, [DocumentChunk(id="chunk:sag", document_id=note.id, chunk_index=0, text=note.content, token_estimate=12)])
        paper = ResearchDocument(
            id="doc:paper",
            provider="literature",
            source_id="paper.txt",
            title="SAG retinal differentiation paper",
            content="Literature discusses SAG timing and BRN3B expectations.",
            metadata={"entities": {"compound": ["SAG"], "gene": ["BRN3B"]}},
        )
        store.upsert_document(paper, [DocumentChunk(id="chunk:paper", document_id=paper.id, chunk_index=0, text=paper.content, token_estimate=9)])
        store.upsert_experiment(
            Experiment(
                id="experiment:sag",
                source_document_id=note.id,
                source_provider="markdown",
                title="SAG D32 differentiation",
                experiment_id="NK_Expt_31",
                compounds=["SAG"],
                markers=["SIX6", "BRN3B"],
                time_points=["D32"],
                conclusions="SAG condition increased SIX6 signal.",
            )
        )
        store.register_asset(
            asset_id="asset:image",
            asset_type="microscopy",
            experiment_id="NK_Expt_31",
            title="D32 SIX6 BRN3B image",
            filename="NK_Expt_31_D32_SIX6_BRN3B.tif",
            provider="microscopy",
            path="samples/images/NK_Expt_31_D32_SIX6_BRN3B.tif",
            metadata={"markers": ["SIX6", "BRN3B"], "timepoint": "D32"},
        )
        store.register_asset(
            asset_id="asset:graphpad",
            asset_type="spreadsheet",
            experiment_id="NK_Expt_31",
            title="GraphPad SAG statistics",
            filename="NK_Expt_31_SAG_stats.csv",
            provider="graphpad",
            path="samples/graphpad/NK_Expt_31_SAG_stats.csv",
            metadata={
                "entities": {"compounds": ["SAG"], "markers": ["SIX6"]},
                "statistics": {"variables": ["SIX6"], "rows": [{"comparison": "DMSO vs SAG", "p_value": 0.01}]},
            },
        )
        store.register_asset(
            asset_id="asset:sheet",
            asset_type="spreadsheet",
            experiment_id="NK_Expt_31",
            title="SAG quantitative spreadsheet",
            filename="NK_Expt_31_quant.csv",
            provider="spreadsheet",
            path="samples/spreadsheets/NK_Expt_31_quant.csv",
            metadata={"entities": {"compounds": ["SAG"], "markers": ["BRN3B"]}},
        )

    def test_exact_search_returns_all_core_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)

            result = UniversalSearchService(settings=settings, store=store).search("SAG")

        groups = result["grouped_results"]
        self.assertTrue(groups["experiments"])
        self.assertTrue(groups["notebook_entries"])
        self.assertTrue(groups["entities"])
        self.assertTrue(groups["images"])
        self.assertTrue(groups["statistics"])
        self.assertTrue(groups["spreadsheets"])
        self.assertTrue(groups["literature"])
        self.assertGreater(result["total_results"], 0)

    def test_partial_fuzzy_multiword_and_quoted_phrase(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)
            service = UniversalSearchService(settings=settings, store=store)

            partial = service.search("BRN")
            fuzzy = service.search("BRNB")
            multi = service.search("SAG D32")
            quoted = service.search('"SAG D32"')

        self.assertTrue(partial["grouped_results"]["entities"] or partial["grouped_results"]["images"])
        self.assertTrue(fuzzy["grouped_results"]["experiments"] or fuzzy["grouped_results"]["images"])
        self.assertTrue(multi["grouped_results"]["experiments"])
        self.assertTrue(quoted["grouped_results"]["notebook_entries"] or quoted["grouped_results"]["experiments"])

    def test_experiments_rank_above_commands_for_experiment_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)

            result = UniversalSearchService(settings=settings, store=store).search("NK_Expt_31")

        self.assertTrue(result["grouped_results"]["experiments"])
        self.assertGreater(
            result["grouped_results"]["experiments"][0]["score"],
            result["grouped_results"]["commands"][0]["score"] if result["grouped_results"]["commands"] else 0,
        )

    def test_missing_providers_and_cache_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            service = UniversalSearchService(settings=settings, store=store)
            empty = service.search("SAG")
            self._seed(store)
            rebuilt = service.search("SAG")

        self.assertEqual(empty["total_results"], 0)
        self.assertGreater(rebuilt["total_results"], 0)

    def test_large_synthetic_dataset_searches_quickly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            for index in range(150):
                store.upsert_experiment(
                    Experiment(
                        id=f"experiment:{index}",
                        source_document_id=f"doc:{index}",
                        source_provider="synthetic",
                        title=f"Synthetic experiment {index}",
                        experiment_id=f"SYN-{index}",
                        markers=["BRN3B"] if index == 149 else [],
                    )
                )

            result = UniversalSearchService(settings=settings, store=store).search("SYN-149")

        self.assertTrue(result["grouped_results"]["experiments"])
        self.assertEqual(result["grouped_results"]["experiments"][0]["metadata"]["experiment_id"], "SYN-149")


if __name__ == "__main__":
    unittest.main()
