# Notebook Single Source of Truth

Mundi experiment workspaces use one editable notebook implementation:

`RichScientificNotebookEditor -> QuillController -> Quill Delta JSON -> experiment notebook API`

The experiment title, attachment cards, tool panels, and dialogs may contain ordinary inputs, but the notebook body itself is edited only by the Quill editor. Search previews and AI context use `plain_text_cache`, which is derived from the Quill document and is not independently editable.

Persisted notebook fields:

- `document_format`: `rich_text_delta_json`
- `content`: canonical Quill Delta JSON
- `structured_content`: the same canonical Quill Delta JSON for API compatibility
- `plain_text_cache`: derived readable text
- `schema_version` and `document_version`: document migration and concurrency metadata

New notebook-first experiments start with a blank Delta document containing only a newline operation. The experiment title is never inserted into the notebook body.
