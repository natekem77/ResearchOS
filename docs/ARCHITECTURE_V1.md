# ResearchOS Architecture V1 Review

This document reviews the current ResearchOS architecture after the expansion into providers, assets, experiments, sessions, workspaces, Knowledge Graph, Event Bus, deterministic agents, assistant workflows, PWA, and OneNote readiness.

The purpose is stabilization and architectural clarity. This review does not introduce new user-facing functionality.

## Current Architecture

ResearchOS is a local-first FastAPI application with a static browser UI served by the backend.

Current major layers:

- **FastAPI API and app composition**: `backend/app/main.py`
- **SQLite repository**: `backend/app/storage.py`
- **Provider modules**: Markdown, OneNote, GraphPad, microscopy/images, spreadsheets, literature
- **Derived intelligence services**: Knowledge Graph, Universal Search, Dashboard, Experiment Workspace, Research Copilot, Assistant, Scientific Reasoning, Planner
- **Event-driven workflow layer**: Event Bus and Automation Engine
- **Deterministic agent layer**: Scientific Agent Framework
- **Frontend/PWA**: `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`

The system is still intentionally local-first. SQLite stores canonical local records. ChromaDB is used initially for vector search where configured. Most advanced reasoning has deterministic fallback behavior when no AI provider is configured.

## Directory Structure Review

Current structure is understandable but is now showing pressure from rapid growth.

### Strong Areas

- Providers live in separate modules: `graphpad_provider.py`, `microscopy_provider.py`, `spreadsheet_provider.py`, `onenote_provider.py`, `literature_provider.py`, `markdown_provider.py`.
- Major derived services are separate: `global_knowledge_graph.py`, `experiment_workspace.py`, `statistics_engine.py`, `dashboard_service.py`, `research_copilot.py`, `universal_search.py`.
- New cross-cutting layers are isolated under `events/` and `agents/`.
- Tests are organized by capability in `backend/tests/`.

### Pressure Points

- `backend/app/main.py` is too large. It currently contains routing, response/request models, app-global service construction, status logic, helper functions, provider orchestration, and frontend-serving concerns.
- `backend/app/storage.py` is also large and owns many unrelated persistence concepts: documents, chunks, experiments, assets, pending entries, sessions, and session events.
- Provider scanning code repeats the same file discovery, duplicate prevention, asset registration, metadata merge, and experiment-ID inference pattern.
- There are overlapping graph concepts:
  - `knowledge_graph.py`
  - `global_knowledge_graph.py`
  - retinal ontology routes and helpers
  - frontend graph/entity pages
- `frontend/app.js` has grown into a large single-file application with routing, API calls, render functions, event handlers, and state management in one place.

## Provider Architecture

ResearchOS providers currently produce local records rather than owning downstream logic.

Current providers:

- **Markdown provider**: local demo notebook source.
- **OneNote provider**: Microsoft Graph read-only sync scaffold and page-to-document ingestion.
- **GraphPad provider**: scans GraphPad-related files, registers assets, parses CSV statistics where possible.
- **Microscopy/image provider**: filename-based metadata extraction and image asset registration.
- **Spreadsheet provider**: generic spreadsheet scanning, metadata extraction, entity detection, quantitative summary.
- **Literature provider**: local paper/PDF/text ingestion and metadata extraction.

### Duplicated Provider Logic

The scan providers repeat:

- configured folder resolution
- recursive supported-file discovery
- provider/path duplicate check
- experiment ID inference from filename
- metadata merge for existing assets
- asset registration
- scan result response shape

Recommendation: introduce a generic `FileProviderScanner` or `AssetProviderBase` with provider-specific hooks:

- `supported_extensions`
- `scan_folders(settings)`
- `asset_type_for_file(path)`
- `metadata_for_file(path)`
- `provider_name`

This would reduce duplicated code and make future providers such as sequencing, flow cytometry, CellProfiler, ImageJ, and PubMed easier to add.

## Data Model Review

Canonical local records are currently stored in SQLite:

- `documents`
- `chunks`
- `experiments`
- `pending_entries`
- `assets`
- `experiment_sessions`
- `session_events`

Derived concepts are mostly built dynamically:

- Knowledge Graph entities and relationships
- Experiment Workspaces
- Research Copilot summaries
- Universal Search index
- Dashboard cards
- Protocol objects

### Redundant or Overlapping Models

- `ResearchDocument`, document dicts, and document response models overlap but serve different layers.
- Asset metadata frequently contains provider-specific nested JSON with inconsistent structure.
- Experiment IDs exist as both internal IDs (`experiment:...`) and human IDs (`NK_Expt_31`), which is useful but should be formalized.
- Protocols are derived from documents/assets instead of a separate table. This is acceptable now, but versioning and history may eventually need a persisted protocol index.
- Knowledge Graph entity references are dynamically derived, while ontology endpoints still expose a narrower retinal-organoid-specific view.

### Recommended Simplifications

1. Introduce typed domain modules:
   - `models/documents.py`
   - `models/experiments.py`
   - `models/assets.py`
   - `models/sessions.py`
   - `models/events.py`
2. Split `SQLiteStore` into repository classes:
   - `DocumentRepository`
   - `ExperimentRepository`
   - `AssetRepository`
   - `EntryRepository`
   - `SessionRepository`
3. Standardize asset metadata around a few common keys:
   - `entities`
   - `statistics`
   - `provenance`
   - `parser`
   - `limitations`
4. Add a formal ID/reference utility for resolving internal IDs, human IDs, file-derived IDs, and aliases.

## API Review

The API surface is broad but mostly grouped by tags.

Recommended service groups:

- **System/status**: `/health`, `/status/providers`, `/status/deployment`, `/status/onenote-readiness`, `/status/automation`
- **Agents/automation**: `/agents`, `/agents/{id}/enable`, `/agents/{id}/disable`
- **Authentication/OneNote**: `/auth/*`, `/onenote/*`, `/sync/onenote`
- **Ingestion/providers**: `/ingest/*`, `/providers/*/status`, `/providers/*/scan`
- **Documents/literature**: `/documents`, `/papers`
- **Experiments/sessions**: `/experiments`, `/experiments/{id}/workspace`, `/experiments/{id}/timeline`, `/sessions`
- **Assets/data/images/statistics**: `/assets`, `/spreadsheets`, `/images`, `/statistics`
- **Knowledge/ontology/graph**: `/knowledgegraph`, `/graph`, `/api/compounds`, `/api/markers`, `/ontology`
- **Assistant/reasoning/planning**: `/assistant/*`, `/chat`, `/search`, `/search/universal`
- **Entries/templates**: `/entries`, `/entries/draft`, `/entry-templates`
- **Demo**: `/demo/reset`, `/demo/status`

### API Refactoring Recommendation

Move route groups out of `main.py` into FastAPI routers:

- `routers/system.py`
- `routers/auth.py`
- `routers/providers.py`
- `routers/documents.py`
- `routers/experiments.py`
- `routers/sessions.py`
- `routers/assets.py`
- `routers/knowledge_graph.py`
- `routers/assistant.py`
- `routers/settings.py`
- `routers/demo.py`

This is the highest-value structural refactor because it reduces risk in future milestones.

## Knowledge Graph

`global_knowledge_graph.py` is the correct architectural direction: it dynamically builds from existing SQLite records and provider metadata instead of maintaining a duplicate graph database.

Strengths:

- Provider-agnostic entity extraction from metadata.
- Case-insensitive lookup and alias handling.
- Relationships across experiments, documents, literature, assets, statistics, pending entries, and sessions.
- Cache fingerprinting to avoid rebuilding on every query.

Risks:

- Graph building scans documents, experiments, assets, and pending entries. This will become expensive with tens of thousands of records.
- Some graph/entity logic overlaps with `knowledge_graph.py` and retinal ontology helpers.
- Entity typing depends heavily on provider metadata quality.

Recommendations:

- Make `global_knowledge_graph.py` the canonical graph layer.
- Deprecate or fold older graph/ontology helpers into compatibility adapters.
- Add incremental graph invalidation by object type once data volume grows.
- Persist optional graph snapshots only after the dynamic version becomes too slow.

## Event Bus

The Event Bus provides synchronous in-process publishing:

- `subscribe()`
- `publish()`
- `unsubscribe()`
- event ordering
- duplicate suppression by event ID
- in-memory history for diagnostics

Current event producers include ingestion, provider scans, asset registration/linking, session updates, draft creation, OneNote sync, and experiment extraction.

### Event Flow Review

Current provider flow is partly event-driven:

```text
Provider endpoint
-> provider/storage operation
-> publish event
-> AutomationEngine refreshes caches
-> derived update events
-> AgentManager dispatches deterministic agents
```

This is acceptable for the synchronous MVP, but providers still directly write to SQLite. That is fine: publishing events should replace direct calls to derived services, not replace persistence.

### Event Flow Issues

- Some derived services still rebuild from SQLite on demand rather than reacting incrementally to events.
- Event publishing currently lives mostly in API route handlers. Future provider modules should publish events themselves or return event intents to keep route code thin.
- Automation Engine and AgentManager both subscribe to the Event Bus. Their responsibilities are close and need clear boundaries.

Recommended boundary:

- **AutomationEngine**: generic cache invalidation and derived update events.
- **AgentManager**: deterministic domain-specific workflow reactions.

## Agent Framework

The Scientific Agent Framework is deterministic, not an LLM multi-agent system.

Current agents:

- `NotebookAgent`
- `SessionAgent`
- `StatisticsAgent`
- `KnowledgeGraphAgent`
- `ImageAgent`
- `LiteratureAgent`
- `ProtocolAgent`

Strengths:

- Registration, enable/disable, and listing are implemented.
- Agents run in deterministic registration order.
- Failures are isolated and reported.
- Settings UI exposes status and controls.

Risks:

- Overlap between AutomationEngine and agents may grow.
- Agents currently mostly track/refresh rather than perform richer deterministic work.
- Agent status is process-local and resets on restart.

Recommendations:

- Persist agent enabled/disabled state in SQLite or config.
- Keep agents small and event-specific.
- Do not let agents become hidden controllers for provider-specific behavior.
- Add a durable agent run log only after the workflow stabilizes.

## Experiment Workspace

Experiment Workspace is the right central object for ResearchOS. It aggregates:

- experiment metadata
- notebook/document evidence
- timeline
- microscopy/images
- GraphPad assets
- spreadsheets
- statistics
- literature
- Knowledge Graph entities
- related experiments
- Research Copilot summary
- provenance

Risks:

- Workspace generation gathers from several stores/services and can become expensive.
- Some provider-specific filtering is still embedded in workspace assembly.
- Provenance is present but not yet consistently normalized across all sections.

Recommendations:

- Introduce a `WorkspaceService` class with cache and event invalidation.
- Standardize workspace section schema.
- Use Knowledge Graph as the main aggregation source where possible.
- Move provider-specific filtering into provider metadata and generic asset classifiers.

## Statistics Engine

The statistics layer is valuable and already more rigorous than raw metadata display.

Strengths:

- Standardized statistical result model.
- Robust p-value column detection.
- Compact summaries for UI/assistant use.
- GraphPad and spreadsheet integration.

Risks:

- Spreadsheet and GraphPad statistics have separate parsing paths.
- Compact summaries and interpretations may duplicate logic.
- Statistical claims are only as good as parsed column metadata.

Recommendations:

- Make `statistics_engine.py` the single canonical interpretation layer.
- Have GraphPad and spreadsheet providers emit raw/parsed quantitative metadata only.
- Route all compact summaries through the statistics engine.
- Add fixtures from common R/Python/Prism exports.

## Assistant and Reasoning

Current assistant capabilities include:

- `/assistant/ask`
- `/assistant/reason`
- `/assistant/knowledge`
- `/assistant/plan-experiment`
- `/assistant/compare-literature`
- `/chat`

Strengths:

- Local deterministic fallback is consistently supported.
- AI provider is optional and configurable.
- Knowledge Graph evidence is increasingly first-class.
- Assistant answers distinguish evidence and limitations better than early versions.

Risks:

- `research_assistant.py` is large and contains retrieval, filtering, local answer formatting, image/statistics/literature handling, and AI prompt handling.
- Several assistant paths collect context separately.
- Prompt construction and evidence packaging are not centralized.

Recommendations:

- Create a shared `EvidenceCollector`.
- Create a shared `AnswerBuilder` for local deterministic answers.
- Keep AI calls in provider-specific adapters only.
- Have assistant modes consume Experiment Workspace or Knowledge Graph evidence instead of each building context independently.

## Deployment

Current deployment supports:

- local WSL/Linux development scripts
- demo startup scripts
- lab-server planning docs
- `/status/deployment`
- environment-driven host/port/public URL

Strengths:

- Local demo workflow is clear.
- Lab-server mode is documented.
- OneNote redirect implications are documented.

Risks:

- No production process manager is included yet.
- SQLite is acceptable for local/lab server MVP but will need backup/locking guidance.
- Authentication beyond Microsoft delegated auth is not yet a full app-login model.

Recommendations:

- Add a deployment profile checklist for local, lab workstation, and hosted modes.
- Add database backup/restore commands.
- Add reverse proxy/HTTPS examples before broader lab use.
- Add app-level access control before shared deployment with sensitive data.

## PWA

The PWA foundation includes:

- manifest
- service worker skeleton
- responsive layout
- mobile navigation
- mobile-friendly new entry/session workflows

Risks:

- Offline behavior is only a skeleton.
- Static frontend remains a large single JS file.
- Mobile testing is not automated.

Recommendations:

- Add Playwright smoke checks at mobile widths.
- Split frontend JS into route/view modules.
- Keep offline behavior conservative until data-sync semantics are clear.

## OneNote Integration

Current OneNote integration is read-only:

- Microsoft Graph auth scaffold
- public-client delegated auth
- `/onenote/notebooks`
- `/onenote/sections`
- `/onenote/pages`
- `/sync/onenote`
- readiness and Azure setup docs

Strengths:

- Correctly avoids client secret for local/public client mode.
- Keeps OneNote as official notebook.
- Write-back remains disabled pending separate approval.

Risks:

- UCSD tenant approval remains external.
- Redirect URI compatibility becomes more complex in lab-server/PWA mode.
- OneNote page HTML conversion will need more test fixtures.

Recommendations:

- Keep read-only MVP permissions minimal.
- Add a dedicated OneNote sync service class separate from routes.
- Add fixtures for representative OneNote HTML.
- Treat write-back as a separate permission and architecture milestone.

## Performance Review

Expensive operations:

- Knowledge Graph full rebuild over documents, experiments, assets, pending entries.
- Universal Search index rebuild over all documents, experiments, assets, graph entities.
- Experiment Workspace generation with linked assets, graph, literature, statistics, and copilot.
- Dashboard generation, especially when it invokes graph/candidate copilot summaries.
- Repeated `store.list_assets()`, `store.list_experiments()`, and `get_all_research_documents()` across services.
- Large frontend render pass after every refresh.

Current caching:

- Knowledge Graph fingerprint cache.
- Universal Search fingerprint cache.
- Dashboard fingerprint cache.
- Event/agent-driven refresh hooks.

Recommended caching:

1. Add a repository-level cheap data version table that increments on writes.
2. Replace count-based fingerprints with data-version fingerprints.
3. Cache Experiment Workspace by experiment ID.
4. Cache compact statistics interpretations by asset ID.
5. Add query-level pagination for documents/assets/experiments/sessions.
6. Avoid full frontend refresh after every small action; update local state incrementally where safe.

## Testing Review

Current test coverage is broad and useful.

Test files cover:

- agent framework
- daily dashboard
- deployment status
- entry drafting
- event bus/automation
- experiment comparison
- experiment extraction
- experiment sessions
- experiment workspace
- global knowledge graph
- knowledge graph assistant
- literature comparison/provider
- OneNote readiness
- protocol intelligence
- research assistant
- research copilot
- spreadsheet provider
- universal search

Current suite count at this review: 66 backend unit tests.

Missing or thin coverage:

- FastAPI route tests for most endpoint groups.
- End-to-end provider scan plus event/agent update tests.
- OneNote HTML conversion fixtures.
- GraphPad/Prism export variations beyond current samples.
- Spreadsheet parser fixtures for R/Python/Excel/flow cytometry/ImageJ exports.
- Frontend tests.
- PWA/mobile layout tests.
- Performance tests over synthetic large datasets.
- Migration/backward compatibility tests for SQLite schema changes.

Recommendations:

- Add route-level tests using FastAPI TestClient once the local harness issue is resolved.
- Add integration tests for provider scan -> events -> agents -> graph/search/dashboard.
- Add synthetic performance tests for 10k experiments and 100k assets.
- Add frontend smoke tests with Playwright.

## Technical Debt List

Priority 0: Stabilization

1. Split `main.py` into routers.
2. Split `storage.py` into repositories.
3. Add a SQLite schema/migration strategy.
4. Resolve local TestClient/live smoke reliability in this environment.

Priority 1: Provider Foundation

1. Extract generic file-provider scanner.
2. Standardize provider result objects.
3. Standardize asset metadata schema.
4. Move event publication closer to provider/service boundaries.

Priority 2: Derived Data

1. Make `global_knowledge_graph.py` the single canonical graph layer.
2. Deprecate duplicate graph/ontology logic or wrap it as compatibility views.
3. Add data-version-based cache invalidation.
4. Add workspace cache with event invalidation.

Priority 3: Assistant and Evidence

1. Extract shared evidence collection.
2. Standardize citation/provenance objects.
3. Route assistant/reasoning/copilot through Knowledge Graph and Workspace objects.
4. Add prompt/evidence tests for every assistant mode.

Priority 4: Frontend

1. Split `frontend/app.js` into modules.
2. Add route-level frontend tests.
3. Add mobile viewport checks.
4. Replace full refresh cycles with local state updates where safe.

## Recommended Roadmap

### v0.3: Stabilized Architecture

- Split FastAPI routers.
- Split storage repositories.
- Introduce schema migrations.
- Create generic file-provider scanner.
- Standardize event publication pattern.
- Add route-level tests for critical endpoints.

### v0.4: Scalable Knowledge Layer

- Make Global Knowledge Graph the canonical relationship layer.
- Add data-version cache invalidation.
- Cache Experiment Workspaces.
- Add large synthetic dataset performance tests.
- Add richer provenance normalization.

### v0.5: Lab-Ready Workflow

- Improve sessions as the primary daily workflow.
- Add voice/session summaries.
- Add app-level access control for lab-server mode.
- Add backup/restore tooling.
- Add Playwright PWA/mobile tests.
- Harden OneNote read-only sync with real HTML fixtures.

### v1.0: Production-Ready Lab Knowledge System

- Stable local/lab-server deployment path.
- Durable event log and optional async worker.
- Provider SDK for future sources.
- Read-only OneNote integration approved and tested.
- Auditable write-back design gated behind separate permissions.
- Documented data privacy/security posture.
- Full test matrix across providers, graph, workspace, assistant, and UI.

## Conclusion

ResearchOS has evolved from a demo notebook companion into a credible local-first research knowledge platform. The core architectural direction is sound: providers emit metadata, SQLite stores canonical local records, the Knowledge Graph derives relationships, Workspaces aggregate context, Events and Agents coordinate updates, and Assistants consume grounded evidence.

The next engineering priority should be modularization and stabilization, not feature expansion. The highest-impact work is splitting routers/repositories, extracting generic provider scanning, consolidating graph layers, and formalizing cache invalidation.
