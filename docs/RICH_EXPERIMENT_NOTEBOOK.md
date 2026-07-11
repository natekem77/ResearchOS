# Rich Experiment Notebook

Each generalized experiment has an `ExperimentNotebookDocument`.

Current first-version support:

- markdown/plain-text editor
- title
- headings
- paragraphs
- lists
- links as text
- autosave-ready save endpoint
- versioned saves
- optimistic concurrency
- typed attachment references

The Flutter editor is intentionally simple for this milestone. The backend supports `document_format` values:

- `markdown`
- `rich_text_json`
- `html`

Binary files are not stored inside notebook content. They should be represented by `ExperimentNotebookAttachment` records with typed references.

## Optimistic Concurrency

Notebook save requests include `current_version`. If the server version has changed, ResearchOS returns a conflict so the UI can ask the user to reload or resolve manually.

## API

```bash
curl http://127.0.0.1:8001/experiments/NK_Expt_26/notebook \
  -H "X-ResearchOS-User: user:researcher-a"
```

```bash
curl -X PUT http://127.0.0.1:8001/experiment-notebooks/experiment-notebook:NK_Expt_26 \
  -H "Content-Type: application/json" \
  -H "X-ResearchOS-User: user:researcher-a" \
  -d '{"current_version":1,"content":"# Updated notes","document_format":"markdown"}'
```

