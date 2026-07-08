"""Tests for the Laboratory Intelligence feed."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.experiments import Experiment
from app.lab_intelligence import LaboratoryIntelligenceService
from app.research_document import DocumentChunk, ResearchDocument
from app.storage import SQLiteStore


class LaboratoryIntelligenceTests(unittest.TestCase):
    """The feed should surface provenance-backed lab attention items."""

    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def _seed(self, store: SQLiteStore) -> None:
        document = ResearchDocument(
            id="doc:intelligence",
            provider="markdown",
            source_id="intelligence.md",
            title="NK_Expt_83 SAG notebook",
            content="NK_Expt_83 used SAG and measured SIX6.",
            metadata={"entities": {"compound": ["SAG"], "marker": ["SIX6"]}},
        )
        store.upsert_document(
            document,
            [
                DocumentChunk(
                    id="chunk:intelligence",
                    document_id=document.id,
                    chunk_index=0,
                    text=document.content,
                    token_estimate=10,
                )
            ],
        )
        store.upsert_experiment(
            Experiment(
                id="experiment:intelligence",
                source_document_id=document.id,
                source_provider="markdown",
                title="SAG intelligence experiment",
                experiment_id="NK_Expt_83",
                compounds=["SAG"],
                markers=["SIX6"],
            )
        )
        store.register_asset(
            asset_id="asset:stats",
            asset_type="graphpad",
            experiment_id="NK_Expt_83",
            title="NK_Expt_83 GraphPad statistics",
            filename="NK_Expt_83_stats.csv",
            provider="graphpad",
            path="samples/graphpad/NK_Expt_83_stats.csv",
            metadata={
                "statistics": {
                    "rows": [
                        {
                            "variable": "SIX6 fluorescence",
                            "group": "SAG",
                            "comparison": "DMSO vs SAG",
                            "mean": 45.6,
                            "sem": 2.1,
                            "n": 3,
                            "p_value": 0.006,
                            "test": "one-way ANOVA with Tukey correction",
                        }
                    ]
                }
            },
        )
        store.upsert_document(
            ResearchDocument(
                id="paper:intelligence",
                provider="literature",
                source_id="paper.md",
                title="SAG literature note",
                content="Published SAG retinal differentiation context.",
            ),
            [
                DocumentChunk(
                    id="chunk:paper-intelligence",
                    document_id="paper:intelligence",
                    chunk_index=0,
                    text="SAG literature context.",
                    token_estimate=4,
                )
            ],
        )
        store.save_resource(resource_type="compound", name="SAG")

    def test_feed_generation_priorities_and_provider_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)
            feed = LaboratoryIntelligenceService(settings=settings, store=store).build_feed(limit=50)

        item_types = {item["item_type"] for item in feed["items"]}
        self.assertIn("Experiment Reminder", item_types)
        self.assertIn("Statistical Finding", item_types)
        self.assertIn("New Literature", item_types)
        self.assertIn("Resource Warning", item_types)
        self.assertTrue(all(item["provenance"] for item in feed["items"]))

    def test_filtering_dismiss_and_pin_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)
            service = LaboratoryIntelligenceService(settings=settings, store=store)
            stats_feed = service.build_feed(item_type="Statistical Finding")
            first = stats_feed["items"][0]
            item_id = str(first["item_id"])
            service.set_item_state(item_id, pinned=True)
            pinned_feed = service.build_feed(limit=10)
            service.set_item_state(item_id, dismissed=True)
            visible_feed = service.build_feed(limit=50)
            dismissed_feed = service.build_feed(include_dismissed=True, limit=50)

        self.assertTrue(all(item["item_type"] == "Statistical Finding" for item in stats_feed["items"]))
        self.assertEqual(pinned_feed["items"][0]["item_id"], item_id)
        self.assertNotIn(item_id, {item["item_id"] for item in visible_feed["items"]})
        self.assertIn(item_id, {item["item_id"] for item in dismissed_feed["items"]})


if __name__ == "__main__":
    unittest.main()
