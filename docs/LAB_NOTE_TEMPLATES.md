# Lab Notebook Templates

ResearchOS v0.1 includes reusable local templates for generating structured lab notebook drafts from dictation or typed notes.

## Available Templates

- `retinal_organoid`: retinal organoid treatment or differentiation experiments.
- `immunostaining`: fixation, staining, marker, antibody, imaging, and result notes.
- `media_treatment_log`: media changes, treatments, concentrations, controls, and deviations.
- `imaging_session`: microscope/imaging session notes, channels, readouts, and image-quality issues.
- `general_experiment`: flexible experiment entry for notes that do not fit a specialized template.

Use:

```bash
curl http://127.0.0.1:8001/entry-templates
```

## Dictation Mapping

The local parser maps dictated notes into structured fields:

- title
- experiment ID
- objective
- date
- researcher
- cell line
- organoid batch
- differentiation day
- conditions
- treatment schedule
- reagents/concentrations
- controls
- planned readouts
- observations
- issues/deviations
- next steps

Example:

```bash
curl -X POST http://127.0.0.1:8001/entries/draft \
  -H "Content-Type: application/json" \
  -d '{
    "template": "retinal_organoid",
    "dictation": "Create NK Expt 31. Date today. Researcher Nathan. D18 SAG plus GRKi rescue with 100 nM SAG and 250 nM GRK inhibitor. DMSO control. Readouts SIX6 and BRN3B. Next steps quantify SIX6 intensity."
  }'
```

The first pass is deterministic regex/local extraction. If an AI provider is configured, ResearchOS can optionally improve the Markdown formatting while preserving the structured fields and avoiding invented facts.

## OneNote Write-Back Later

The current workflow is review-before-save:

1. Dictate or type raw notes.
2. Select a template.
3. Generate a structured draft.
4. Review the Markdown notebook entry.
5. Copy or download Markdown locally.

Saving directly to OneNote remains disabled in v0.1. Future OneNote write-back would reuse these templates to create consistent pages through Microsoft Graph, but that would require separate UCSD IT approval for create/write permissions such as `Notes.Create` or `Notes.ReadWrite`.
