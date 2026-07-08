"""Tests for first-class Research Resources."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app import main
from app.config import Settings
from app.experiment_workspace import build_experiment_workspace
from app.experiments import Experiment
from app.global_knowledge_graph import KnowledgeGraphService
from app.research_document import DocumentChunk, ResearchDocument
from app.storage import SQLiteStore
from app.universal_search import UniversalSearchService


class ResearchResourceTests(unittest.TestCase):
    """Resources should be reusable objects connected to experiments."""

    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def _seed_experiment(self, store: SQLiteStore) -> dict[str, object]:
        document = ResearchDocument(
            id="doc:resources",
            provider="markdown",
            source_id="resources.md",
            title="SAG resource experiment",
            content="NK_Expt_82 used SAG with SIX6 readout.",
            metadata={"entities": {"compound": ["SAG"], "marker": ["SIX6"]}},
        )
        store.upsert_document(
            document,
            [DocumentChunk(id="chunk:resources", document_id=document.id, chunk_index=0, text=document.content, token_estimate=8)],
        )
        store.upsert_experiment(
            Experiment(
                id="experiment:resources",
                source_document_id=document.id,
                source_provider="markdown",
                title="SAG resource experiment",
                experiment_id="NK_Expt_82",
                compounds=["SAG"],
                markers=["SIX6"],
            )
        )
        experiment = store.get_experiment("experiment:resources")
        assert experiment is not None
        return experiment

    def test_resource_crud_and_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(settings=self._settings(tmpdir))
            resource = store.save_resource(
                resource_type="compound",
                name="SAG",
                aliases=["Smoothened agonist"],
                vendor="Demo Vendor",
                catalog_number="SAG-001",
                lot_number="LOT-82",
                storage_location="-20C box A",
            )
            usage = store.record_resource_usage(
                resource_id=str(resource["resource_id"]),
                object_type="experiment",
                object_id="experiment:resources",
                usage_type="treatment",
                source="test",
            )
            updated = store.save_resource(
                resource_id=str(resource["resource_id"]),
                resource_type="compound",
                name="SAG",
                aliases=["Smoothened agonist", "Hh agonist"],
                vendor="Updated Vendor",
            )

        self.assertEqual(resource["resource_type"], "compound")
        self.assertEqual(usage["usage_type"], "treatment")
        self.assertIn("Hh agonist", updated["aliases"])
        self.assertEqual(updated["vendor"], "Updated Vendor")

    def test_api_crud_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_settings = main.settings
            main.settings = self._settings(tmpdir)
            try:
                created = main.create_resource(
                    main.ResourceRequest(
                        resource_type="antibody",
                        name="Anti-BRN3B",
                        aliases=["POU4F2 antibody"],
                        vendor="Demo Vendor",
                        rrid="RRID:AB_000000",
                    )
                )
                listed = main.resources(resource_type=None, query=None, workspace_id=None)
                typed = main.resources_by_type("antibody", workspace_id=None)
                detail = main.resource_detail(created.resource_id)
                updated = main.update_resource(
                    created.resource_id,
                    main.ResourceRequest(resource_type="antibody", name="Anti-BRN3B", aliases=["BRN3B antibody"]),
                )
            finally:
                main.settings = original_settings

        self.assertEqual(len(listed), 1)
        self.assertEqual(len(typed), 1)
        self.assertEqual(detail.name, "Anti-BRN3B")
        self.assertIn("BRN3B antibody", updated.aliases)

    def test_resources_enter_knowledge_graph_workspace_and_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            experiment = self._seed_experiment(store)
            resource = store.save_resource(
                resource_type="compound",
                name="SAG",
                aliases=["Smoothened agonist"],
                vendor="Demo Vendor",
            )
            store.record_resource_usage(
                resource_id=str(resource["resource_id"]),
                object_type="experiment",
                object_id=str(experiment["id"]),
                usage_type="treatment",
                source="test",
            )
            graph = KnowledgeGraphService(settings=settings, store=store)
            sag = graph.entity_detail("Smoothened agonist")
            workspace = build_experiment_workspace(
                "NK_Expt_82",
                {"experiment_id": "experiment:resources", "title": "Timeline", "events": []},
                settings=settings,
                use_ai=False,
                knowledge_graph=graph,
            )
            search = UniversalSearchService(settings=settings, store=store, knowledge_graph=graph).search("SAG")

        self.assertIsNotNone(sag)
        assert sag is not None
        self.assertTrue(sag["resources"])
        self.assertIsNotNone(workspace)
        assert workspace is not None
        self.assertTrue(workspace["resources"])
        self.assertTrue(search["grouped_results"].get("resources"))


if __name__ == "__main__":
    unittest.main()
