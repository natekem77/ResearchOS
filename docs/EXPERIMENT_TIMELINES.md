# Experiment Timelines

ResearchOS experiment timelines combine structured experiment records with the
research assets linked to those experiments.

## API

```bash
curl http://127.0.0.1:8001/experiments/{experiment_id}/timeline
```

The `{experiment_id}` can be a ResearchOS internal ID such as
`experiment:8ff67dfff14ec61c` or a human experiment ID when one exists.

Each event contains:

- `timestamp`
- `event_type`
- `title`
- `description`
- `source`
- `linked_asset_ids`
- `linked_document_ids`

Event types used by the current UI:

- `notebook_entry`
- `extracted_experiment`
- `graphpad_analysis`
- `statistics_result`
- `image_asset`
- `literature_reference`
- `pending_entry`

## Event Sources

The timeline currently includes:

- Extracted experiment records
- Source notebook or literature documents
- Local pending notebook-entry drafts when their experiment ID matches
- Linked GraphPad assets
- Parsed GraphPad statistics assets
- Linked image, microscopy, PDF, literature, protocol, spreadsheet, and other assets
- AI summaries if a future provider stores summary text in asset metadata

Events are sorted chronologically using the best available timestamp. Unknown
timestamps are placed at the end.

Timestamps are normalized into readable ISO-style values when possible. Unix
timestamps, SQLite timestamps such as `2026-07-07 01:32:42`, and date-only
values are all converted before returning the timeline.

## Examples

Example extracted experiment event:

```json
{
  "timestamp": "2026-07-07T01:32:42",
  "event_type": "extracted_experiment",
  "title": "SAG rescue experiment",
  "description": "Structured experiment extracted from markdown.",
  "source": "markdown",
  "linked_asset_ids": [],
  "linked_document_ids": ["doc:example"]
}
```

Example GraphPad statistics event:

```json
{
  "timestamp": "2026-07-07T01:40:11",
  "event_type": "statistics_result",
  "title": "NK Expt 31 SIX6 BRN3B stats",
  "description": "Parsed GraphPad CSV statistics: variables SIX6, BRN3B; groups DMSO, SAG, SAG + GRKi; p-values 0.018, 0.006; test one-way ANOVA with Tukey correction.",
  "source": "graphpad",
  "linked_asset_ids": ["asset:example"],
  "linked_document_ids": []
}
```

Assets linked to human experiment IDs, such as `NK_Expt_31`, are included when
that human ID matches the extracted experiment record or appears in the
extracted experiment title, notes, or conclusions.

## UI

Every experiment detail page has a `Timeline` tab. The dashboard also includes a
Recent Timeline widget that surfaces recent experiment, document, and asset
events.

## Limitations

The timeline is local-first and depends on linked assets. It does not infer every
possible relationship automatically yet. Future milestones can add richer
timeline clustering, source previews, image thumbnails, OneNote page deep links,
and AI-generated timeline summaries.
