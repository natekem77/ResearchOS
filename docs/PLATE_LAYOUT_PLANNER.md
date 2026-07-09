# Plate and Sample Layout Planner

The Plate and Sample Layout Planner converts an `ExperimentDesign` into a practical bench layout. It helps researchers translate conditions and replicates into wells, tubes, racks, or custom sample positions.

This is a planning aid. It does not control instruments or write to OneNote.

## Supported Formats

Built-in formats:

- `6-well`
- `12-well`
- `24-well`
- `48-well`
- `96-well`
- `384-well`
- `tube_rack`
- `custom`

For `custom`, provide explicit `rows` and `columns`.

## API

List layouts:

```bash
curl http://127.0.0.1:8001/plate-layouts
```

Generate from an experiment design:

```bash
curl -X POST http://127.0.0.1:8001/experiment-designs/{design_id}/generate-plate-layout \
  -H "Content-Type: application/json" \
  -d '{"title":"D1 SAG 96-well layout","format":"96-well","balanced":true,"grouped_by_condition":true}'
```

Generate a randomized layout:

```bash
curl -X POST http://127.0.0.1:8001/experiment-designs/{design_id}/generate-plate-layout \
  -H "Content-Type: application/json" \
  -d '{"format":"96-well","randomized":true}'
```

Get one layout:

```bash
curl http://127.0.0.1:8001/plate-layouts/{layout_id}
```

Export CSV:

```bash
curl http://127.0.0.1:8001/plate-layouts/{layout_id}/export-csv \
  -o plate_layout.csv
```

## Well Assignment Fields

Each well assignment includes:

- well ID
- row
- column
- position
- condition
- replicate
- sample ID
- treatment
- dose
- units
- day
- notes

Unused wells remain present in the layout with empty assignment fields.

## Layout Warnings

ResearchOS flags practical issues:

- no obvious control condition
- too few wells for the number of assignments
- unbalanced replicate counts across conditions

These warnings are deterministic. They do not infer scientific conclusions.

## Example: 96-Well Organoid Plate

For a retinal organoid design with DMSO, D1 SAG, and D9 SAG conditions:

```bash
curl -X POST http://127.0.0.1:8001/experiment-designs/{design_id}/generate-plate-layout \
  -H "Content-Type: application/json" \
  -d '{"format":"96-well","balanced":true,"grouped_by_condition":true}'
```

The resulting layout assigns condition replicates into wells and leaves unused wells empty.

## Example: 24-Well Staining Plate

For a staining workflow with a small number of samples:

```bash
curl -X POST http://127.0.0.1:8001/experiment-designs/{design_id}/generate-plate-layout \
  -H "Content-Type: application/json" \
  -d '{"title":"D32 staining 24-well plate","format":"24-well","grouped_by_condition":true}'
```

The CSV export can be opened in Excel and printed for bench setup.

## UI Workflow

The web app includes:

- Plate Layout page
- visual grid
- condition color coding
- click-to-edit wells
- CSV export
- printable view

Future work can add drag-and-drop editing, plate maps, barcode labels, and randomized/blinded sample labels.
