# Compact Quantitative Summaries

ResearchOS stores full spreadsheet and statistics metadata for inspection, but
demos and assistant answers need a concise view. Compact summaries provide that
presentation layer.

## Endpoints

```bash
curl http://127.0.0.1:8001/spreadsheets/{asset_id}/compact-summary
curl http://127.0.0.1:8001/statistics/{asset_id}/compact-summary
```

## Response Shape

Compact summaries include:

- title
- experiment ID
- detected markers/entities
- detected treatments/groups
- key numeric measurements
- per-group means
- n per group
- p-values when available
- short interpretation
- limitations

## Spreadsheet Summaries

Spreadsheet compact summaries are derived from generic table metadata:

- numeric column summaries
- grouped summaries when columns such as `Treatment`, `Condition`, or `Group`
  are detected
- dynamically detected entities from column names and cell values

No marker, compound, gene, or model-system names are hardcoded.

## GraphPad Statistics Summaries

GraphPad compact summaries are derived from parsed CSV statistics metadata:

- variables
- groups
- means by group
- sample sizes
- p-values
- statistical tests

## UI Behavior

The Data page and Statistics page show compact cards first. Raw metadata is kept
behind an expandable **Raw metadata** section in asset detail views so demos stay
readable while preserving full local metadata for developers.

## Assistant Behavior

The assistant now prefers compact summaries when answering quantitative
questions. It still keeps the full metadata in local storage for future deeper
reasoning and provider-specific analysis.
