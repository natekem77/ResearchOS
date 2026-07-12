# Notebook Migration

Notebook loading follows this precedence:

1. Valid Quill Delta JSON.
2. Recoverable double-encoded Delta JSON.
3. Valid outer Delta documents whose text insert contains serialized Delta JSON.
4. Legacy records where Delta JSON was accidentally stored as visible text, preserving trailing user-entered text when possible.
5. Legacy Markdown/plain text converted into a Quill document.
6. A blank Quill document.

Migration is idempotent: reopening a migrated notebook must not duplicate headings, titles, or serialized JSON. Existing readable text and line breaks are preserved where practical.

The nested repair only unwraps an insert string when the entire trimmed string validates as a Quill Delta array or `{"ops":[...]}` object. Arbitrary JSON prose remains prose.

The backend repair helpers normalize notebook saves to `rich_text_delta_json` and regenerate `plain_text_cache` from the Delta document. The frontend also normalizes API payloads before creating the Quill document, including decoded list/map content, double-encoded JSON strings, and nested Delta-in-text records.

## Local Development Repair Command

Use the repair script before a demo if local SQLite data may contain older corrupted notebook records.

Dry run:

```bash
python3 scripts/repair_notebook_delta.py --dry-run
```

Apply repairs with a database backup:

```bash
python3 scripts/repair_notebook_delta.py --apply
```

The command reports notebook `document_id` values only, never notebook content. When `--apply` is used, it creates a timestamped backup next to the configured SQLite database before rewriting records. The repair is idempotent; running it again after a successful repair should report no records needing repair.
