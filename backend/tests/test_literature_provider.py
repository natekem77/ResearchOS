"""Tests for local literature ingestion."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.literature_provider import load_literature_documents


class LiteratureProviderTests(unittest.TestCase):
    """Paper notes should become provider-agnostic literature documents."""

    def test_loads_text_paper_metadata_and_entities(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            paper_path = Path(tmpdir) / "brn3b_note.txt"
            paper_path.write_text(
                "\n".join(
                    [
                        "Title: BRN3B staining in retinal organoids",
                        "Authors: ResearchOS Test",
                        "Year: 2025",
                        "Journal: Demo Methods",
                        "DOI: 10.0000/researchos.test.2025",
                        "",
                        "Abstract:",
                        "BRN3B and SIX6 immunostaining can help evaluate retinal ganglion cell differentiation.",
                        "Confocal imaging should include DAPI controls.",
                        "",
                        "Keywords: BRN3B, SIX6, DAPI, immunostaining, confocal",
                    ]
                ),
                encoding="utf-8",
            )

            documents = load_literature_documents([Path(tmpdir)])

        self.assertEqual(len(documents), 1)
        document = documents[0]
        self.assertEqual(document.provider, "literature")
        self.assertEqual(document.title, "BRN3B staining in retinal organoids")
        self.assertEqual(document.metadata["year"], "2025")
        self.assertEqual(document.metadata["doi"], "10.0000/researchos.test.2025")
        self.assertIn("BRN3B", document.metadata["markers"])
        self.assertIn("SIX6", document.metadata["genes"])
        self.assertIn("immunostaining", document.metadata["methods"])


if __name__ == "__main__":
    unittest.main()
