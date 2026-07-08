"""Tests for Experiment Sessions."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.storage import SQLiteStore


class ExperimentSessionTests(unittest.TestCase):
    """Sessions should act as live containers for experiment work."""

    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def test_start_append_and_end_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(settings=self._settings(tmpdir))
            session = store.start_session(experiment_id="NK_Expt_31", notes="Started D32 staining session.")
            note = store.append_session_event(
                session_id=session["session_id"],
                event_type="voice_note",
                title="Voice note",
                content="SIX6 and BRN3B staining looked organized.",
            )
            treatment = store.append_session_event(
                session_id=session["session_id"],
                event_type="treatment",
                title="Added SAG",
                content="Added SAG plus GRKi condition.",
            )
            ended = store.end_session(session["session_id"], notes="Session complete.")

        self.assertIsNotNone(note)
        self.assertIsNotNone(treatment)
        self.assertIsNotNone(ended)
        assert ended is not None
        self.assertEqual(ended["status"], "ended")
        self.assertEqual(ended["experiment_id"], "NK_Expt_31")
        self.assertIn("SIX6 and BRN3B", ended["voice_transcripts"][0])
        self.assertGreaterEqual(len(ended["timeline"]), 4)

    def test_session_assets_and_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(settings=self._settings(tmpdir))
            asset = store.register_asset(
                asset_id="asset:image",
                asset_type="image",
                experiment_id="NK_Expt_31",
                title="D32 SIX6 image",
                filename="NK_Expt_31_D32_SIX6.tif",
                provider="microscopy",
                path="samples/images/NK_Expt_31_D32_SIX6.tif",
                metadata={"markers": ["SIX6"]},
            )
            session = store.start_session(experiment_id="NK_Expt_31")
            event = store.append_session_event(
                session_id=session["session_id"],
                event_type="image_imported",
                title="Image imported",
                asset_id=asset["asset_id"],
                metadata={"source": "microscopy"},
            )
            detail = store.get_session(session["session_id"])

        self.assertIsNotNone(event)
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["assets"][0]["asset_id"], "asset:image")
        self.assertEqual(detail["timeline"][0]["event_type"], "image_imported")

    def test_missing_session_append_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(settings=self._settings(tmpdir))
            event = store.append_session_event(
                session_id="session:missing",
                event_type="manual_note",
                title="Missing",
            )

        self.assertIsNone(event)


if __name__ == "__main__":
    unittest.main()
