"""Tests for structured experiment comparison."""

from __future__ import annotations

import unittest

from app.experiment_comparison import compare_experiments


class ExperimentComparisonTests(unittest.TestCase):
    """Comparison should separate shared features and differences."""

    def test_compares_shared_and_different_fields_without_ai(self) -> None:
        experiments = [
            {
                "id": "experiment:one",
                "title": "SAG Experiment",
                "date": "2026-06-12",
                "researcher": "N. Researcher",
                "cell_line": "SIX6 reporter iPSC line",
                "organoid_batch": "RO-SAG-24A",
                "compounds": ["SAG", "DMSO"],
                "treatments": ["SAG-treated"],
                "concentrations": ["100 nM"],
                "time_points": ["D32"],
                "markers": ["SIX6", "BRN3B"],
                "imaging_methods": ["brightfield"],
                "sequencing": [],
                "notes": "SAG-treated organoids showed smoother rims.",
                "conclusions": "SAG may improve early patterning.",
            },
            {
                "id": "experiment:two",
                "title": "SIX6/BRN3B Staining Result",
                "date": "2026-06-28",
                "researcher": None,
                "cell_line": None,
                "organoid_batch": None,
                "compounds": ["SAG"],
                "treatments": ["SAG-treated"],
                "concentrations": [],
                "time_points": ["D32"],
                "markers": ["SIX6", "BRN3B", "DAPI"],
                "imaging_methods": [],
                "sequencing": [],
                "notes": "BRN3B-positive cells were sparse.",
                "conclusions": "BRN3B conclusions should remain cautious.",
            },
        ]

        comparison = compare_experiments(experiments, use_ai=False)

        self.assertEqual(comparison.shared_features["compounds"], ["SAG"])
        self.assertEqual(comparison.shared_features["markers"], ["BRN3B", "SIX6"])
        self.assertEqual(comparison.shared_features["time_points"], ["D32"])
        self.assertNotIn("cell_line", comparison.shared_features)
        self.assertIn("cell_line", comparison.differences)
        self.assertIn("conclusions", comparison.differences)
        self.assertIn("Compared 2 experiments", comparison.likely_scientific_interpretation)
        self.assertFalse(comparison.ai_used)


if __name__ == "__main__":
    unittest.main()
