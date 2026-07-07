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

## UI

Every experiment detail page has a `Timeline` tab. The dashboard also includes a
Recent Timeline widget that surfaces recent experiment, document, and asset
events.

## Limitations

The timeline is local-first and depends on linked assets. It does not infer every
possible relationship automatically yet. Future milestones can add richer
timeline clustering, source previews, image thumbnails, OneNote page deep links,
and AI-generated timeline summaries.
