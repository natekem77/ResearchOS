# ResearchOS Event Bus and Automation Engine

ResearchOS is moving from request-driven provider code toward an event-driven platform.

Providers should publish events whenever new information arrives. Derived systems such as the Knowledge Graph, Search, Dashboard, Workspaces, Timelines, Statistics, and Research Copilot subscribe to those events.

The current implementation is synchronous and in-process. The API shape is intentionally compatible with a future async queue or durable event stream.

## Core Components

Code lives under:

```text
backend/app/events/
├── event_models.py
├── event_bus.py
├── automation_engine.py
└── subscribers/
```

### EventBus

`EventBus` provides:

- `subscribe(event_type, handler)`
- `publish(event)`
- `unsubscribe(event_type, handler)`
- duplicate suppression by `event_id`
- ordered synchronous delivery
- in-memory event history for diagnostics and tests

Use `event_type=None` to subscribe to all events.

### ResearchOSEvent

Every event contains:

- `event_type`
- `source`
- `payload`
- `event_id`
- `timestamp`
- `correlation_id`

### AutomationEngine

`AutomationEngine` subscribes to upstream provider/source events and publishes derived events.

Example:

```text
SpreadsheetParsed
-> KnowledgeGraphUpdated
-> WorkspaceUpdated
-> TimelineUpdated
-> DashboardUpdated
-> SearchIndexUpdated
```

The engine also refreshes registered cache-backed services:

- Knowledge Graph
- Universal Search index
- Daily Dashboard

## Event Types

Current canonical event types:

- `NotebookImported`
- `ExperimentExtracted`
- `AssetRegistered`
- `AssetLinked`
- `SpreadsheetParsed`
- `GraphPadParsed`
- `StatisticsGenerated`
- `ImageImported`
- `LiteratureImported`
- `KnowledgeGraphUpdated`
- `WorkspaceUpdated`
- `TimelineUpdated`
- `DraftCreated`
- `ProviderSynced`
- `SessionStarted`
- `SessionEventAppended`
- `SessionEnded`
- `DashboardUpdated`
- `SearchIndexUpdated`

## Provider Integration Pattern

Future providers should avoid direct coupling to derived services.

Instead of:

```python
knowledge_graph.refresh()
dashboard.refresh()
workspace.refresh()
```

publish an event:

```python
from app.events import EventType, ResearchOSEvent, get_event_bus

get_event_bus().publish(
    ResearchOSEvent(
        event_type=EventType.ASSET_REGISTERED,
        source="sequencing",
        payload={
            "asset_id": asset_id,
            "provider": "sequencing",
            "experiment_id": experiment_id,
        },
    )
)
```

The automation engine handles downstream refreshes and derived update events.

## Current Publishers

The backend currently publishes events after successful:

- Markdown ingestion
- OneNote read-only sync
- literature ingestion
- demo reset
- experiment extraction
- pending draft save
- asset registration
- asset linking
- experiment session start/end
- experiment session timeline updates
- GraphPad scan
- microscopy/image scan
- spreadsheet scan

## Diagnostics

Check automation status:

```bash
curl http://127.0.0.1:8001/status/automation
```

This returns recent event history, processed event counts, and registered refreshable services. It does not expose secrets.

## Design Rules

Providers should:

- publish events after successful writes
- include stable identifiers in payloads
- avoid calling downstream services directly
- use provider-neutral event types where possible
- keep payloads metadata-only and avoid secrets

Subscribers should:

- be idempotent
- tolerate repeated events
- avoid mutating source provider records
- rebuild derived state from SQLite/provider metadata
- keep future async execution in mind

## Future Extensions

Likely next steps:

- durable event log in SQLite
- async background worker
- retry policy for failed subscribers
- event filtering by provider
- notification subscribers
- UI activity stream backed by event history
- provider SDK helpers for OneNote, GraphPad, microscopy, sequencing, flow cytometry, CellProfiler, and ImageJ
