# Bench Mode

Bench Mode is the primary mobile workflow for scientists actively performing experiments.

Design question:

```text
Can a scientist perform this action while standing at the bench using one hand?
```

The mobile app should feel like a laboratory companion, not a database browser.

## Philosophy

Bench Mode prioritizes:

- minimal typing
- large touch targets
- portrait-first layout
- high-contrast, readable controls
- one-handed operation
- glove-friendly spacing
- fast timestamped capture
- no duplicated backend science logic

The mobile app sends compact actions to the ResearchOS `/mobile/*` API. The backend owns provider logic, workflows, timelines, Knowledge Graph relationships, statistics, assets, OneNote readiness, and future sync behavior.

## Current Prototype

Bench Mode is implemented in the Flutter scaffold at:

```text
mobile/researchos_mobile/lib/screens/bench_mode_screen.dart
```

It is the Home tab in the mobile app. When an experiment session is active, it shows:

- active experiment/session
- workflow stage when available
- session status/start time
- quick summary
- compact Research Copilot alerts
- large action buttons

Current action buttons:

- Voice Note
- Observation
- Media Change
- Treatment
- Capture Image
- Attach File
- Add GraphPad
- Add Sequencing
- Finish Session

The current prototype records timestamped session notes through:

```http
POST /mobile/sessions/{session_id}/observation
POST /mobile/sessions/{session_id}/treatment
POST /mobile/sessions/{session_id}/media-change
POST /mobile/sessions/{session_id}/voice-note
POST /mobile/sessions/{session_id}/attach-placeholder
```

Each endpoint appends a session timeline event and publishes a ResearchOS EventBus event through the existing session-event pipeline.

The prototype does not yet access the device microphone, camera, file picker, barcode scanner, microscope, or sequencing instrument.

## Voice Workflow

Current behavior:

- Voice Note immediately calls `POST /mobile/sessions/{session_id}/voice-note`.
- If speech recognition is unavailable, it appends a placeholder transcript to the active session.
- This validates the interaction flow without requiring device speech APIs.

Future behavior:

1. Tap Voice Note.
2. Start speech capture immediately.
3. Transcribe locally or through a reviewed speech provider.
4. Show transcript for quick review.
5. Append transcript to the session timeline.
6. Optionally generate a structured notebook draft.
7. Later, after approval, write reviewed entries to OneNote.

Voice capture must never silently write final notebook content. The scientist reviews before saving or exporting.

## Camera Workflow

Current behavior:

- Capture Image calls `POST /mobile/sessions/{session_id}/attach-placeholder` with `attachment_type="image"`.
- No real camera or gallery access is implemented yet.

Future behavior:

1. Tap Capture Image.
2. Open camera or gallery.
3. Attach image to the active session.
4. Register the image as a ResearchOS asset.
5. Infer experiment ID, timepoint, markers, and source when possible.
6. Add a timeline event.
7. Make the image available to the Knowledge Graph, Experiment Workspace, and Research Copilot.

Microscope integrations should follow the same asset workflow rather than implementing separate logic.

## Treatment Workflow

Current behavior:

- Treatment opens a bottom sheet for compound, dose, units, time, and notes.
- It calls `POST /mobile/sessions/{session_id}/treatment`.
- The backend appends a timestamped treatment event to the session timeline.

Future behavior:

- structured treatment records
- reagent inventory links
- dose validation
- reminder scheduling
- protocol-stage awareness
- OneNote draft generation

## Media Change Workflow

Current behavior:

- Media Change opens a bottom sheet for media type and notes.
- It calls `POST /mobile/sessions/{session_id}/media-change`.
- The backend appends a timestamped media-change event to the session timeline.

Future behavior:

- one-tap recurring media change templates
- scheduled reminders
- incubator or plate metadata
- protocol compliance checks

## Research Copilot Alerts

Bench Mode may show compact suggestions such as:

- Media change due.
- Statistics still pending.
- GraphPad not uploaded.
- Notebook observation missing.

Alerts must be grounded in ResearchOS data. They should not invent experimental observations or imply work was done when it was not recorded.

## OneNote Write-back

Bench Mode should eventually feed the reviewed notebook-entry workflow:

```text
session events -> structured draft -> scientist review -> OneNote write-back
```

Write-back remains disabled until UCSD IT approves future create/write permissions such as `Notes.Create` or `Notes.ReadWrite`.

The read-only MVP permissions must remain separate from future write-back approval.

## Future Integrations

Bench Mode is the integration point for:

- voice dictation
- camera/gallery import
- barcode scanning
- file import
- GraphPad upload
- sequencing upload
- treatment reminders
- protocol step tracking
- OneNote draft generation
- OneNote write-back after approval
- session-aware Research Copilot
- notifications

Future providers should publish events and let the backend event bus, Knowledge Graph, timelines, workspaces, and dashboard update from those events.
