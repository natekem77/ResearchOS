# Quantification Workspace

The Quantification Workspace is the central ResearchOS location for every quantitative result connected to an experiment.

This milestone does not implement AI image analysis. It creates the workflow infrastructure that future quantitative analysis tools will plug into.

## Purpose

The workspace organizes the path from raw image acquisition through imported tables, statistical analysis, and publication-ready figures.

It belongs to one experiment and aggregates data from:

- microscopy/image assets
- GraphPad assets
- spreadsheets
- statistics interpretations
- notebook source records
- experiment sessions
- Knowledge Graph
- Evidence Engine
- Workflow Engine
- Research Copilot

## API

```bash
curl http://127.0.0.1:8001/experiments/NK_Expt_31/quantification
curl http://127.0.0.1:8001/mobile/experiments/NK_Expt_31/quantification
```

## Workspace Sections

### Raw Images

Microscopy assets linked to the experiment. Filename-derived metadata such as markers, channels, timepoints, extension, and parser are shown when available.

### Processed Images

Placeholder section for future outputs:

- ImageJ/Fiji outputs
- CellProfiler outputs
- segmentation masks
- representative images
- annotated microscopy

No processing is performed yet.

### Quantification Tables

Imported CSV, TSV, Excel, or spreadsheet assets. ResearchOS summarizes variables, groups, replicates, numeric measurements, and compact summary statistics when metadata is available.

### Statistical Analysis

GraphPad and spreadsheet-derived statistical interpretations. This section includes significance, p-values when explicitly parsed, and future placeholders for effect size and confidence intervals.

### Representative Figures

Placeholder for future publication figures, annotated microscopy, and figure panels.

### Research Copilot

Local deterministic synthesis of:

- current quantitative evidence
- missing analyses
- potential concerns
- recommended next steps

Copilot statements are provenance-backed and must not invent observations.

## Timeline Integration

The workspace exposes quantification-specific timeline events:

- `images_imported`
- `spreadsheet_imported`
- `graphpad_imported`
- `statistics_completed`
- `notebook_entry`
- `session_context`

These events are derived from existing ResearchOS records.

## Knowledge Graph Integration

Quantitative assets connect to:

- experiment
- markers
- compounds
- genes/proteins when detected
- resources
- statistics
- evidence summaries

Future providers should emit metadata and asset records so they automatically appear in this workspace.

## Future Integrations

The architecture is designed for:

- ImageJ
- Fiji
- CellProfiler
- QuPath
- Napari
- cell counting
- organoid segmentation
- marker intensity
- morphology analysis
- lamination scoring
- automatic GraphPad generation
- automatic figure generation

All future tools should contribute to the Quantification Workspace rather than creating separate quantitative result interfaces.
