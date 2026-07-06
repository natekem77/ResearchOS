# Draft Export Workflow

ResearchOS pending entries can be copied or downloaded while OneNote write-back is pending UCSD IT approval.

## Workflow

1. Generate a notebook entry on the **New Experiment** page.
2. Click **Save Draft in ResearchOS**.
3. Open **Saved Drafts**.
4. Open a saved draft detail page.
5. Use:
   - **Copy Markdown** to copy the notebook page text.
   - **Download Markdown** to download a `.md` file.
   - **Mark Ready for OneNote** to flag the draft for future write-back review.

The **Save to OneNote** button remains disabled in v0.1.

## API

Return Markdown as JSON content for copy workflows:

```bash
curl http://127.0.0.1:8001/entries/entry-id/markdown
```

Download a `.md` file:

```bash
curl -OJ http://127.0.0.1:8001/entries/entry-id/download
```

The existing pending-entry endpoints remain available:

```bash
curl http://127.0.0.1:8001/entries
curl http://127.0.0.1:8001/entries/entry-id
curl -X POST http://127.0.0.1:8001/entries/save-draft
```

## OneNote Status

Exporting Markdown does not write to OneNote and does not require new Microsoft Graph permissions. Future OneNote write-back would require separate UCSD IT approval for create/write scopes.
