# Notebook Document Format

Experiment notebooks store rich content as Quill Delta JSON.

Primary fields:
- `document_id`
- `experiment_id`
- `title`
- `document_format`: `rich_text_delta_json`, `markdown`, or `html`
- `content`: canonical saved payload
- `structured_content`: structured Delta payload used by rich clients
- `plain_text_cache`: generated text for search, previews, accessibility, and AI context
- `schema_version`
- `document_version`
- `version`
- `updated_by`

Binary files are never stored inside the document JSON. The document may contain typed references to attachments or ResearchObjects, while the binary data remains in attachment storage.

For Quill Delta, `content` is a JSON array of operations.

```json
[
  {"insert":"Experiment notes"},
  {"insert":"\n","attributes":{"header":1}},
  {"insert":"SAG treatment observation.\n"}
]
```

`plain_text_cache` is regenerated on save and should be treated as derived data.
