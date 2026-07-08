"""Tests for the Quantification Workspace."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.experiments import Experiment
from app.quantification_workspace import QuantificationWorkspaceService
from app.research_document import DocumentChunk, ResearchDocument
from app.storage import SQLiteStore


class QuantificationWorkspaceTests(unittest.TestCase):
    """Quantitative analysis should be organized as a first-class workspace."""

    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def _seed(self, store: SQLiteStore) -> None:
        document = ResearchDocument(
            id="doc:quant",
            provider="markdown",
            source_id="quant.md",
            title="NK_Expt_85 quantification note",
            content="NK_Expt_85 used SAG and measured SIX6 and BRN3B microscopy.",
            metadata={"entities": {"compound": ["SAG"], "marker": ["SIX6", "BRN3B"]}},
        )
        store.upsert_document(
            document,
            [DocumentChunk(id="chunk:quant", document_id=document.id, chunk_index=0, text=document.content, token_estimate=10)],
        )
        store.upsert_experiment(
            Experiment(
                id="experiment:quant",
                source_document_id=document.id,
                source_provider="markdown",
                title="NK_Expt_85 quantification",
                experiment_id="NK_Expt_85",
                compounds=["SAG"],
                markers=["SIX6", "BRN3B"],
            )
        )
        store.register_asset(
            asset_id="asset:quant-image",
            asset_type="microscopy",
            experiment_id="NK_Expt_85",
            title="D32 SIX6 BRN3B image",
            filename="NK_Expt_85_D32_SIX6_BRN3B_DAPI.tif",
            provider="microscopy",
            path="samples/images/NK_Expt_85_D32_SIX6_BRN3B_DAPI.tif",
            metadata={"markers": ["SIX6", "BRN3B", "DAPI"], "timepoint": "D32", "extension": ".tif", "parser": "filename_metadata"},
        )
        store.register_asset(
            asset_id="asset:quant-table",
            asset_type="spreadsheet",
            experiment_id="NK_Expt_85",
            title="SIX6 quantification table",
            filename="NK_Expt_85_quant.csv",
            provider="spreadsheet",
            path="samples/spreadsheets/NK_Expt_85_quant.csv",
            metadata={
                "detected_tables": [
                    {
                        "numeric_summaries": {"Percent_Positive": {"mean": 42.0, "median": 41.0, "standard_deviation": 2.0, "sem": 1.1}},
                        "grouped_summaries": {"Treatment": {"DMSO": {"Percent_Positive": {"mean": 30.0, "count": 3}}, "SAG": {"Percent_Positive": {"mean": 42.0, "count": 3}}}},
                    }
                ],
                "entities": {"markers": ["SIX6"], "treatments": ["SAG"]},
            },
        )
        store.register_asset(
            asset_id="asset:quant-graphpad",
            asset_type="graphpad",
            experiment_id="NK_Expt_85",
            title="SIX6 GraphPad stats",
            filename="NK_Expt_85_stats.csv",
            provider="graphpad",
            path="samples/graphpad/NK_Expt_85_stats.csv",
            metadata={
                "statistics": {
                    "rows": [
                        {
                            "variable": "SIX6 Percent_Positive",
                            "group": "SAG",
                            "comparison": "DMSO vs SAG",
                            "mean": 42.0,
                            "sem": 1.1,
                            "n": 3,
                            "p_value": 0.02,
                            "test": "one-way ANOVA",
                        }
                    ]
                }
            },
        )

    def test_workspace_generation_and_linking(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)
            workspace = QuantificationWorkspaceService(settings=settings, store=store).build("NK_Expt_85")

        self.assertIsNotNone(workspace)
        assert workspace is not None
        self.assertEqual(workspace["workspace_type"], "quantification")
        self.assertEqual(len(workspace["raw_images"]), 1)
        self.assertEqual(len(workspace["quantification_tables"]), 1)
        self.assertEqual(len(workspace["graphpad_assets"]), 1)
        self.assertTrue(workspace["statistical_analysis"])
        self.assertIn("SIX6", workspace["raw_images"][0]["markers"])

    def test_timeline_kg_evidence_and_copilot_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)
            workspace = QuantificationWorkspaceService(settings=settings, store=store).build("experiment:quant")

        assert workspace is not None
        event_types = {event["event_type"] for event in workspace["timeline_events"]}
        self.assertIn("images_imported", event_types)
        self.assertIn("spreadsheet_imported", event_types)
        self.assertIn("graphpad_imported", event_types)
        self.assertIn("statistics_completed", event_types)
        self.assertIn("SIX6", workspace["knowledge_graph"]["markers"])
        self.assertIn("summary", workspace["evidence"])
        self.assertIn("current_quantitative_evidence", workspace["research_copilot"]["sections"])
        self.assertTrue(workspace["provenance"])


if __name__ == "__main__":
    unittest.main()
