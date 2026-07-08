# ResearchOS Tech Stack

This document describes the current and intended technical stack for ResearchOS.

## Frontend

Current:

- Plain HTML/CSS/JavaScript
- Static files served by FastAPI
- Responsive dashboard UI
- PWA manifest and service worker skeleton

Near-term recommendations:

- Split `frontend/app.js` into view modules.
- Add Playwright tests for desktop and mobile.
- Keep the frontend lightweight until workflow requirements stabilize.

Future options:

- React/Vite or another component framework if UI complexity continues to grow.
- Offline-aware PWA workflows after data sync semantics are designed.

## Backend

Current:

- Python 3.12
- FastAPI
- Pydantic response/request models
- Uvicorn for local development
- Modular service files under `backend/app/`

Near-term recommendations:

- Split `main.py` into routers.
- Move request/response schemas into dedicated modules.
- Keep services provider-agnostic.

## Database

Current:

- SQLite
- Tables for documents, chunks, experiments, pending entries, assets, sessions, and session events

Near-term recommendations:

- Add schema migrations.
- Split `SQLiteStore` into repositories.
- Add backup/restore scripts.
- Add data-version table for cache invalidation.

Future options:

- PostgreSQL for multi-user/cloud deployments.
- Object storage for large files.

## Knowledge Graph

Current:

- In-memory graph built dynamically from SQLite records and provider metadata
- Cached by fingerprint
- Entity and relationship queries exposed through `/knowledgegraph`

Near-term recommendations:

- Make `global_knowledge_graph.py` the canonical graph layer.
- Deprecate older graph/ontology logic into compatibility adapters.
- Add incremental invalidation.

Future options:

- Persisted graph snapshots.
- Dedicated graph database only if dynamic SQLite-derived graph becomes insufficient.

## Event Bus

Current:

- Synchronous in-process EventBus
- Event models under `backend/app/events/`
- AutomationEngine for cache refresh and derived update events

Near-term recommendations:

- Keep events metadata-only.
- Move event publishing closer to provider/service boundaries.
- Add durable event log when workflows stabilize.

Future options:

- Async workers
- SQLite-backed queue
- Redis/RQ/Celery for larger deployments

## Scientific Agents

Current:

- Deterministic agent framework
- AgentManager
- Notebook, Session, Statistics, KnowledgeGraph, Image, Literature, Protocol agents

Near-term recommendations:

- Persist enabled/disabled status.
- Add agent run logs.
- Keep agents deterministic and small.

## Providers

Current:

- Markdown
- OneNote
- GraphPad
- Microscopy/images
- Spreadsheets
- Literature/local papers

Future providers:

- PubMed
- Benchling
- ImageJ/Fiji
- CellProfiler
- Flow cytometry
- Bulk RNA-seq
- scRNA-seq
- Seurat
- Scanpy
- Cell Ranger

Provider design:

- Providers emit documents, assets, metadata, and events.
- Providers should not directly call downstream services.

## AI

Current:

- Configurable AI provider abstraction
- OpenAI-compatible support
- Ollama/LM Studio-compatible base URL support
- placeholder Claude provider
- deterministic local fallbacks

Principles:

- AI is optional.
- AI must be grounded in local evidence.
- AI should never silently edit official notebooks.

Future:

- provider-specific model presets
- structured output validation
- local model profiles
- per-workflow AI enable/disable controls

## Mobile

Current:

- Responsive web UI
- PWA manifest
- service worker skeleton
- mobile navigation

Future:

- richer PWA install flow
- offline draft capture
- voice capture workflows
- mobile image/file attachment
- lab-server access guidance

## Deployment

Current:

- WSL/Linux development scripts
- local demo script
- lab-server deployment documentation
- `/status/deployment`

Future:

- desktop packaging
- lab server service unit
- HTTPS reverse proxy docs
- Docker Compose
- cloud deployment profile
- app-level auth and permissions

## Authentication

Current:

- Microsoft Graph delegated auth using MSAL public client flow
- OneNote read-only scopes
- readiness checks for Azure redirect URI and permissions

Future:

- app-level user login for shared lab server
- role-based permissions
- PI review/approval roles
- optional future OneNote write-back permissions after separate approval

## Testing

Current:

- Python unit tests
- smoke test script
- py_compile checks
- frontend JS syntax check

Future:

- FastAPI route tests
- Playwright frontend tests
- mobile viewport tests
- large synthetic dataset performance tests
- provider fixture libraries
