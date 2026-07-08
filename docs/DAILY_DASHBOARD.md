# ResearchOS Daily Dashboard

The Daily Dashboard is the default ResearchOS homepage summary. It collects
local evidence from documents, experiments, assets, providers, the Knowledge
Graph, timelines, statistics, literature, and Research Copilot into one
attention-focused view.

## Endpoint

```http
GET /api/dashboard/daily
```

Examples:

```bash
curl http://127.0.0.1:8001/api/dashboard/daily
curl "http://127.0.0.1:8001/api/dashboard/daily?use_ai=false"
```

## Sections

The dashboard returns ordered, collapsible cards:

- Overview
- Experiments requiring attention
- Recent activity
- Today's timeline
- Research Copilot insights
- Recent imports
- Pending analyses
- Recent literature
- Pinned experiments
- Pinned papers
- Recent searches
- Quick actions

Each item includes provenance so recommendations can be traced to local
ResearchOS records.

## Quick Actions

The dashboard includes shortcuts for:

- New Experiment
- Capture Note
- Import Files
- Search
- Ask Research Copilot

## Safety Model

The dashboard does not invent experimental observations. It separates observed
facts from inferred attention items and suggested actions. AI, when configured,
only summarizes the already-assembled dashboard JSON.

## UI

The homepage renders dashboard cards near the top of the page. Cards are
collapsible and can be reordered by dragging in the current browser session.
The layout collapses to one column on mobile.

## Cache

`DashboardService` caches the generated dashboard by counts of documents,
experiments, assets, and pending entries. When new records are ingested or
registered, the fingerprint changes and the dashboard is rebuilt.
