"""Regression tests for generic spreadsheet ingestion and summaries."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.spreadsheet_provider import compact_spreadsheet_summary, scan_spreadsheet_assets
from app.storage import PROJECT_ROOT


class SpreadsheetProviderTests(unittest.TestCase):
    """Spreadsheet summaries should only report explicit statistical p-values."""

    def test_percent_positive_mean_is_not_reported_as_p_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}",
                spreadsheet_scan_folders=str(PROJECT_ROOT / "samples" / "spreadsheets"),
            )

            scan_result = scan_spreadsheet_assets(settings=settings)
            assets = scan_result.registered_assets + scan_result.skipped_assets
            asset = next(
                item for item in assets if item.get("filename") == "NK_Expt_31_quantitative_readouts.csv"
            )
            summary = compact_spreadsheet_summary(str(asset["asset_id"]), settings=settings)

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary["p_values"], [])
        self.assertIn("No p-values detected", summary["short_interpretation"])
        self.assertNotIn(37.9666, summary["p_values"])


if __name__ == "__main__":
    unittest.main()
