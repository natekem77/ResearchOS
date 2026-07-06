"""Tests for dictated experiment entry drafting."""

from __future__ import annotations

import unittest

from app.entry_drafting import draft_entry_from_notes


class EntryDraftingTests(unittest.TestCase):
    """Dictated notes should produce a reviewable structured draft."""

    def test_sample_dictation_extracts_core_fields(self) -> None:
        draft = draft_entry_from_notes(
            (
                "Create NK Expt 31. Day 1 SAG plus GRK inhibitor. "
                "Objective: test early retinal organoid patterning. "
                "Cell line SIX6 reporter iPSC line. Organoid batch RO-NK-31. "
                "Treat with 100 nM SAG from D18 to D24. DMSO vehicle control. "
                "Planned readouts brightfield and BRN3B staining at D32. "
                "Observed smooth rims. Next steps quantify SIX6 intensity."
            ),
            use_ai=False,
        )

        self.assertEqual(draft.structured["experiment_id"], "NK-EXPT-31")
        self.assertIn("SAG", draft.structured["treatments"])
        self.assertIn("100 nM", draft.structured["concentrations"])
        self.assertIn("RO-NK-31", draft.structured["organoid_batch"])
        self.assertIn("DMSO vehicle control", draft.structured["controls"])
        self.assertIn("BRN3B", draft.structured["planned_readouts"])
        self.assertEqual(draft.structured["next_steps"], "quantify SIX6 intensity")
        self.assertIn("# NK-EXPT-31", draft.markdown)
        self.assertGreater(draft.confidence, 0.45)


if __name__ == "__main__":
    unittest.main()
