# Spreadsheet Provider

The Spreadsheet Provider is ResearchOS's generic quantitative data ingestion
layer. It registers local spreadsheets as Research Assets and stores parsed
table summaries in SQLite asset metadata.

## Supported Formats

ResearchOS scans:

- `data/spreadsheets/`
- `samples/spreadsheets/`

Supported file extensions:

- `.csv`
- `.tsv`
- `.xlsx`
- `.xls`

CSV, TSV, and basic XLSX files are parsed with Python standard-library tools.
Legacy `.xls` files are registered as assets, but deep parsing is intentionally
limited unless a future optional binary Excel parser is added.

## API

```bash
curl http://127.0.0.1:8001/providers/spreadsheets/status
curl -X POST http://127.0.0.1:8001/providers/spreadsheets/scan
curl http://127.0.0.1:8001/spreadsheets
curl http://127.0.0.1:8001/spreadsheets/{asset_id}
curl http://127.0.0.1:8001/spreadsheets/{asset_id}/summary
curl -OJ http://127.0.0.1:8001/spreadsheets/{asset_id}/download
```

## Parser Design

The parser does not assume a specific lab, organism, marker panel, disease
model, or experiment type. For each table it detects:

- column names
- numeric columns
- categorical columns
- identifier columns
- date/time columns
- text columns

For numeric columns it computes:

- count
- mean
- median
- standard deviation
- SEM
- min and max
- quartiles
- missing values

When grouping columns exist, such as `Group`, `Treatment`, `Condition`, `Dose`,
`Timepoint`, or `Batch`, ResearchOS computes per-group numeric summaries.

## Entity Detection

Entity detection is heuristic and preserves unknown terms. It looks at both
column names and cell values to infer:

- genes
- proteins
- antibodies
- markers
- compounds
- drugs
- treatments
- cell lines
- organoid batches
- sample IDs
- animal IDs
- patient IDs
- sequencing clusters
- unknown scientific terms

Unknown scientific terms are kept in metadata rather than discarded.

## Extensible Ontology

Future labs can add terms without modifying code by creating:

```text
data/ontology_config.json
```

Example:

```json
{
  "markers": ["SIX6", "BRN3B"],
  "compounds": ["SAG", "BMP4"],
  "cell_lines": ["SIX6 reporter iPSC line"],
  "organisms": ["mouse", "human"],
  "disease_models": ["retinal degeneration"]
}
```

These terms are merged with dynamically discovered spreadsheet entities.

## Experiment Linking

ResearchOS attempts to infer experiment relationships from filenames such as:

- `NK_Expt_31_quantitative_readouts.csv`
- `EXP_31_flow_summary.tsv`

The inferred value is stored as `experiment_id`, but existing links are not
overwritten automatically.

## Assistant Integration

Spreadsheet-derived evidence is available to the assistant, scientific
reasoning engine, and follow-up experiment planner. Questions like:

```text
What happened to SIX6?
```

can retrieve evidence from notebooks, extracted experiments, literature,
GraphPad, spreadsheets, microscopy assets, and timelines.

## Future Extensions

The provider is designed to support future data from:

- retinal organoids
- scRNA-seq exports
- flow cytometry
- CellProfiler
- ImageJ/Fiji
- high-content imaging
- proteomics
- metabolomics
- behavioral experiments
- animal studies

Provider-specific interpretation can be layered on top later without changing
the core spreadsheet ingestion architecture.
