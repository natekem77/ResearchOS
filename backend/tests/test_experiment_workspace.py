"""Tests for unified experiment workspace assembly."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.experiment_workspace import build_experiment_workspace
from app.experiments import Experiment
from app.global_knowledge_graph import KnowledgeGraphService
from app.research_document import DocumentChunk, ResearchDocument
from app.storage import SQLiteStore


class ExperimentWorkspaceTests(unittest.TestCase):
    """Experiment workspaces should aggregate graph-backed local evidence."""

    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def _seed(self, store: SQLiteStore) -> None:
        for index in [1, 2]:
            document = ResearchDocument(
                id=f"doc:{index}",
                provider="markdown",
                source_id=f"note-{index}.md",
                title=f"SAG notebook {index}",
                content="NK_Expt_31 used SAG with SIX6 and BRN3B readouts.",
                metadata={"entities": {"compound": ["SAG"], "marker": ["SIX6", "BRN3B"]}},
            )
            store.upsert_document(
                document,
                [DocumentChunk(id=f"chunk:{index}", document_id=document.id, chunk_index=0, text=document.content, token_estimate=12)],
            )
        literature = ResearchDocument(
            id="doc:lit",
            provider="literature",
            source_id="paper.txt",
            title="SAG retinal differentiation literature",
            content="SAG and SIX6 are discussed in retinal differentiation literature.",
            metadata={"entities": {"compound": ["SAG"], "gene": ["SIX6"]}},
        )
        store.upsert_document(
            literature,
            [DocumentChunk(id="chunk:lit", document_id=literature.id, chunk_index=0, text=literature.content, token_estimate=10)],
        )
        store.upsert_experiment(
            Experiment(
                id="experiment:workspace",
                source_document_id="doc:1",
                source_provider="markdown",
                title="NK Expt 31 SAG workspace",
                experiment_id="NK_Expt_31",
                cell_line="SIX6 reporter iPSC",
                organoid_batch="RO-NK-31",
                compounds=["SAG"],
                treatments=["SAG + GRKi"],
                markers=["SIX6", "BRN3B"],
                conclusions="SAG condition produced stronger SIX6 signal.",
            )
        )
        store.upsert_experiment(
            Experiment(
                id="experiment:related",
                source_document_id="doc:2",
                source_provider="markdown",
                title="Related BRN3B note",
                experiment_id="NK_Expt_32",
                compounds=["SAG"],
                markers=["BRN3B"],
            )
        )
        store.register_asset(
            asset_id="asset:image1",
            asset_type="microscopy",
            experiment_id="NK_Expt_31",
            title="SIX6 image",
            filename="NK_Expt_31_SIX6.tif",
            provider="microscopy",
            path="samples/images/NK_Expt_31_SIX6.tif",
            metadata={"markers": ["SIX6"]},
        )
        store.register_asset(
            asset_id="asset:image2",
            asset_type="microscopy",
            experiment_id="NK_Expt_31",
            title="BRN3B image",
            filename="NK_Expt_31_BRN3B.tif",
            provider="microscopy",
            path="samples/images/NK_Expt_31_BRN3B.tif",
            metadata={"markers": ["BRN3B"]},
        )
        store.register_asset(
            asset_id="asset:graphpad",
            asset_type="spreadsheet",
            experiment_id="NK_Expt_31",
            title="GraphPad stats",
            filename="NK_Expt_31_stats.csv",
            provider="graphpad",
            path="samples/graphpad/NK_Expt_31_stats.csv",
            metadata={
                "statistics": {
                    "variables": ["SIX6"],
                    "group_names": ["DMSO", "SAG"],
                    "statistical_tests": ["t-test"],
                    "rows": [{"variable": "SIX6", "group": "SAG", "comparison": "DMSO vs SAG", "p_value": 0.01}],
                }
            },
        )
        store.register_asset(
            asset_id="asset:sheet1",
            asset_type="spreadsheet",
            experiment_id="NK_Expt_31",
            title="Quant sheet 1",
            filename="NK_Expt_31_quant_1.csv",
            provider="spreadsheet",
            path="samples/spreadsheets/NK_Expt_31_quant_1.csv",
            metadata={"entities": {"markers": ["SIX6"], "treatments": ["SAG"]}},
        )
        store.register_asset(
            asset_id="asset:sheet2",
            asset_type="spreadsheet",
            experiment_id="NK_Expt_31",
            title="Quant sheet 2",
            filename="NK_Expt_31_quant_2.csv",
            provider="spreadsheet",
            path="samples/spreadsheets/NK_Expt_31_quant_2.csv",
            metadata={"entities": {"markers": ["BRN3B"], "treatments": ["SAG"]}},
        )

    def test_workspace_aggregates_multiple_providers_with_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)
            service = KnowledgeGraphService(settings=settings, store=store)
            timeline = {"experiment_id": "experiment:workspace", "title": "Timeline", "events": []}

            workspace = build_experiment_workspace("NK_Expt_31", timeline, settings=settings, use_ai=False, knowledge_graph=service)

        self.assertIsNotNone(workspace)
        assert workspace is not None
        self.assertEqual(workspace["experiment"]["experiment_id"], "NK_Expt_31")
        self.assertGreaterEqual(len(workspace["microscopy"]), 2)
        self.assertGreaterEqual(len(workspace["spreadsheets"]), 2)
        self.assertTrue(workspace["graphpad"])
        self.assertTrue(workspace["statistics"])
        self.assertTrue(workspace["literature"])
        self.assertIn("SAG", workspace["compounds"])
        self.assertIn("SIX6", workspace["markers"])
        self.assertTrue(workspace["related_experiments"])
        self.assertTrue(any(item["asset"] == "asset:image1" for item in workspace["provenance"]))
        self.assertEqual(workspace["ai_summary"]["provider"], "local-fallback")

    def test_workspace_handles_missing_optional_providers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            document = ResearchDocument(
                id="doc:min",
                provider="markdown",
                source_id="min.md",
                title="Minimal experiment",
                content="Minimal note.",
                metadata={},
            )
            store.upsert_document(
                document,
                [DocumentChunk(id="chunk:min", document_id=document.id, chunk_index=0, text=document.content, token_estimate=2)],
            )
            store.upsert_experiment(
                Experiment(id="experiment:min", source_document_id=document.id, source_provider="markdown", title="Minimal")
            )
            timeline = {"experiment_id": "experiment:min", "title": "Timeline", "events": []}

            workspace = build_experiment_workspace("experiment:min", timeline, settings=settings, use_ai=False)

        self.assertIsNotNone(workspace)
        assert workspace is not None
        self.assertEqual(workspace["microscopy"], [])
        self.assertTrue(workspace["limitations"])


if __name__ == "__main__":
    unittest.main()
