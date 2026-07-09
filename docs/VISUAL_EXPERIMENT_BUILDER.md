# Visual Experiment Builder

The Visual Experiment Builder lets researchers design experiments by branching conditions instead of manually creating spreadsheet rows.

It is another entry point into the same ResearchOS `ExperimentDesign` model. Spreadsheet import, templates, reminders, calendar export, plate layouts, and timeline tools continue to work because the visual builder compiles into normal design objects.

## Concepts

Supported node types:

- Experiment
- Cell Line
- Reporter
- Treatment
- Compound
- Dose
- Timepoint
- Collection
- Imaging
- Analysis
- Custom

Supported connection meanings:

- branch conditions
- merge branches
- parallel conditions
- sequential events

The current implementation stores the visual canvas as nodes and connections, then compiles it deterministically into:

- Experiment Design
- Conditions
- Events
- Timeline
- Reminders
- optional Plate Layout

## API

Create a visual builder:

```bash
curl -X POST http://127.0.0.1:8001/visual-experiment-builders \
  -H "Content-Type: application/json" \
  -d '{
    "title":"D1 SAG visual design",
    "nodes":[
      {"node_id":"experiment","type":"experiment","label":"D1 SAG visual design","properties":{"experiment_type":"retinal organoid"}},
      {"node_id":"control","type":"treatment","label":"DMSO control","properties":{"replicate_count":3,"start_day":"D1"}},
      {"node_id":"sag","type":"compound","label":"SAG","properties":{"dose":"100","units":"nM","replicate_count":3,"start_day":"D1"}},
      {"node_id":"d32","type":"timepoint","label":"D32"},
      {"node_id":"image","type":"imaging","label":"Image SIX6/BRN3B"}
    ],
    "connections":[
      {"source":"experiment","target":"control","relationship":"branch"},
      {"source":"experiment","target":"sag","relationship":"branch"},
      {"source":"sag","target":"d32","relationship":"sequential"},
      {"source":"d32","target":"image","relationship":"sequential"}
    ]
  }'
```

Compile without saving a design:

```bash
curl -X POST http://127.0.0.1:8001/visual-experiment-builders/{builder_id}/compile
```

Generate a real design and plate layout:

```bash
curl -X POST http://127.0.0.1:8001/visual-experiment-builders/{builder_id}/generate-design \
  -H "Content-Type: application/json" \
  -d '{"title":"Generated D1 SAG design","start_date":"2026-07-08","generate_plate_layout":true,"plate_format":"96-well"}'
```

List saved builders:

```bash
curl http://127.0.0.1:8001/visual-experiment-builders
```

## UI

The web UI includes a Visual Builder page with:

- canvas-style node board
- touch-friendly node cards
- example canvas loader
- duplicate branch
- rename/delete/duplicate node
- undo/redo
- mini-map scaffold
- compile/generate workflow
- links to generated Experiment Design, CSV export, and Plate Layout

Drag, pan, zoom, and mini-map are scaffolded through saved node coordinates and UI controls. A richer drag-and-drop canvas can replace the current node-card renderer without changing the backend model.

## Research Copilot Checks

The compiler highlights deterministic design issues:

- missing control branch
- unbalanced branch replicate counts
- unused/unconnected nodes

ResearchOS does not invent scientific conclusions from the visual canvas.

## Relationship To Existing Tools

The visual builder creates the same underlying model as:

- manual design forms
- CSV import
- mapped spreadsheet import
- design templates

That means a visual design can immediately use:

- `/experiment-designs/{design_id}/timeline`
- `/experiment-designs/{design_id}/export-csv`
- `/experiment-designs/{design_id}/export-ics`
- `/experiment-designs/{design_id}/generate-plate-layout`

## Future Work

- full drag-and-drop editing
- connection drawing
- branch merge visualization
- zoom/pan controls
- richer mini-map
- Flutter canvas implementation
- visual protocol blocks
- plate layout preview inside the builder
- branch balance scoring
