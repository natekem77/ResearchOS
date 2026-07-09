# Voice Laboratory Assistant

The ResearchOS Voice Assistant is designed for fast hands-free laboratory documentation. It is not an AI conversation feature. The first workflow turns a reviewed transcript into structured ResearchOS records.

## Safety Model

Voice input always follows a review-before-save workflow:

1. Capture or type a transcript.
2. Draft a voice command with `POST /voice/draft`.
3. Review the transcript, command type, parsed fields, and suggested corrections.
4. Confirm with `POST /voice/confirm`.

ResearchOS never silently modifies the transcript. Parsed fields and Research Copilot suggestions are stored separately from the original wording.

## Supported Commands

- Start experiment
- Start session
- End session
- Observation
- Treatment
- Media change
- Collection
- Imaging
- Custom note

## Speech Provider Abstraction

The backend exposes a `SpeechProvider` abstraction in `backend/app/voice_assistant.py`.

Current provider:

- `placeholder`: accepts typed or pasted transcripts. No cloud speech is required.

Planned providers:

- iOS speech
- Android speech
- OpenAI
- Whisper
- Apple Speech
- Android Speech

Provider output is normalized into transcript, provider name, confidence, and metadata. This keeps mobile, desktop, and future local speech implementations decoupled from session and notebook storage.

## Backend Commit Workflow

`POST /voice/draft` does not write anything.

`POST /voice/confirm` can create:

- Session event
- Session timeline event
- Pending notebook draft
- Workflow note when the session is linked to a known extracted experiment

The pending notebook draft preserves the confirmed transcript and parsed command. OneNote write-back remains disabled.

## API Examples

Draft a command:

```bash
curl -s -X POST http://127.0.0.1:8001/voice/draft \
  -H "Content-Type: application/json" \
  -d '{"transcript":"Observation SIX6 reporter looks brighter after SAG.","session_id":"session:...","experiment_id":"NK_Expt_31"}'
```

Confirm the command:

```bash
curl -s -X POST http://127.0.0.1:8001/voice/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "voice_session_id":"voice-session:...",
    "command_type":"observation",
    "transcript":"Observation SIX6 reporter looks brighter after SAG.",
    "parsed_fields":{"note":"Observation SIX6 reporter looks brighter after SAG."},
    "session_id":"session:...",
    "experiment_id":"NK_Expt_31",
    "create_notebook_draft":true
  }'
```

List speech providers:

```bash
curl -s http://127.0.0.1:8001/voice/speech-providers
```

## Flutter Bench Mode

Bench Mode includes a large microphone control:

- Hold to speak.
- Preview/edit transcript.
- Preview parsed command.
- Confirm and save.

The current mobile workflow uses a placeholder transcript if browser/device speech is unavailable. Typed notes remain supported.

## Research Copilot

Research Copilot may later suggest corrections such as missing dose, missing compound, or ambiguous command type. Those suggestions are advisory only. The user must confirm before anything is saved.

## Future Work

- Native iOS/Android speech capture.
- Local Whisper transcription.
- Optional cloud transcription with explicit privacy settings.
- Voice-driven session start/end.
- Voice-driven inventory usage and barcode workflows.
- OneNote write-back after separate UCSD IT approval for create/write permissions.
