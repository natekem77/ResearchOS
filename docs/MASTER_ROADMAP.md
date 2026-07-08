# ResearchOS Master Roadmap

This is the master development roadmap for ResearchOS. It organizes the platform into epics and proposes milestones through v1.0.

ResearchOS should grow deliberately. The next phase should stabilize architecture before adding too many new features.

## Epic 1: Knowledge Platform

### Description

The Knowledge Platform is the core layer that connects notebook entries, documents, literature, assets, search, timelines, workspaces, and the Knowledge Graph.

### Goals

- Make every research object searchable and connected.
- Make the Global Knowledge Graph the canonical relationship layer.
- Make Experiment Workspace the primary evidence object.
- Preserve provenance for every displayed fact.

### Dependencies

- SQLite repository layer
- provider metadata
- event bus
- asset graph
- universal search

### Priority

Critical.

### Estimated Difficulty

High.

### Milestones

#### v0.3

- Split API routers and storage repositories.
- Canonicalize Global Knowledge Graph.
- Standardize provenance objects.
- Add route tests for documents, experiments, assets, graph, and search.

#### v0.4

- Add data-version cache invalidation.
- Cache Experiment Workspace by experiment ID.
- Add large synthetic graph/search tests.
- Consolidate old graph/ontology helpers into compatibility views.

#### v0.5

- Add richer timeline aggregation.
- Add relationship confidence scoring.
- Add saved/pinned workspace views.
- Add advanced entity pages.

#### v0.6

- Add cross-project/workspace support.
- Add graph export/import.
- Add knowledge snapshots for reports.

#### v0.7

- Add semantic relationship detection.
- Add lab-wide analytics dashboards.
- Add controlled vocabulary/ontology management.

#### v0.8

- Add multi-lab/project boundaries.
- Add full provenance explorer.

#### v0.9

- Add knowledge graph diffing over time.
- Add graph-backed manuscript evidence packs.

#### v1.0

- Stable Knowledge Platform API.
- Scalable graph/search/workspace performance.
- Complete provenance path from claim to source.

### Future Ideas

- Graph-based hypothesis recommendations.
- Knowledge gap detection.
- Experiment lineage maps.
- Dataset-to-paper traceability.

## Epic 2: Scientific Intelligence

### Description

Scientific Intelligence includes Research Copilot, reasoning, hypothesis generation, protocol intelligence, statistics interpretation, similarity search, and grounded AI synthesis.

### Goals

- Provide evidence-grounded scientific assistance.
- Never invent observations.
- Support deterministic local fallback.
- Use AI only as a synthesis layer over retrieved evidence.

### Dependencies

- Knowledge Graph
- Experiment Workspace
- Statistics Engine
- literature ingestion
- asset graph
- AI provider abstraction

### Priority

Critical.

### Estimated Difficulty

High.

### Milestones

#### v0.3

- Extract shared EvidenceCollector.
- Standardize assistant response sections.
- Add prompt/evidence regression tests.
- Route assistant modes through Knowledge Graph and Workspace evidence.

#### v0.4

- Add experiment similarity search.
- Add protocol performance summaries.
- Improve statistical interpretation coverage.
- Add deterministic hypothesis-gap detection.

#### v0.5

- Add Hypothesis Engine prototype.
- Add follow-up experiment scoring.
- Add literature contradiction detection.

#### v0.6

- Add mechanism/pathway-aware reasoning where metadata supports it.
- Add confidence scoring across experiments, statistics, images, and literature.

#### v0.7

- Add automated evidence packets for lab meeting questions.
- Add reviewer-style critique mode.

#### v0.8

- Add cross-project scientific memory.
- Add structured claim/evidence database.

#### v0.9

- Add manuscript-ready results synthesis from selected evidence.
- Add grant-specific significance/innovation drafting support.

#### v1.0

- Stable grounded scientific assistant with auditable evidence and deterministic fallbacks.

### Future Ideas

- Causal graph support.
- Mechanistic model comparisons.
- Reagent or perturbation recommendation engine.

## Epic 3: Laboratory Workflow

### Description

Laboratory Workflow turns ResearchOS into the daily operating surface for conducting experiments.

### Goals

- Make Experiment Sessions the primary active workflow.
- Support voice capture and structured notebook drafts.
- Track tasks, reminders, calendars, notifications, and experiment lifecycle.

### Dependencies

- sessions
- pending entries
- event bus
- notification system
- OneNote write-back design
- mobile/PWA

### Priority

High.

### Estimated Difficulty

High.

### Milestones

#### v0.3

- Improve sessions with templates.
- Add session summary export.
- Add task model.
- Add dashboard session/task cards.

#### v0.4

- Add reminders and timers.
- Add calendar view.
- Add notification framework.
- Add voice capture to session timeline.

#### v0.5

- Add experiment lifecycle states: planned, active, completed, analyzed, written.
- Add PI review queue.
- Add session-to-OneNote draft generation.

#### v0.6

- Add recurring protocol/session templates.
- Add mobile-first capture workflows.

#### v0.7

- Add lab-level task assignments.
- Add experiment dependency maps.

#### v0.8

- Add inventory/reagent reminders.
- Add plate/map/sample planning.

#### v0.9

- Add audit-ready experiment lifecycle export.

#### v1.0

- Stable daily lab workflow for sessions, tasks, capture, drafts, and review.

### Future Ideas

- Calendar integrations.
- Smart reminders based on protocol timing.
- Watch/phone quick capture.

## Epic 4: Providers

### Description

Providers connect ResearchOS to external files, tools, notebooks, datasets, and services.

### Goals

- Keep providers modular.
- Make provider outputs generic: documents, assets, metadata, events.
- Avoid provider-specific coupling in downstream services.

### Dependencies

- Asset model
- Event Bus
- provider scanner base
- authentication
- storage repositories

### Priority

Critical.

### Estimated Difficulty

High.

### Milestones

#### v0.3

- Extract generic file-provider scanner.
- Standardize provider result objects.
- Move provider event publication into provider/service layer.
- Add OneNote HTML fixtures.

#### v0.4

- Harden OneNote read-only sync.
- Add folder watchers for local providers.
- Add PubMed provider prototype.

#### v0.5

- Add ImageJ/Fiji metadata provider.
- Add CellProfiler output provider.
- Add Flow Cytometry file skeleton.

#### v0.6

- Add Sequencing provider skeleton.
- Add Cell Ranger output discovery.
- Add Benchling feasibility prototype.

#### v0.7

- Add Seurat/Scanpy object metadata import.
- Add PubMed monitor.

#### v0.8

- Add OneNote write-back prototype after approval.
- Add provider SDK.

#### v0.9

- Add provider certification tests.
- Add provider health dashboard.

#### v1.0

- Stable provider framework with OneNote, Markdown, GraphPad, microscopy, spreadsheet, literature, and sequencing foundations.

### Future Ideas

- LabArchives provider.
- Google Drive provider.
- Dropbox/Box provider.
- Instrument watcher plugins.

## Epic 5: Image Analysis

### Description

Image Analysis turns microscopy/image assets into searchable, measurable scientific evidence.

### Goals

- Browse microscopy assets.
- Link images to experiments and markers.
- Support segmentation, morphology, cell counting, and phenotype detection.

### Dependencies

- microscopy provider
- asset graph
- sessions
- image storage/access
- optional AI/computer vision stack

### Priority

High.

### Estimated Difficulty

Very High.

### Milestones

#### v0.3

- Improve image browser and filters.
- Add image preview support for common web formats.
- Add metadata normalization for markers/timepoints.

#### v0.4

- Add TIFF preview pipeline.
- Add image thumbnails.
- Add image-to-session attachment.

#### v0.5

- Add basic cell counting prototype.
- Add marker intensity extraction for simple images.

#### v0.6

- Add segmentation pipeline abstraction.
- Add Cellpose or similar integration prototype.

#### v0.7

- Add morphology metrics.
- Add phenotype classification.

#### v0.8

- Add batch image analysis jobs.
- Add image QC reports.

#### v0.9

- Add AI-assisted microscopy summaries with provenance.

#### v1.0

- Stable microscopy browser and first quantitative image-analysis workflows.

### Future Ideas

- Napari integration.
- OMERO integration.
- high-content screening dashboards.

## Epic 6: Sequencing

### Description

Sequencing connects bulk RNA-seq, scRNA-seq, trajectories, cell communication, and cluster metadata to experiments and literature.

### Goals

- Ingest sequencing outputs.
- Connect clusters/genes/pathways to experiments.
- Support Seurat, Scanpy, Cell Ranger, Monocle, Slingshot, and CellChat.

### Dependencies

- asset model
- provider framework
- Knowledge Graph
- large-file handling
- statistics engine

### Priority

Medium-High.

### Estimated Difficulty

Very High.

### Milestones

#### v0.3

- Define sequencing metadata schema.
- Add sequencing asset type refinements.

#### v0.4

- Add Cell Ranger folder detection.
- Add gene list import.

#### v0.5

- Add bulk RNA-seq differential-expression table ingestion.
- Add gene/pathway entity pages.

#### v0.6

- Add Seurat/Scanpy exported metadata ingestion.
- Add cluster-to-marker linking.

#### v0.7

- Add trajectory result imports from Monocle/Slingshot.
- Add cell-cell communication imports from CellChat.

#### v0.8

- Add sequencing experiment workspace sections.
- Add literature comparison for gene/pathway findings.

#### v0.9

- Add multi-dataset comparison.
- Add gene signature search.

#### v1.0

- Stable sequencing metadata and result integration for common exported formats.

### Future Ideas

- Direct `.h5ad` and Seurat object readers.
- Pathway enrichment provider.
- Interactive UMAP browser.

## Epic 7: Publication Tools

### Description

Publication Tools help convert connected evidence into figures, legends, methods, results, discussions, supplements, manuscripts, grants, and patents.

### Goals

- Generate publication materials from traceable evidence.
- Keep scientist review in control.
- Connect figures and text to source experiments/assets.

### Dependencies

- Knowledge Graph
- Experiment Workspace
- assets
- statistics
- literature
- assistant
- collaboration/review workflows

### Priority

Medium.

### Estimated Difficulty

High.

### Milestones

#### v0.3

- Define figure/manuscript asset model.
- Add evidence packet export.

#### v0.4

- Add figure builder concept.
- Add figure legend draft from selected assets.

#### v0.5

- Add methods draft from protocols and sessions.
- Add results draft from statistics and experiment workspaces.

#### v0.6

- Add discussion draft with literature context.
- Add supplement builder.

#### v0.7

- Add manuscript workspace.
- Add grant workspace.

#### v0.8

- Add patent workspace.
- Add reviewer response workspace.

#### v0.9

- Add citation manager integration.
- Add journal/grant formatting profiles.

#### v1.0

- Stable evidence-grounded writing workspace with provenance.

### Future Ideas

- PowerPoint export.
- Word/LaTeX export.
- graphical abstract assistant.

## Epic 8: Collaboration

### Description

Collaboration supports lab members, PI review, permissions, comments, approvals, version history, and audit trails.

### Goals

- Make ResearchOS safe for shared lab use.
- Support review-before-save workflows.
- Add approval and audit mechanisms.

### Dependencies

- authentication
- deployment
- sessions
- entries
- OneNote write-back
- audit/event log

### Priority

Medium-High before shared deployment.

### Estimated Difficulty

High.

### Milestones

#### v0.3

- Define user/role model.
- Define audit event model.

#### v0.4

- Add local app login for lab server.
- Add basic roles: admin, PI, researcher, viewer.

#### v0.5

- Add comments on experiments, sessions, assets, drafts.
- Add PI review queue.

#### v0.6

- Add approvals for notebook drafts and protocol changes.
- Add version history for drafts/protocol records.

#### v0.7

- Add audit trail export.
- Add user activity dashboard.

#### v0.8

- Add team/project permissions.
- Add private notes.

#### v0.9

- Add shared annotations on images, statistics, literature.

#### v1.0

- Stable multi-user collaboration and review workflow for lab-server deployment.

### Future Ideas

- SSO integration.
- Slack/Teams notifications.
- electronic signatures if required by deployment context.

## Epic 9: Automation

### Description

Automation coordinates events, deterministic agents, folder watchers, scheduled tasks, background jobs, PubMed monitors, and OneNote sync.

### Goals

- Providers publish events.
- Agents react deterministically.
- Background jobs perform expensive work safely.
- Future automation remains auditable.

### Dependencies

- Event Bus
- Agent Framework
- provider framework
- deployment
- notifications

### Priority

High.

### Estimated Difficulty

High.

### Milestones

#### v0.3

- Add durable event log.
- Persist agent enabled/disabled status.
- Add provider event integration tests.

#### v0.4

- Add folder watcher prototype.
- Add scheduled tasks.
- Add background job abstraction.

#### v0.5

- Add PubMed monitor.
- Add OneNote scheduled sync.
- Add notification framework.

#### v0.6

- Add job retry/error handling.
- Add automation dashboard.

#### v0.7

- Add user-configurable automation rules.
- Add experiment/session reminders.

#### v0.8

- Add background image/statistics/sequencing processing queue.

#### v0.9

- Add lab-wide automation policies.

#### v1.0

- Stable deterministic automation backbone with durable logs and operational visibility.

### Future Ideas

- Plugin marketplace.
- Instrument-triggered workflows.
- Git-like protocol automation hooks.

## Epic 10: Deployment

### Description

Deployment covers desktop, PWA, iPhone, Android, Windows, Mac, Linux, cloud, and lab-server modes.

### Goals

- Support easy local demos.
- Support shared lab-server use.
- Support mobile/PWA capture.
- Add secure deployment paths.

### Dependencies

- authentication
- permissions
- data backup
- PWA
- HTTPS
- OneNote redirect configuration

### Priority

High.

### Estimated Difficulty

High.

### Milestones

#### v0.3

- Add Docker Compose.
- Add backup/restore scripts.
- Add schema migrations.

#### v0.4

- Add lab-server service setup.
- Add HTTPS reverse proxy examples.
- Add local app login.

#### v0.5

- Add PWA install guidance inside UI.
- Add mobile smoke tests.

#### v0.6

- Add desktop packaging feasibility for Windows/Mac/Linux.
- Add data directory migration tools.

#### v0.7

- Add cloud deployment profile.
- Add secure secrets management.

#### v0.8

- Add admin dashboard.
- Add monitoring/health checks.

#### v0.9

- Add multi-project/lab deployment support.

#### v1.0

- Stable deployment profiles: local, lab server, PWA/mobile, and secure hosted mode.

### Future Ideas

- Tailscale-first lab deployment.
- UCSD-hosted deployment profile.
- managed ResearchOS appliance.

## Top 25 Milestones Before ResearchOS v1 Beta

These are ordered by impact, not implementation difficulty.

1. Split `main.py` into FastAPI routers.
2. Split `SQLiteStore` into focused repositories.
3. Add SQLite schema migrations.
4. Extract generic file-provider scanner.
5. Make Global Knowledge Graph the canonical graph layer.
6. Standardize provenance objects across all services.
7. Add data-version cache invalidation.
8. Cache Experiment Workspaces by experiment ID.
9. Extract shared EvidenceCollector for assistants.
10. Standardize assistant response schema and citation handling.
11. Add route-level API tests for all core services.
12. Add provider scan -> event -> agent -> graph integration tests.
13. Add frontend Playwright smoke tests.
14. Harden OneNote read-only sync with real HTML fixtures.
15. Add durable Event Bus log.
16. Persist Scientific Agent enabled/disabled state.
17. Add backup/restore scripts.
18. Add Docker Compose or equivalent lab-server deployment path.
19. Add app-level authentication for shared lab server mode.
20. Improve Experiment Sessions into the primary daily workflow.
21. Add task/reminder model.
22. Add folder watcher prototype for local providers.
23. Add image thumbnail/preview pipeline.
24. Add sequencing metadata schema and first import prototype.
25. Add PI review and approval workflow for notebook drafts.

## Roadmap Summary

ResearchOS should prioritize stabilization before expansion.

The platform already has the right foundations:

- local-first storage
- provider modules
- Knowledge Graph
- Asset Graph
- Event Bus
- deterministic agents
- Experiment Workspace
- Sessions
- assistant/reasoning/copilot workflows
- PWA and deployment planning

The next phase should make those foundations modular, testable, scalable, and safe for real lab use.
