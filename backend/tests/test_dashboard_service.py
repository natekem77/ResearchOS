"""Tests for the ResearchOS Daily Dashboard service."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.dashboard_service import DashboardService
from app.experiments import Experiment
from app.research_document import DocumentChunk, ResearchDocument
from app.storage import SQLiteStore


class FakeDashboardAI:
    """Fake chat provider for dashboard AI-enabled tests."""

    provider_name = "fake-dashboard-ai"

    def chat(self, message: str, context: str | None = None) -> str:
        return "AI summary based only on dashboard JSON."


class DashboardServiceTests(unittest.TestCase):
    """Daily dashboard should summarize local evidence without hallucination."""

    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def _seed(self, store: SQLiteStore, count: int = 2) -> None:
        document = ResearchDocument(
            id="doc:dashboard",
            provider="markdown",
            source_id="dashboard.md",
            title="Dashboard SAG note",
            content="NK_Expt_31 used SAG with SIX6 readout.",
            metadata={"entities": {"compound": ["SAG"], "marker": ["SIX6"]}},
        )
        store.upsert_document(document, [DocumentChunk(id="chunk:dashboard", document_id=document.id, chunk_index=0, text=document.content, token_estimate=8)])
        literature = ResearchDocument(
            id="doc:lit",
            provider="literature",
            source_id="paper.txt",
            title="SAG literature",
            content="SAG retinal literature.",
            metadata={"entities": {"compound": ["SAG"]}},
        )
        store.upsert_document(literature, [DocumentChunk(id="chunk:lit", document_id=literature.id, chunk_index=0, text=literature.content, token_estimate=4)])
        for index in range(count):
            store.upsert_experiment(
                Experiment(
                    id=f"experiment:{index}",
                    source_document_id=document.id,
                    source_provider="markdown",
                    title=f"SAG experiment {index}",
                    experiment_id=f"NK_Expt_{31 + index}",
                    compounds=["SAG"],
                    markers=["SIX6"] if index == 0 else [],
                    conclusions="SAG increased SIX6 signal." if index == 0 else "",
                )
            )
        store.register_asset(
            asset_id="asset:stats",
            asset_type="spreadsheet",
            experiment_id="NK_Expt_31",
            title="SAG stats",
            filename="stats.csv",
            provider="graphpad",
            path="samples/graphpad/stats.csv",
            metadata={"statistics": {"variables": ["SIX6"], "rows": [{"p_value": 0.01}]}},
        )

    def test_dashboard_generation_with_no_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = DashboardService(settings=self._settings(tmpdir))
            dashboard = service.build(use_ai=False)

        self.assertEqual(dashboard["assistant_summary"]["provider"], "local-fallback")
        self.assertEqual(len(dashboard["sections"]), 13)
        self.assertTrue(dashboard["layout"]["supports_collapse"])
        self.assertTrue(dashboard["layout"]["supports_reorder"])
        self.assertEqual(dashboard["layout"]["mobile"]["columns"], 1)

    def test_dashboard_generation_with_sample_data_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)
            dashboard = DashboardService(settings=settings, store=store).build(use_ai=False)

        sections = {section["id"]: section for section in dashboard["sections"]}
        self.assertTrue(sections["overview"]["items"])
        self.assertTrue(sections["workflow_stages"]["items"])
        self.assertTrue(sections["research_copilot_insights"]["items"])
        for section in dashboard["sections"]:
            for item in section["items"]:
                self.assertTrue(item["provenance"], item)

    def test_dashboard_generation_with_many_experiments(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store, count=75)
            dashboard = DashboardService(settings=settings, store=store).build(use_ai=False)

        sections = {section["id"]: section for section in dashboard["sections"]}
        self.assertLessEqual(len(sections["experiments_requiring_attention"]["items"]), 8)
        self.assertEqual(dashboard["layout"]["mobile"]["priority_sections"][0], "overview")

    def test_dashboard_ai_enabled_and_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)
            ai_service = DashboardService(
                settings=Settings(database_url=settings.database_url, ai_provider="openai_compatible", ai_base_url="http://localhost", ai_model="test"),
                store=store,
                ai_provider_factory=lambda settings: FakeDashboardAI(),
            )
            ai_dashboard = ai_service.build(use_ai=True)
            local_dashboard = DashboardService(settings=settings, store=store).build(use_ai=False)

        self.assertEqual(ai_dashboard["assistant_summary"]["provider"], "fake-dashboard-ai")
        self.assertEqual(local_dashboard["assistant_summary"]["provider"], "local-fallback")

    def test_dashboard_cache_rebuilds_when_data_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            service = DashboardService(settings=settings, store=store)
            empty = service.build(use_ai=False)
            cached_empty = service.build(use_ai=False)
            self._seed(store)
            rebuilt = service.build(use_ai=False)

        self.assertTrue(cached_empty["cache"]["cached"])
        self.assertNotEqual(empty["cache"]["fingerprint"], rebuilt["cache"]["fingerprint"])
        self.assertGreater(int(rebuilt["sections"][0]["items"][0]["summary"]), 0)


if __name__ == "__main__":
    unittest.main()
