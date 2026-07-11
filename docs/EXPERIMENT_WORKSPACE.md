# Experiment Workspace

Milestone 48 introduces the unified Experiment Workspace. This is the central
ResearchOS object for an experiment and should be the default place future
features gather experiment context.

## Endpoint

```http
GET /experiments/{experiment_id}/workspace
```

Example:

```bash
curl http://127.0.0.1:8001/experiments/NK_Expt_31/workspace
```

Disable AI synthesis for deterministic local output:

```bash
curl "http://127.0.0.1:8001/experiments/NK_Expt_31/workspace?use_ai=false"
```

## Returned Data

The workspace returns:

- `experiment`
- `notebook_entries`
- `timeline`
- `microscopy`
- `graphpad`
- `spreadsheets`
- `statistics`
- `literature`
- `compounds`
- `markers`
- `genes`
- `proteins`
- `organoid_batches`
- `related_experiments`
- `related_entities`
- `conclusions`
- `limitations`
- `provenance`
- `sections`
- `ai_summary`

## Architecture

The workspace uses `KnowledgeGraphService` as its backbone. It does not rescan
providers or duplicate provider-specific discovery logic.

It gathers:

- notebook source documents from experiment extraction metadata
- timeline events from the existing timeline builder
- microscopy/image assets through Knowledge Graph experiment neighborhoods
- GraphPad assets and statistics through asset metadata
- spreadsheet compact summaries through the spreadsheet provider
- statistical interpretations through the statistics engine
- literature through shared Knowledge Graph entities
- related entities and experiments from graph relationships

Future providers should contribute metadata to the global Knowledge Graph. The
workspace will then include them through graph neighborhoods and asset records.

## Provenance

Every workspace has a `provenance` array. Each record includes:

- `fact`
- `source`
- `provider`
- `document`
- `asset`
- `timestamp`

The UI displays this as a collapsible Provenance section so users can trace
where workspace information came from.

## AI Summary

If an AI provider is configured, ResearchOS sends the workspace contents to the
provider for a concise scientific summary. If not configured, ResearchOS returns
a deterministic local summary.

Summaries distinguish:

- Observed
- Inferred
- Referenced from literature

The summary must not invent missing information.

## UI

Open an experiment workspace from the experiment detail page:

```text
http://127.0.0.1:8001/#/experiments/{experiment_id}/workspace
```

The workspace page includes:

- overview
- timeline
- treatment/readout tags
- microscopy/images
- GraphPad analyses
- spreadsheet summaries
- statistics
- literature
- connected experiments
- related entities
- files
- AI/local summary
- limitations
- provenance

## Generalized Workspace Foundation

The generalized experiment foundation adds a parallel workspace endpoint for
the narrative-notebook plus structured-plan model:

```bash
curl http://127.0.0.1:8001/experiments/NK_Expt_26/general-workspace \
  -H "X-ResearchOS-User: user:researcher-a"
```

Create a blank experiment:

```bash
curl -X POST http://127.0.0.1:8001/experiments/general \
  -H "Content-Type: application/json" \
  -H "X-ResearchOS-User: user:researcher-a" \
  -d '{"title":"Primary cell assay","biological_system":"primary cells","sample_unit_type":"well"}'
```

Create from protocol:

```bash
curl -X POST http://127.0.0.1:8001/experiments/general/from-protocol \
  -H "Content-Type: application/json" \
  -H "X-ResearchOS-User: user:researcher-a" \
  -d '{"title":"Protocol-derived test","protocol_id":"protocol:meyer-retinal-organoid-protocol","protocol_version_id":"protocol-version:meyer-retinal-organoid-protocol:demo-v1"}'
```

Protocol-derived events retain `protocol_event_id` and protocol version
metadata. Protocol changes do not silently alter historical experiment
timelines.
