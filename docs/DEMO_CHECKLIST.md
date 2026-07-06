# ResearchOS Demo Checklist

Use this checklist for the PI/lab demo.

## Start

From the repository root:

```bash
./scripts/demo.sh
```

Dashboard URL:

```text
http://127.0.0.1:8001
```

## Buttons to Click

1. Click **Load demo notes**.
   - Expected: documents, experiments, compounds, markers, cell lines, and organoid batches populate.

2. Click **Suggested Questions**:
   - **Which experiments used SAG?**
   - Expected: ResearchOS lists SAG-specific experiments first, with source snippets and limitations.

3. Click **Compare our SAG experiments with the literature.**
   - Expected: ResearchOS separates lab experiment evidence from literature evidence.

4. Open **Experiments**.
   - Select two experiments with checkboxes.
   - Click **Compare selected**.
   - Expected: shared features, differences, interpretation, limitations, and source records appear.

5. Open **New Experiment**.
   - Click **Use sample dictation**.
   - Click **Generate structured entry**.
   - Expected: a structured JSON-style preview and Markdown notebook entry are generated.
   - Click **Copy Markdown** or **Download .md**.

6. Open **Settings**.
   - Expected: Markdown demo provider and local database are active.
   - Expected: OneNote shows not connected or pending UCSD IT approval.
   - Expected: AI provider shows configured or local fallback, depending on `.env`.

## Questions to Ask

- Which experiments used SAG?
- What does BMP4 do?
- Show experiments involving SIX6.
- Compare BRN3B experiments.
- Compare our SAG experiments with the literature.
- Summarize today's demo notebook.

## Expected Outputs

- The dashboard should show nonzero demo documents and experiments after loading demo notes.
- Search and assistant answers should cite local source snippets.
- Experiment comparison should avoid unrelated evidence unless it is clearly labeled as context.
- Literature comparison should work locally when sample papers are loaded.
- New Experiment should create a reviewable Markdown draft, but should not write to OneNote.

## OneNote and UCSD IT Talking Points

- OneNote remains the official lab notebook.
- ResearchOS is read-only for OneNote in the MVP.
- The current demo uses local Markdown notes so development is not blocked by Microsoft tenant approval.
- UCSD IT approval is needed before real OneNote login/sync can be used in the UCSD tenant.
- OneNote write-back is intentionally disabled and would require separate future approval for create/write permissions.
- No Microsoft client secrets or API keys are hardcoded in the repository.
