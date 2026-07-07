# Follow-up Experiment Planner

The Follow-up Experiment Planner turns ResearchOS evidence into a concrete next
experiment proposal.

## API

```bash
curl -X POST http://127.0.0.1:8001/assistant/plan-experiment \
  -H "Content-Type: application/json" \
  -d '{"question":"What should we test next for early SAG + GRKi retinal rescue?","use_ai":false}'
```

The response includes:

- proposed experiment title
- hypothesis
- rationale
- experimental groups
- treatment schedule
- controls
- planned readouts
- suggested markers
- statistical analysis plan
- risks and confounders
- expected outcomes
- suggested Markdown notebook draft

## Evidence Sources

The planner gathers context from:

- scientific reasoning output
- extracted experiments
- GraphPad statistics assets
- microscopy assets
- literature matches
- timeline events
- local notebook/protocol text and templates

## Local Fallback

Without an AI provider, ResearchOS builds a deterministic plan from local
evidence and known retinal organoid planning conventions. This keeps demos and
lab use unblocked without cloud AI.

## Optional AI Synthesis

If an AI provider is configured, ResearchOS uses the same local evidence package
to improve the plan rationale. It does not invent missing data and does not
write to OneNote.

## Draft Workflow

The UI includes a **Plan Follow-up Experiment** page. After generating a plan,
users can click **Save as Draft** to store the suggested notebook entry in
ResearchOS pending drafts.

OneNote write-back remains disabled until UCSD IT approves create/write
permissions.
