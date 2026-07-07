"""Tests for Knowledge Graph powered assistant responses."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.experiments import Experiment
from app.knowledge_graph_assistant import answer_with_knowledge_graph
from app.research_assistant import ask_research_assistant
from app.research_document import DocumentChunk, ResearchDocument
from app.scientific_reasoning import reason_scientifically
from app.storage import SQLiteStore


class KnowledgeGraphAssistantTests(unittest.TestCase):
    """Assistant answers should use Knowledge Graph evidence first."""

    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def _seed(self, store: SQLiteStore) -> None:
        document = ResearchDocument(
            id="doc:sag",
            provider="markdown",
            source_id="sag.md",
            title="SAG SIX6 BRN3B notebook",
            content="NK_Expt_31 used SAG and measured SIX6 and BRN3B.",
            metadata={"entities": {"compound": ["SAG"], "marker": ["SIX6", "BRN3B"]}},
        )
        store.upsert_document(
            document,
            [DocumentChunk(id="chunk:sag", document_id=document.id, chunk_index=0, text=document.content, token_estimate=12)],
        )
        store.upsert_experiment(
            Experiment(
                id="experiment:sag",
                source_document_id=document.id,
                source_provider="markdown",
                title="NK Expt 31 SAG",
                experiment_id="NK_Expt_31",
                compounds=["SAG"],
                markers=["SIX6", "BRN3B"],
            )
        )
        store.register_asset(
            asset_id="asset:image",
            asset_type="microscopy",
            experiment_id="NK_Expt_31",
            title="SIX6 BRN3B image",
            filename="NK_Expt_31_SIX6_BRN3B.tif",
            provider="microscopy",
            path="samples/images/NK_Expt_31_SIX6_BRN3B.tif",
            metadata={"markers": ["SIX6", "BRN3B"]},
        )

    def test_knowledge_assistant_entity_question(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)

            answer = answer_with_knowledge_graph("What do we know about SAG?", settings=settings, use_ai=False)

        self.assertEqual(answer.entity, "SAG")
        self.assertTrue(answer.experiments)
        self.assertTrue(answer.notebook_entries)
        self.assertIn("Knowledge Graph evidence", answer.direct_answer)

    def test_knowledge_assistant_experiment_question(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)

            answer = answer_with_knowledge_graph("What data exists for NK_Expt_31?", settings=settings, use_ai=False)

        self.assertEqual(answer.experiment["experiment_id"], "NK_Expt_31")
        self.assertTrue(answer.microscopy_images)

    def test_existing_assistant_and_reasoning_include_graph_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            self._seed(store)

            assistant = ask_research_assistant("Show everything involving SIX6.", settings=settings, use_ai=False)
            reasoning = reason_scientifically("Which experiments involve BRN3B?", settings=settings, use_ai=False)

        self.assertIn("SIX6", assistant.extracted_facts.get("knowledge_graph_entities", []))
        self.assertIn("knowledge_graph", reasoning.reasoning)
        self.assertTrue(reasoning.reasoning["knowledge_graph"]["sources"])


if __name__ == "__main__":
    unittest.main()
