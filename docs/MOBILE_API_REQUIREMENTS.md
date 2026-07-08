# Mobile API Requirements

This document lists the API surface a future ResearchOS mobile app will need. It is a planning document only; it does not require implementing Flutter or changing the current backend.

## API Principles

Mobile APIs should be:

- versioned, preferably under `/api/v1`
- authenticated
- HTTPS-only outside local development
- stable across mobile app releases
- explicit about sync status and provenance
- safe for offline draft workflows
- careful with Microsoft Graph tokens and OneNote data

The mobile app should call ResearchOS APIs rather than duplicating provider-specific logic.

## System and Readiness

Needed endpoints:

- `GET /health`
- `GET /status/deployment`
- `GET /status/providers`
- `GET /status/onenote-readiness`
- `GET /demo/status` for demos only

Mobile use:

- show server status
- show mobile/PWA access status
- show OneNote readiness
- show AI provider status
- show whether backend is local/demo/lab-server/cloud

Future additions:

- `GET /api/v1/status/mobile`
- `GET /api/v1/status/sync`

## Authentication and User Session

Current backend does not yet have full ResearchOS user accounts.

Future mobile endpoints needed:

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/users/me/settings`
- `PATCH /api/v1/users/me/settings`

Microsoft Graph/OneNote endpoints:

- `GET /auth/login`
- `GET /auth/callback`
- `GET /auth/status`
- `GET /status/onenote-readiness`

Mobile note:

ResearchOS app authentication should be separate from Microsoft Graph delegated auth. OneNote tokens should normally remain backend-side.

## Dashboard

Current endpoints:

- `GET /api/dashboard/daily?use_ai=false`
- `GET /demo/status`

Future mobile endpoints:

- `GET /api/v1/dashboard`
- `GET /api/v1/dashboard/today`
- `GET /api/v1/dashboard/recent-activity`
- `GET /api/v1/dashboard/quick-actions`

Mobile use:

- daily attention dashboard
- active session card
- pending workflow items
- recent imports
- quick actions

## Experiments

Current endpoints:

- `GET /experiments`
- `GET /experiments/{experiment_id}`
- `GET /experiments/{experiment_id}/workspace`
- `GET /experiments/{experiment_id}/timeline`
- `GET /experiments/{experiment_id}/images`
- `POST /experiments/compare`

Future mobile endpoints:

- `GET /api/v1/experiments`
- `GET /api/v1/experiments/{id}`
- `GET /api/v1/experiments/{id}/workspace`
- `GET /api/v1/experiments/{id}/timeline`
- `POST /api/v1/experiments/{id}/pin`
- `POST /api/v1/experiments/compare`

Mobile use:

- browse experiment list
- open workspace
- view timeline
- compare experiments
- see linked assets, statistics, literature, and Knowledge Graph entities

## Workflows

Current endpoints:

- `GET /workflows`
- `GET /workflows/definitions`
- `GET /workflows/{workflow_id}`
- `GET /workflows/experiment/{experiment_id}`
- `POST /workflows/{workflow_id}/transition`
- `POST /workflows/{workflow_id}/note`

Future mobile endpoints:

- `GET /api/v1/workflows`
- `GET /api/v1/workflows/definitions`
- `GET /api/v1/workflows/{id}`
- `POST /api/v1/workflows/{id}/transition`
- `POST /api/v1/workflows/{id}/note`
- `GET /api/v1/workflows/{id}/history`

Mobile use:

- show workflow progress
- show current stage
- add stage notes
- transition stage after explicit user action
- show blocking issues and next actions

## Sessions

Current endpoints:

- `POST /sessions/start`
- `POST /sessions/{id}/events`
- `POST /sessions/{id}/end`
- `GET /sessions`
- `GET /sessions/{id}`
- `GET /sessions/{id}/timeline`

Future mobile endpoints:

- `POST /api/v1/sessions/start`
- `POST /api/v1/sessions/{id}/events`
- `POST /api/v1/sessions/{id}/end`
- `GET /api/v1/sessions/active`
- `GET /api/v1/sessions/{id}`

Mobile use:

- start active lab session
- append dictated note
- append observation
- append treatment/media change
- attach image/file
- end session and optionally advance workflow

## New Experiment and Draft Entries

Current endpoints:

- `GET /entry-templates`
- `POST /entries/draft`
- `POST /entries/save-draft`
- `GET /entries`
- `GET /entries/{entry_id}`
- `DELETE /entries/{entry_id}`
- `GET /entries/{entry_id}/markdown`
- `GET /entries/{entry_id}/download`

Future mobile endpoints:

- `GET /api/v1/entry-templates`
- `POST /api/v1/entries/draft`
- `POST /api/v1/entries/save-draft`
- `GET /api/v1/entries`
- `GET /api/v1/entries/{id}`
- `PATCH /api/v1/entries/{id}`
- `POST /api/v1/entries/{id}/mark-ready`
- `POST /api/v1/entries/{id}/export`

Mobile use:

- dictate raw notes
- generate structured notebook entry
- review before save/export
- save pending draft in ResearchOS
- copy/download Markdown while OneNote write-back is pending

## Assistant and Copilot

Current endpoints:

- `POST /assistant/ask`
- `POST /assistant/knowledge`
- `POST /assistant/reason`
- `POST /assistant/plan-experiment`
- `POST /assistant/compare-literature`

Future mobile endpoints:

- `POST /api/v1/assistant/ask`
- `POST /api/v1/assistant/reason`
- `POST /api/v1/assistant/copilot`
- `POST /api/v1/assistant/plan-experiment`

Mobile use:

- ask questions by voice or text
- retrieve provenance-backed answers
- display source documents/assets
- plan follow-up experiments
- avoid hallucinated observations

## Knowledge Graph and Search

Current endpoints:

- `GET /knowledgegraph`
- `GET /knowledgegraph/search?q=...`
- `GET /knowledgegraph/entity/{entity}`
- `GET /knowledgegraph/type/{entity_type}`
- `GET /knowledgegraph/experiment/{experiment_id}`
- `GET /search/universal?q=...`
- `POST /search`

Future mobile endpoints:

- `GET /api/v1/search/universal`
- `GET /api/v1/knowledgegraph`
- `GET /api/v1/knowledgegraph/entity/{entity}`
- `GET /api/v1/knowledgegraph/experiment/{id}`

Mobile use:

- command-palette style global search
- entity pages
- experiment-linked graph view
- related assets and literature

## Assets and Providers

Current endpoints:

- `GET /assets`
- `GET /assets/{asset_id}`
- `POST /assets/register`
- `POST /assets/link`
- `GET /assets/{asset_id}/links`
- `DELETE /assets/{asset_id}`
- `GET /images`
- `GET /images/by-marker/{marker}`
- `GET /spreadsheets`
- `GET /statistics`
- `GET /papers`

Provider scan endpoints:

- `POST /providers/images/scan`
- `POST /providers/graphpad/scan`
- `POST /providers/spreadsheets/scan`
- `POST /ingest/papers`
- `POST /ingest/markdown`
- `POST /sync/onenote`

Future mobile endpoints:

- `POST /api/v1/assets/upload`
- `POST /api/v1/assets/register`
- `POST /api/v1/assets/{id}/link`
- `GET /api/v1/assets/{id}`
- `GET /api/v1/providers/status`
- `POST /api/v1/providers/{provider}/sync`

Mobile use:

- upload or register photos/files
- link assets to experiments
- scan server folders from lab workstation
- view parsed summaries

Important:

Mobile devices should not be expected to parse proprietary provider files locally. Upload/register first, then let backend providers parse.

## OneNote

Current endpoints:

- `GET /auth/login`
- `GET /auth/callback`
- `GET /auth/status`
- `GET /onenote/notebooks`
- `GET /onenote/sections`
- `GET /onenote/pages`
- `POST /sync/onenote`
- `GET /status/onenote-readiness`

Future mobile endpoints:

- `GET /api/v1/onenote/status`
- `POST /api/v1/onenote/sync`
- `GET /api/v1/onenote/notebooks`
- `GET /api/v1/onenote/sections`

Write-back remains future-only and requires separate approval:

- `POST /api/v1/onenote/pages/create`
- `POST /api/v1/onenote/pages/{id}/append`

Do not add `Notes.Create` or `Notes.ReadWrite` for the current read-only MVP.

## Notifications and Tasks

Future mobile endpoints:

- `GET /api/v1/tasks`
- `POST /api/v1/tasks`
- `PATCH /api/v1/tasks/{id}`
- `GET /api/v1/notifications`
- `POST /api/v1/devices/register`

Mobile use:

- workflow reminders
- imaging/timepoint reminders
- PI review notifications
- sync failure alerts

Push notifications require platform-specific setup and a privacy/security decision.

## Offline Draft Sync

Future mobile endpoints:

- `POST /api/v1/sync/drafts`
- `GET /api/v1/sync/status`
- `POST /api/v1/sync/conflicts/resolve`

Offline-capable mobile data should start narrow:

- pending notebook drafts
- voice transcripts
- session notes
- queued file uploads

Avoid offline OneNote write-back until review, conflict handling, and audit trails are mature.

## Security Requirements

Before mobile production:

- user authentication
- per-user authorization
- API tokens or sessions
- HTTPS
- CORS policy
- encrypted token storage
- audit logs
- rate limits
- input validation
- mobile session revocation

## Versioning Recommendation

Current routes can remain for development. Native mobile should use versioned routes:

```text
/api/v1/...
```

The backend can initially map `/api/v1` handlers to existing services, then gradually stabilize schemas for mobile release.
