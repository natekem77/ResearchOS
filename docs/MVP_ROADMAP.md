# ResearchOS MVP Roadmap

This roadmap describes the intended sequence for building the first ResearchOS
module: AI-assisted OneNote workflows for scientific laboratories.

## Phase 0: Foundation

- Establish repository structure.
- Add FastAPI backend skeleton.
- Add environment-based configuration.
- Add logging.
- Document architecture and development direction.

## Phase 1: OneNote Read Integration

- Register Microsoft Graph application credentials.
- Implement OAuth flow for development use.
- Read notebook, section, page, and page content metadata.
- Store normalized OneNote records in SQLite.
- Add clear sync status and error logging.

## Phase 2: Search and Retrieval

- Extract searchable text from OneNote pages.
- Chunk notebook content for retrieval.
- Store embeddings and metadata in ChromaDB.
- Add semantic search endpoints.
- Preserve source links back to OneNote pages.

## Phase 3: Research Assistant Workflows

- Summarize experiment notes.
- Compare related experiments.
- Draft protocols from prior successful runs.
- Identify missing metadata in experiment records.
- Add guardrails for scientific uncertainty and citations.

## Phase 4: Collaboration and Review

- Add user accounts and project workspaces.
- Add role-aware access controls.
- Add protocol version history.
- Add audit logs for AI-generated outputs.

## Phase 5: Additional Modules

- Microscopy image analysis.
- RNA-seq integration.
- Inventory management.
- Paper writing and literature management.
- Experiment planning.

## Non-Goals for the Initial Scaffold

- No OneNote synchronization.
- No authentication.
- No AI provider integration.
- No frontend implementation.
- No production deployment manifests.
