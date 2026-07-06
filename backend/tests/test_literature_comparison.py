"""Tests for local lab-literature comparison helpers."""

from __future__ import annotations

import unittest

from app.literature_comparison import (
    _differences,
    _protocol_treatment_differences,
    _similarities,
)


SAMPLE_LAB_EXPERIMENTS = [
    {
        "title": "Retinal Organoid SAG Experiment",
        "compounds": ["SAG", "DMSO"],
        "markers": ["SIX6", "BRN3B"],
        "treatments": ["100 nM SAG added daily"],
        "concentrations": ["100 nM"],
        "time_points": ["D18 to D24", "D32"],
        "imaging_methods": ["brightfield"],
        "sequencing": [],
    }
]

SAMPLE_LITERATURE = [
    {
        "title": "Retinal organoid patterning signals",
        "snippet": (
            "SAG experiments should include vehicle controls such as DMSO. "
            "Markers such as SIX6 and BRN3B are used at D32. "
            "BMP4 timing should be interpreted carefully."
        ),
    }
]


class LiteratureComparisonTests(unittest.TestCase):
    """Comparison helpers should separate overlap from lab-only details."""

    def test_detects_lab_literature_overlap(self) -> None:
        similarities = _similarities(SAMPLE_LAB_EXPERIMENTS, SAMPLE_LITERATURE)

        joined = " ".join(similarities)
        self.assertIn("SAG", joined)
        self.assertIn("DMSO", joined)
        self.assertIn("BRN3B", joined)

    def test_detects_lab_only_protocol_details(self) -> None:
        differences = _differences(SAMPLE_LAB_EXPERIMENTS, SAMPLE_LITERATURE)

        joined = " ".join(differences)
        self.assertIn("100 nM", joined)
        self.assertIn("D18 to D24", joined)

    def test_detects_protocol_notes(self) -> None:
        notes = _protocol_treatment_differences(SAMPLE_LAB_EXPERIMENTS, SAMPLE_LITERATURE)

        joined = " ".join(notes)
        self.assertIn("vehicle", joined)
        self.assertIn("timing", joined)


if __name__ == "__main__":
    unittest.main()
