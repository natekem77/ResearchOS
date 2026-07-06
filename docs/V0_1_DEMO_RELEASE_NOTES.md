# ResearchOS v0.1 Demo Release Notes

ResearchOS v0.1 is a local-first demo release for PI/lab discussion and UCSD IT handoff. It is intended to show the direction of the system without requiring access to UCSD Microsoft OneNote data.

## What Works

- FastAPI backend with health, provider status, demo reset, search, assistant, experiment, literature, and graph endpoints.
- Browser dashboard served from the backend at `http://127.0.0.1:8001`.
- Local Markdown demo note ingestion from `samples/lab_notes`.
- SQLite storage for documents, chunks, extracted experiments, and local metadata.
- ChromaDB/vector-index foundation with keyword fallback search.
- Structured experiment extraction from local notes.
- Scientific assistant with local fallback answers when no AI provider is configured.
- Experiment comparison from structured extracted fields.
- Local literature ingestion from `samples/papers` and `data/papers`.
- Lab-literature comparison using local experiment and literature context.
- Knowledge Graph Explorer linking experiments, papers, protocols, compounds, markers, genes, cell lines, and organoid batches.
- Voice-to-structured-entry prototype with copy/download Markdown workflow.

## What Is Demo Data

- The lab notes under `samples/lab_notes` are synthetic demo notes.
- The paper notes under `samples/papers` are lightweight local sample literature records.
- The extracted experiments, ontology terms, graph links, assistant answers, and comparisons are derived from those local sample files unless the user ingests additional local files.
- No UCSD OneNote notebook content is required for the demo.

## OneNote-Ready But Pending UCSD IT Approval

- Microsoft Graph delegated authentication scaffolding is present.
- Read-only OneNote notebook, section, page listing, and page sync pipeline are implemented behind Microsoft login.
- The intended MVP remains read-only: OneNote stays the official notebook, while ResearchOS indexes local copies for search, extraction, assistant answers, and graph exploration.
- Real UCSD tenant access requires UCSD IT approval or a UCSD-owned Microsoft Entra app registration.
- Current requested delegated permissions remain read-only/minimal: `User.Read`, `Notes.Read`, `openid`, `profile`, and `offline_access`.
- OneNote write-back is intentionally disabled and would require separate future approval for create/write permissions.

## Known Limitations

- Demo extraction is regex/local-heuristic first and may miss or over-link scientific entities.
- The knowledge graph is generated from local SQLite records at request time; it is not yet a dedicated graph database.
- Literature PDF/text extraction is lightweight and may miss complex paper metadata.
- AI synthesis is optional. Without an AI provider, assistant and comparison endpoints use local fallback summaries.
- OneNote sync depends on Microsoft tenant consent, user licensing, and notebook access.
- Browser speech input is not implemented yet; the New Experiment workflow currently uses typed or OS-level dictated text.

## Next Milestones

- UCSD IT approval and real read-only OneNote pilot sync.
- Better OneNote HTML-to-markdown conversion and incremental sync tracking.
- More rigorous scientific entity extraction and graph disambiguation.
- Tests for graph entity linking and UI smoke flows.
- Optional AI-provider setup for richer synthesis.
- PI-reviewed write-back design, with separate UCSD approval if the lab wants OneNote create/write support.
