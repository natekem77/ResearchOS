# Experiment Sessions

Experiment Sessions are the live workflow container for conducting experiments in ResearchOS.

A session represents one active laboratory session. Notes, observations, treatments, media changes, files, images, GraphPad imports, spreadsheet imports, and notebook draft updates attach to the session timeline.

Future voice capture, OneNote write-back, reminders, notifications, and AI assistants should attach to sessions instead of floating independently.

## Session Model

Each session contains:

- `session_id`
- `experiment_id`
- `start_time`
- `end_time`
- `status`
- `notes`
- `voice_transcripts`
- `assets`
- `timeline`

Timeline events include:

- `voice_note`
- `manual_note`
- `observation`
- `treatment`
- `media_change`
- `image_imported`
- `file_imported`
- `graphpad_imported`
- `spreadsheet_imported`
- `notebook_draft_updated`

## API

Start a session:

```bash
curl -X POST http://127.0.0.1:8001/sessions/start \
  -H "Content-Type: application/json" \
  -d '{"experiment_id":"NK_Expt_31","notes":"Starting D32 staining session."}'
```

List sessions:

```bash
curl http://127.0.0.1:8001/sessions
```

Open a session:

```bash
curl http://127.0.0.1:8001/sessions/session:example
```

Append an observation:

```bash
curl -X POST http://127.0.0.1:8001/sessions/session:example/events \
  -H "Content-Type: application/json" \
  -d '{"event_type":"observation","title":"SIX6 staining","content":"SIX6 signal appeared stronger in SAG + GRKi."}'
```

Append a treatment:

```bash
curl -X POST http://127.0.0.1:8001/sessions/session:example/events \
  -H "Content-Type: application/json" \
  -d '{"event_type":"treatment","title":"Added SAG + GRKi","content":"Added SAG and GRK inhibitor to rescue condition."}'
```

Append an image event:

```bash
curl -X POST http://127.0.0.1:8001/sessions/session:example/events \
  -H "Content-Type: application/json" \
  -d '{"event_type":"image_imported","title":"D32 SIX6/BRN3B image","asset_id":"asset:example"}'
```

View timeline:

```bash
curl http://127.0.0.1:8001/sessions/session:example/timeline
```

End a session:

```bash
curl -X POST http://127.0.0.1:8001/sessions/session:example/end \
  -H "Content-Type: application/json" \
  -d '{"notes":"Session complete."}'
```

## UI

The Sessions page shows:

- current active session
- session timer
- timeline
- recent notes
- files
- images
- today's sessions

The dashboard shows the current session and today's session count.

## Event Bus Integration

Session actions publish events into the ResearchOS automation engine:

- `SessionStarted`
- `SessionEventAppended`
- `SessionEnded`

Session timeline events can also trigger provider-style events:

- image events publish `ImageImported`
- file events publish `AssetRegistered`
- GraphPad events publish `GraphPadParsed`
- spreadsheet events publish `SpreadsheetParsed`
- notebook draft updates publish `DraftCreated`

This keeps sessions provider-agnostic while still updating downstream Knowledge Graph, Workspace, Timeline, Dashboard, and Search layers.

## Design Direction

Sessions should become the primary interaction surface for active lab work.

Planned extensions:

- direct browser voice capture into session timelines
- automatic asset attachment during a session
- reminders and timers
- AI session summaries
- OneNote draft creation from session timeline
- OneNote write-back after separate UCSD approval
- notifications for active or stale sessions
