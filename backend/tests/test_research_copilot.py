"""Tests for Research Copilot workspace synthesis."""

from __future__ import annotations

import unittest

from app.config import Settings
from app.research_copilot import ResearchCopilotService


class FakeAIProvider:
    """Minimal fake provider for AI-enabled Copilot tests."""

    provider_name = "fake-ai"

    def chat(self, message: str, context: str | None = None) -> str:
        return "Observed: extracted conclusion only. Inferred: linked assets. Suggested: replicate with controls."


class ResearchCopilotTests(unittest.TestCase):
    """Copilot output must stay provenance-backed and non-hallucinatory."""

    def _workspace(self, include_statistics: bool = True, include_literature: bool = True) -> dict[str, object]:
        statistics = [
            {
                "asset_id": "asset:stats",
                "provider": "graphpad",
                "interpretation": {"summary": "SIX6 was higher in SAG than DMSO (p=0.01)."},
                "compact_summary": {"short_interpretation": "SAG group showed higher SIX6 signal."},
            }
        ] if include_statistics else []
        literature = [{"id": "doc:lit", "title": "SAG retinal differentiation literature", "provider": "literature"}] if include_literature else []
        return {
            "experiment": {
                "id": "experiment:copilot",
                "experiment_id": "NK_Expt_31",
                "title": "SAG rescue",
                "compounds": ["SAG"],
                "markers": ["SIX6", "BRN3B"],
                "conclusions": "SAG condition produced stronger SIX6 signal.",
            },
            "notebook_entries": [{"id": "doc:note", "title": "SAG notebook", "provider": "markdown"}],
            "microscopy": [{"asset_id": "asset:image", "provider": "microscopy", "filename": "SIX6.tif"}],
            "graphpad": [{"asset_id": "asset:graphpad", "provider": "graphpad", "filename": "stats.csv"}],
            "spreadsheets": [{"asset_id": "asset:sheet", "provider": "spreadsheet", "filename": "quant.csv"}],
            "statistics": statistics,
            "literature": literature,
            "related_experiments": [{"id": "experiment:related", "experiment_id": "NK_Expt_32"}],
            "compounds": ["SAG"],
            "markers": ["SIX6", "BRN3B"],
            "limitations": ["Workspace is assembled from local ResearchOS records."],
            "conclusions": {
                "observed": ["SAG condition produced stronger SIX6 signal."],
                "inferred": ["Workspace links are inferred from provider metadata."],
                "referenced_from_literature": ["SAG retinal differentiation literature"] if include_literature else [],
            },
            "lifecycle": {
                "current_stage": "Analysis",
                "recommended_next_actions": ["Complete statistics before making final claims."],
                "history": [{"to_stage": "Analysis"}],
            },
            "provenance": [
                {"fact": "experiment", "source": "experiment_extraction", "provider": "markdown", "document": "doc:note"},
                {"fact": "statistics", "source": "statistics_interpreter", "provider": "graphpad", "asset": "asset:stats"},
                {"fact": "microscopy", "source": "asset", "provider": "microscopy", "asset": "asset:image"},
                {"fact": "literature", "source": "document", "provider": "literature", "document": "doc:lit"},
                {"fact": "entity", "source": "knowledge_graph", "provider": "knowledgegraph", "document": "SAG"},
            ],
        }

    def test_local_fallback_sections_include_multiple_providers(self) -> None:
        copilot = ResearchCopilotService(settings=Settings(ai_provider="none")).build(self._workspace(), use_ai=False)

        self.assertEqual(copilot["provider"], "local-fallback")
        sections = copilot["sections"]
        self.assertTrue(sections["key_findings"])
        self.assertTrue(sections["related_experiments"])
        self.assertTrue(sections["related_literature"])
        self.assertTrue(sections["suggested_follow_up_experiments"])
        self.assertIn("SIX6", copilot["natural_summary"])

    def test_ai_enabled_uses_provider_for_natural_summary(self) -> None:
        service = ResearchCopilotService(
            settings=Settings(ai_provider="openai_compatible", ai_base_url="http://localhost", ai_model="test"),
            ai_provider_factory=lambda settings: FakeAIProvider(),
        )

        copilot = service.build(self._workspace(), use_ai=True)

        self.assertEqual(copilot["provider"], "fake-ai")
        self.assertIn("Observed:", copilot["natural_summary"])
        self.assertTrue(copilot["sections"]["key_findings"])

    def test_missing_statistics_and_literature_are_reported_as_concerns(self) -> None:
        copilot = ResearchCopilotService(settings=Settings(ai_provider="none")).build(
            self._workspace(include_statistics=False, include_literature=False),
            use_ai=False,
        )

        concerns = " ".join(item["text"] for item in copilot["sections"]["potential_concerns"])
        self.assertIn("No parsed statistics", concerns)
        self.assertIn("No literature references", concerns)
        self.assertIn("Lifecycle stage is Analysis", concerns)

    def test_every_statement_has_provenance(self) -> None:
        copilot = ResearchCopilotService(settings=Settings(ai_provider="none")).build(self._workspace(), use_ai=False)

        for statements in copilot["sections"].values():
            for statement in statements:
                self.assertTrue(statement["provenance"], statement)

    def test_no_hallucinated_observations(self) -> None:
        workspace = self._workspace(include_statistics=False, include_literature=False)
        workspace["experiment"]["conclusions"] = ""
        workspace["conclusions"]["observed"] = []

        copilot = ResearchCopilotService(settings=Settings(ai_provider="none")).build(workspace, use_ai=False)
        observed = [
            statement["text"]
            for statement in copilot["sections"]["key_findings"]
            if statement["category"] == "observed"
        ]

        self.assertEqual(observed, ["No explicit observed findings have been extracted yet."])
        self.assertNotIn("improved retinal differentiation", " ".join(observed).lower())

    def test_lifecycle_recommendations_feed_follow_ups(self) -> None:
        workspace = self._workspace()
        workspace["lifecycle"] = {
            "current_stage": "Analysis",
            "recommended_next_actions": ["Upload GraphPad analysis if quantitative comparison is expected."],
            "history": [{"to_stage": "Analysis"}],
        }

        copilot = ResearchCopilotService(settings=Settings(ai_provider="none")).build(workspace, use_ai=False)
        suggestions = " ".join(item["text"] for item in copilot["sections"]["suggested_follow_up_experiments"])

        self.assertIn("Upload GraphPad analysis", suggestions)


if __name__ == "__main__":
    unittest.main()
