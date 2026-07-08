"""Tests for Overnight Intelligence Morning Briefs."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.experiments import Experiment
from app.overnight_intelligence import OvernightIntelligenceService
from app.research_document import DocumentChunk, ResearchDocument
from app.storage import SQLiteStore


class OvernightIntelligenceTests(unittest.TestCase):
    """Morning Brief should summarize real updates with provenance."""

    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def _seed(self, store: SQLiteStore) -> None:
        doc = ResearchDocument(
            id="doc:overnight",
            provider="markdown",
            source_id="overnight.md",
            title="Overnight SAG note",
            content="NK_Expt_84 used SAG and SIX6.",
        )
        store.upsert_document(
            doc,
            [DocumentChunk(id="chunk:overnight", document_id=doc.id, chunk_index=0, text=doc.content, token_estimate=8)],
        )
        store.upsert_experiment(
            Experiment(
                id="experiment:overnight",
                source_document_id=doc.id,
                source_provider="markdown",
                title="Overnight SAG experiment",
                experiment_id="NK_Expt_84",
                compounds=["SAG"],
                markers=["SIX6"],
            )
        )
        store.upsert_document(
            ResearchDocument(
                id="paper:overnight",
                provider="literature",
                source_id="paper.md",
                title="Overnight literature",
                content="Literature context.",
            ),
            [DocumentChunk(id="chunk:overnight-paper", document_id="paper:overnight", chunk_index=0, text="Literature context.", token_estimate=3)],
        )
        store.save_resource(resource_type="compound", name="SAG")

    def test_today_brief_has_sections_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)
            brief = OvernightIntelligenceService(settings=settings, store=store).morning_brief(period="today")

        self.assertGreater(brief["total_items"], 0)
        self.assertTrue(brief["sections"]["new_experiments"])
        self.assertTrue(brief["sections"]["new_literature"])
        self.assertTrue(brief["sections"]["resource_alerts"])
        for section_items in brief["sections"].values():
            for item in section_items:
                self.assertTrue(item["provenance"])

    def test_yesterday_brief_can_be_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)
            brief = OvernightIntelligenceService(settings=settings, store=store).morning_brief(period="yesterday")

        self.assertEqual(brief["total_items"], 0)
        self.assertIn("No observed ResearchOS changes", brief["summary"])

    def test_last_week_includes_multiple_provider_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)
            store.register_asset(
                asset_id="asset:overnight-stats",
                asset_type="graphpad",
                experiment_id="NK_Expt_84",
                title="Overnight stats",
                filename="overnight.csv",
                provider="graphpad",
                path="samples/graphpad/overnight.csv",
                metadata={"statistics": {"rows": [{"variable": "SIX6", "group": "SAG", "mean": 2.0, "n": 3, "p_value": 0.04}]}},
            )
            brief = OvernightIntelligenceService(settings=settings, store=store).morning_brief(period="last_week")

        self.assertTrue(brief["sections"]["new_experiments"])
        self.assertTrue(brief["sections"]["knowledge_graph_changes"])
        self.assertTrue(brief["sections"]["suggested_priorities"])


if __name__ == "__main__":
    unittest.main()
