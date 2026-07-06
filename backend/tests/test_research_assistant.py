"""Tests and examples for ResearchOS assistant relevance filtering."""

from __future__ import annotations

import unittest

from app.research_assistant import (
    _local_direct_answer,
    _query_intent,
    _score_experiments,
    _split_experiment_relevance,
)


SAMPLE_EXPERIMENTS = [
    {
        "id": "experiment:sag",
        "source_document_id": "markdown:sag",
        "source_provider": "markdown",
        "title": "Retinal Organoid SAG Experiment",
        "experiment_id": "EXP-SAG",
        "date": "2026-06-12",
        "cell_line": "SIX6 reporter iPSC line",
        "organoid_batch": "RO-SAG-24A",
        "compounds": ["SAG", "DMSO"],
        "markers": ["SIX6", "BRN3B"],
        "time_points": ["D32"],
        "notes": "SAG-treated organoids showed smoother rims.",
        "conclusions": "SAG may improve early patterning consistency.",
    },
    {
        "id": "experiment:bmp4",
        "source_document_id": "markdown:bmp4",
        "source_provider": "markdown",
        "title": "BMP4 Protocol Note",
        "experiment_id": "EXP-BMP4",
        "date": "2026-06-05",
        "cell_line": None,
        "organoid_batch": "RO-BMP4-setup",
        "compounds": ["BMP4"],
        "markers": [],
        "time_points": ["D9"],
        "notes": "BMP4 pulse protocol for early retinal differentiation.",
        "conclusions": None,
    },
    {
        "id": "experiment:brn3b",
        "source_document_id": "markdown:brn3b",
        "source_provider": "markdown",
        "title": "SIX6/BRN3B Staining Result",
        "experiment_id": "EXP-BRN3B",
        "date": "2026-06-28",
        "cell_line": None,
        "organoid_batch": None,
        "compounds": ["SAG"],
        "markers": ["SIX6", "BRN3B", "DAPI"],
        "time_points": ["D32"],
        "notes": "BRN3B-positive cells were sparse.",
        "conclusions": "BRN3B conclusions should remain cautious.",
    },
]


SAMPLE_ONTOLOGY = {
    "compounds": [{"name": "SAG"}, {"name": "BMP4"}, {"name": "DMSO"}],
    "markers": [{"name": "BRN3B"}, {"name": "SIX6"}, {"name": "DAPI"}],
    "cell-lines": [{"name": "SIX6 reporter iPSC line"}],
    "organoid-batches": [{"name": "RO-SAG-24A"}, {"name": "RO-BMP4-setup"}],
}


class AssistantRelevanceTests(unittest.TestCase):
    """Entity-specific questions should avoid unrelated evidence."""

    def test_sag_question_only_directly_matches_sag_experiments(self) -> None:
        intent = _query_intent("Which experiments used SAG?", SAMPLE_ONTOLOGY)
        direct, related = _split_experiment_relevance(_score_experiments(intent, SAMPLE_EXPERIMENTS))

        self.assertEqual({experiment["experiment_id"] for experiment in direct}, {"EXP-SAG", "EXP-BRN3B"})
        self.assertEqual(related, [])
        self.assertNotIn("EXP-BMP4", {experiment["experiment_id"] for experiment in direct})

    def test_bmp4_question_only_directly_matches_bmp4_experiment(self) -> None:
        intent = _query_intent("What did BMP4 experiments show?", SAMPLE_ONTOLOGY)
        direct, related = _split_experiment_relevance(_score_experiments(intent, SAMPLE_EXPERIMENTS))

        self.assertEqual([experiment["experiment_id"] for experiment in direct], ["EXP-BMP4"])
        self.assertEqual(related, [])

    def test_brn3b_question_only_directly_matches_marker_experiments(self) -> None:
        intent = _query_intent("What markers were used with BRN3B?", SAMPLE_ONTOLOGY)
        direct, related = _split_experiment_relevance(_score_experiments(intent, SAMPLE_EXPERIMENTS))

        self.assertEqual({experiment["experiment_id"] for experiment in direct}, {"EXP-SAG", "EXP-BRN3B"})
        self.assertEqual(related, [])
        self.assertNotIn("EXP-BMP4", {experiment["experiment_id"] for experiment in direct})

    def test_cell_line_question_only_directly_matches_cell_line_experiment(self) -> None:
        intent = _query_intent("Which experiments used SIX6 reporter iPSC line?", SAMPLE_ONTOLOGY)
        direct, related = _split_experiment_relevance(_score_experiments(intent, SAMPLE_EXPERIMENTS))

        self.assertEqual(intent.explicit_entities, {"cell-lines": ["SIX6 reporter iPSC line"]})
        self.assertEqual([experiment["experiment_id"] for experiment in direct], ["EXP-SAG"])
        self.assertEqual(related, [])

    def test_comparison_question_allows_multiple_direct_entities(self) -> None:
        intent = _query_intent("Compare BMP4 and SAG experiments.", SAMPLE_ONTOLOGY)
        direct, related = _split_experiment_relevance(_score_experiments(intent, SAMPLE_EXPERIMENTS))

        self.assertEqual({experiment["experiment_id"] for experiment in direct}, {"EXP-SAG", "EXP-BMP4", "EXP-BRN3B"})
        self.assertEqual(related, [])

    def test_direct_answer_names_direct_entity_scope(self) -> None:
        intent = _query_intent("Which experiments used SAG?", SAMPLE_ONTOLOGY)
        direct, related = _split_experiment_relevance(_score_experiments(intent, SAMPLE_EXPERIMENTS))
        evidence = [
            {"experiment_id": experiment["experiment_id"], "title": experiment["title"]}
            for experiment in direct
        ]

        answer = _local_direct_answer(
            "Which experiments used SAG?",
            direct_evidence=evidence,
            related_evidence=[],
            facts={"compounds": ["SAG"], "markers": []},
            intent=intent,
        )

        self.assertIn("containing SAG", answer)
        self.assertIn("EXP-SAG", answer)
        self.assertIn("EXP-BRN3B", answer)

    def test_show_question_uses_readable_result_summary(self) -> None:
        intent = _query_intent("What did BMP4 experiments show?", SAMPLE_ONTOLOGY)
        direct, _ = _split_experiment_relevance(_score_experiments(intent, SAMPLE_EXPERIMENTS))
        evidence = [
            {
                "experiment_id": experiment["experiment_id"],
                "title": experiment["title"],
                "notes": experiment["notes"],
                "conclusions": experiment["conclusions"],
            }
            for experiment in direct
        ]

        answer = _local_direct_answer(
            "What did BMP4 experiments show?",
            direct_evidence=evidence,
            related_evidence=[],
            facts={"compounds": ["BMP4"], "markers": []},
            intent=intent,
        )

        self.assertIn("direct result", answer)
        self.assertIn("EXP-BMP4", answer)
        self.assertIn("BMP4 pulse protocol", answer)


if __name__ == "__main__":
    unittest.main()
