"""Unit tests for the ResearchOS experiment extraction layer."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.experiment_extraction import extract_experiment
from app.experiments import Experiment
from app.research_document import ResearchDocument
from app.storage import SQLiteStore


class ExperimentExtractionTests(unittest.TestCase):
    """Regex extraction should produce useful structured experiment records."""

    def test_extracts_structured_fields_from_research_document(self) -> None:
        document = ResearchDocument(
            id="markdown:test",
            provider="markdown",
            source_id="test.md",
            title="Retinal Organoid SAG Experiment",
            content=(
                "# Retinal Organoid SAG Experiment\n\n"
                "Experiment ID: SAG-D32-001\n"
                "Date: 2026-06-12\n"
                "Researcher: N. Researcher\n"
                "Organoid batch: RO-24A\n\n"
                "- Cell line: SIX6 reporter iPSC line.\n"
                "- Treatment: 100 nM SAG added daily.\n"
                "- Readouts: brightfield morphology, SIX6 fluorescence, BRN3B staining at D32.\n\n"
                "Markers:\n\n- SIX6\n- BRN3B\n- DAPI\n\n"
                "Interpretation:\n\nSAG may improve early patterning consistency."
            ),
        )

        experiment = extract_experiment(document)

        self.assertIsNotNone(experiment)
        assert experiment is not None
        self.assertEqual(experiment.experiment_id, "SAG-D32-001")
        self.assertEqual(experiment.date, "2026-06-12")
        self.assertEqual(experiment.researcher, "N. Researcher")
        self.assertEqual(experiment.cell_line, "SIX6 reporter iPSC line")
        self.assertEqual(experiment.organoid_batch, "RO-24A")
        self.assertIn("SAG", experiment.compounds)
        self.assertIn("100 nM", experiment.concentrations)
        self.assertIn("D32", experiment.time_points)
        self.assertIn("SIX6", experiment.markers)
        self.assertIn("BRN3B", experiment.markers)
        self.assertIn("brightfield", experiment.imaging_methods)
        self.assertIn("SAG may improve", experiment.conclusions or "")


class ExperimentStorageTests(unittest.TestCase):
    """SQLite storage should persist extracted experiments."""

    def test_upserts_and_reads_experiment(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "researchos-test.db"
            settings = SimpleNamespace(database_url=f"sqlite:///{db_path}")
            store = SQLiteStore(settings=settings)  # type: ignore[arg-type]
            experiment = Experiment(
                id="experiment:test",
                source_document_id="markdown:test",
                source_provider="markdown",
                title="Test Experiment",
                experiment_id="EXP-1",
                date="2026-06-12",
                compounds=["SAG"],
                treatments=["SAG-treated"],
                concentrations=["100 nM"],
                time_points=["D32"],
                markers=["SIX6"],
                antibodies=[],
                imaging_methods=["brightfield"],
                sequencing=[],
                notes="Observed smoother rims.",
                conclusions="Repeat with more organoids.",
            )

            store.upsert_experiment(experiment)

            experiments = store.list_experiments()
            self.assertEqual(len(experiments), 1)
            self.assertEqual(experiments[0]["id"], "experiment:test")
            self.assertEqual(experiments[0]["compounds"], ["SAG"])
            self.assertEqual(experiments[0]["markers"], ["SIX6"])

            fetched = store.get_experiment("experiment:test")
            self.assertIsNotNone(fetched)
            assert fetched is not None
            self.assertEqual(fetched["conclusions"], "Repeat with more organoids.")


if __name__ == "__main__":
    unittest.main()
