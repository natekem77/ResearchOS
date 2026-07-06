# Pending Notebook Entries

ResearchOS can save generated lab notebook drafts locally before OneNote write-back is approved.

## Why This Exists

The PI-requested workflow is:

1. Dictate or type experiment details.
2. Generate a structured notebook entry.
3. Review and revise the entry.
4. Eventually save to OneNote.

In v0.1, ResearchOS intentionally does not write to OneNote. Pending entries provide a temporary local holding area so useful drafts are not lost while UCSD IT approval and lab policy are still pending.

## Local Status Values

- `draft`: generated or saved locally, still being reviewed.
- `ready_for_onenote`: reviewed and ready for a future OneNote save workflow.
- `exported`: copied or downloaded outside ResearchOS.

These statuses are local ResearchOS metadata only. They do not change OneNote.

## API

Save or update a pending entry:

```bash
curl -X POST http://127.0.0.1:8001/entries/save-draft \
  -H "Content-Type: application/json" \
  -d '{
    "title": "NK-EXPT-31: SAG + GRKi",
    "experiment_id": "NK-EXPT-31",
    "template": "retinal_organoid",
    "structured": {"title": "NK-EXPT-31: SAG + GRKi"},
    "markdown": "# NK-EXPT-31: SAG + GRKi",
    "status": "draft"
  }'
```

List drafts:

```bash
curl http://127.0.0.1:8001/entries
```

Open one draft:

```bash
curl http://127.0.0.1:8001/entries/entry-id
```

Delete one draft:

```bash
curl -X DELETE http://127.0.0.1:8001/entries/entry-id
```

## UI Workflow

On the **New Experiment** page:

1. Generate a structured entry.
2. Click **Save Draft in ResearchOS**.
3. Click **Mark ready for OneNote** after review if appropriate.
4. Open **Saved Drafts** to reopen or delete local drafts.

The **Save to OneNote** button remains disabled until UCSD IT approves OneNote create/write permissions in a separate future milestone.

## Privacy

Pending entries are stored in the local SQLite database configured for ResearchOS. They are not sent to Microsoft Graph or OneNote. If a cloud AI provider is configured for draft formatting, raw notes may be sent to that provider according to the configured provider settings.
