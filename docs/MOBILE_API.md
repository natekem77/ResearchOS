# Mobile API

ResearchOS exposes `/mobile/*` endpoints for a future Flutter, iPhone, Android, or tablet app.

The mobile app should be a thin client. It should not need to understand provider internals, Knowledge Graph construction, statistics parsing, event bus mechanics, agents, or OneNote implementation details.

## Response Design Principles

Mobile responses are:

- compact
- display-ready
- low-bandwidth
- shallow where possible
- labeled with routes/actions
- limited to compact provenance
- free of raw provider metadata dumps

Full/raw metadata remains available through the existing desktop/backend endpoints.

## Endpoints

Status:

```bash
curl http://127.0.0.1:8001/mobile/status
```

Dashboard:

```bash
curl http://127.0.0.1:8001/mobile/dashboard
```

Search:

```bash
curl "http://127.0.0.1:8001/mobile/search?q=SAG"
```

Experiments:

```bash
curl http://127.0.0.1:8001/mobile/experiments
curl http://127.0.0.1:8001/mobile/experiments/NK_Expt_31
curl http://127.0.0.1:8001/mobile/experiments/NK_Expt_31/workspace
curl http://127.0.0.1:8001/mobile/experiments/NK_Expt_31/timeline
```

Sessions:

```bash
curl http://127.0.0.1:8001/mobile/sessions
curl http://127.0.0.1:8001/mobile/sessions/active
curl -X POST http://127.0.0.1:8001/mobile/sessions/start \
  -H "Content-Type: application/json" \
  -d '{"experiment_id":"NK_Expt_31","notes":"Started from mobile."}'
curl -X POST http://127.0.0.1:8001/mobile/sessions/{session_id}/note \
  -H "Content-Type: application/json" \
  -d '{"note_type":"observation","text":"Organoids look healthy today."}'
curl -X POST http://127.0.0.1:8001/mobile/sessions/{session_id}/end \
  -H "Content-Type: application/json" \
  -d '{"notes":"Ended from mobile."}'
```

Knowledge and assistant:

```bash
curl http://127.0.0.1:8001/mobile/knowledge/entity/SAG
curl -X POST http://127.0.0.1:8001/mobile/assistant/ask \
  -H "Content-Type: application/json" \
  -d '{"message":"Which experiments used SAG?"}'
curl -X POST http://127.0.0.1:8001/mobile/assistant/copilot \
  -H "Content-Type: application/json" \
  -d '{"question":"What should I know about SAG?"}'
```

Settings and auth:

```bash
curl http://127.0.0.1:8001/mobile/settings
curl http://127.0.0.1:8001/mobile/auth/me
```

## Expected Flutter Screens

Future Flutter screens can map directly to mobile endpoints:

- Home: `/mobile/dashboard`
- Search: `/mobile/search`
- Experiments: `/mobile/experiments`
- Experiment detail: `/mobile/experiments/{id}`
- Experiment workspace: `/mobile/experiments/{id}/workspace`
- Session bench mode: `/mobile/sessions/active`, `/mobile/sessions/start`, note/end endpoints
- Knowledge entity: `/mobile/knowledge/entity/{entity}`
- Assistant: `/mobile/assistant/ask`
- Copilot: `/mobile/assistant/copilot`
- Settings: `/mobile/settings`
- Account: `/mobile/auth/me`

## Authentication Notes

Current local demo mode does not force login. `/mobile/auth/me` returns the same safe compact user information as the backend app user scaffold.

Future mobile deployment should use Microsoft identity as ResearchOS app login, with secure session handling and workspace permissions enforced on the backend.

## OneNote Notes

OneNote delegated Graph auth remains separate from ResearchOS app login.

The mobile API does not expose Graph tokens or OneNote internals. It surfaces only readiness/status through `/mobile/settings`.

## Future Offline Sync Plan

Offline/mobile sync should eventually support:

- local draft cache
- queued session notes
- conflict handling
- background upload when online
- read-only cached workspaces
- explicit user review before any OneNote write-back

Offline mode should not assume Microsoft tokens are available.
