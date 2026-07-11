# Protocol Hub 2.0

Protocol Hub turns protocols into structured, versioned scientific workflows. A protocol is not treated as a static PDF; it is a reusable workflow with events, materials, media recipes, expected results, QC checkpoints, troubleshooting notes, linked papers, and usage history.

## Core Objects

- `Protocol`: stable protocol identity, lab, title, category, biological system, sample unit, owner, status, and current version.
- `ProtocolVersion`: immutable scientific version used by experiments. Experiments always reference the exact version they used.
- `ProtocolEvent`: baseline timeline event such as media change, compound addition, collection, imaging, assay, QC, passage, or custom step.
- `ProtocolMaterial`: reagent/material requirement, optionally linked to inventory.
- `ProtocolMedia`: structured media recipe, preparation, storage, and change schedule.
- `ProtocolNotebookDocument`: editable protocol notebook content.
- `ProtocolExpectedResult`: expected morphology, marker expression, differentiation stage, QC metric, or timeline checkpoint.
- `ProtocolTroubleshooting`: issue, possible causes, possible solutions, and evidence links.

## Workspace Tabs

The Protocol Workspace is organized around:

- Overview
- Notebook
- Timeline
- Materials
- Media
- Equipment
- Events
- Expected Results
- QC
- Troubleshooting
- Linked Papers
- Version History
- Usage Statistics
- Related Experiments
- Discussion

The current implementation stores structured tabs through local SQLite tables and exposes them through `/protocol-hub` endpoints.

## API Examples

```bash
curl http://127.0.0.1:8001/protocol-hub/protocols
curl http://127.0.0.1:8001/protocol-hub/protocols/protocol:meyer-retinal-organoid-protocol
curl "http://127.0.0.1:8001/protocol-hub/search?q=BMP4"
curl "http://127.0.0.1:8001/protocol-hub/compare?left_version_id=...&right_version_id=..."
```

Create a protocol:

```bash
curl -X POST http://127.0.0.1:8001/protocol-hub/protocols \
  -H "Content-Type: application/json" \
  -d '{
    "title": "General immunostaining protocol",
    "short_name": "IF staining",
    "category": "assay",
    "biological_system": "general",
    "sample_unit": "sample",
    "version_number": "1.0",
    "events": [
      {"title": "Fix sample", "relative_day": 0, "event_type": "assay"},
      {"title": "Primary antibody incubation", "relative_day": 0, "event_type": "assay"}
    ],
    "materials": [
      {"name": "Primary antibody", "required": true}
    ]
  }'
```

## Demo Protocols

Protocol Hub seeds representative structured protocols:

- Meyer retinal organoid protocol
- Nakano retinal organoid protocol
- Simple RPE protocol
- Stem cell maintenance
- Media preparation
- Immunostaining
- RNA extraction

These are demo scaffolds, not validated wet-lab instructions.

## Experiment Integration

Starting an experiment from a protocol should inherit protocol events, materials, media, QC expectations, and expected results. The experiment references the protocol version actually used. Later protocol updates do not alter the historical experiment.

Experiments define deviations and overrides. Protocols define the baseline.

