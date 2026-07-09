"""Tests for the confirmation-first Voice Laboratory Assistant."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app import main
from app.config import Settings
from app.experiments import Experiment
from app.storage import SQLiteStore
from app.voice_assistant import parse_voice_command
from app.workflow_engine import experiment_workflow_id


class VoiceAssistantTests(unittest.TestCase):
    """Voice commands should be parsed safely and committed only after review."""

    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def test_parse_treatment_command_preserves_transcript(self) -> None:
        transcript = "Treatment add SAG at 100 nM on D32 for NK Expt 31."
        command = parse_voice_command(transcript)

        self.assertEqual(command.command_type, "treatment")
        self.assertEqual(command.transcript, transcript)
        self.assertTrue(command.requires_confirmation)
        self.assertIn("100 nM", command.parsed_fields["dose"])
        self.assertEqual(command.parsed_fields["timepoint"], "D32")

    def test_draft_does_not_write_until_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_settings = main.settings
            main.settings = self._settings(tmpdir)
            try:
                store = SQLiteStore(settings=main.settings)
                session = store.start_session(experiment_id="NK_Expt_31")
                draft = main.voice_draft(
                    main.VoiceDraftRequest(
                        transcript="Observation organoids look healthy.",
                        session_id=session["session_id"],
                        experiment_id="NK_Expt_31",
                    )
                )
                entries = store.list_pending_entries()
                timeline = store.session_timeline(session["session_id"])
            finally:
                main.settings = original_settings

        self.assertEqual(draft["status"], "draft")
        self.assertTrue(draft["requires_confirmation"])
        self.assertEqual(entries, [])
        self.assertEqual(timeline, [])

    def test_confirm_creates_session_event_entry_and_workflow_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_settings = main.settings
            main.settings = self._settings(tmpdir)
            try:
                store = SQLiteStore(settings=main.settings)
                store.upsert_experiment(
                    Experiment(
                        id="experiment:voice",
                        source_document_id="document:voice",
                        source_provider="markdown",
                        title="Voice-linked experiment",
                        experiment_id="NK_Expt_31",
                    )
                )
                session = store.start_session(experiment_id="NK_Expt_31")
                response = main.voice_confirm(
                    main.VoiceConfirmRequest(
                        voice_session_id="voice-session:test",
                        command_type="observation",
                        transcript="Observation SIX6 reporter looks brighter after SAG.",
                        parsed_fields={"note": "Observation SIX6 reporter looks brighter after SAG."},
                        session_id=session["session_id"],
                        experiment_id="NK_Expt_31",
                    )
                )
                timeline = store.session_timeline(session["session_id"])
                entries = store.list_pending_entries()
                notes = store.workflow_notes(experiment_workflow_id("experiment:voice"))
            finally:
                main.settings = original_settings

        self.assertTrue(response["committed"])
        self.assertIsNotNone(response["session_event"])
        self.assertEqual(timeline[0]["event_type"], "observation")
        self.assertEqual(entries[0]["template"], "voice_assistant")
        self.assertTrue(response["workflow_update"]["updated"])
        self.assertIn("Voice observation", notes[0]["note"])


if __name__ == "__main__":
    unittest.main()
