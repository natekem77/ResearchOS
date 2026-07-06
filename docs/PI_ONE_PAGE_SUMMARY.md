# ResearchOS PI One-Page Summary

## Problem

Lab knowledge is spread across notebook pages, protocols, images, spreadsheets,
and papers. Even when documentation is complete, it can be slow to find prior
experiments, compare conditions, identify repeated protocols, or summarize what
happened across related studies.

## Proposed Solution

ResearchOS is an AI-powered research operating system for scientific
laboratories. It adds a searchable, structured intelligence layer around existing
lab notes. The first target integration is Microsoft OneNote, with local
development currently using sample Markdown notes.

The system indexes notes, extracts experiments, identifies retinal organoid
entities such as compounds and markers, and provides a dashboard for search,
comparison, and future AI-assisted summarization.

## Why Keep OneNote

OneNote should remain the official lab notebook. ResearchOS is not intended to
replace it. Keeping OneNote preserves the lab's existing documentation workflow,
reduces adoption friction, and avoids changing the official record system.

ResearchOS works as a read-only companion layer that helps researchers use the
information already present in OneNote more effectively.

## Benefits

- Faster search across prior experiments and protocols.
- Structured experiment views from unstructured notes.
- Entity pages for compounds, markers, cell lines, and organoid batches.
- Better continuity between lab members and projects.
- Foundation for future microscopy, RNA-seq, literature, protocol, and planning
  modules.
- Local-first development path that does not block on Microsoft approval.

## Risks And Security

- Lab notebook data is sensitive and should be treated as confidential.
- OneNote integration requires UCSD Microsoft tenant approval.
- Initial OneNote access should be read-only.
- No secrets should be hardcoded or committed.
- Local storage should be documented and protected.
- Cloud AI should be optional and used only under approved lab and UCSD policy.

## Development Status

Working locally:

- FastAPI backend.
- Browser dashboard.
- Markdown demo ingestion.
- SQLite storage.
- Search.
- Experiment extraction.
- Retinal organoid ontology pages.
- Configurable AI chat architecture.
- Microsoft Graph login scaffold and read-only metadata listing.

Pending:

- UCSD approval or UCSD-owned app registration for OneNote access.
- Full OneNote page sync.
- OneNote HTML-to-text conversion.
- Production-grade token handling and deployment decisions.

## Next Steps

1. Review local demo with the lab.
2. Decide whether to request UCSD IT approval for read-only OneNote access.
3. Submit the UCSD IT approval request.
4. Implement read-only OneNote sync after approval.
5. Continue improving extraction quality and retinal organoid intelligence.
