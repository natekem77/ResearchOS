# Experiment Lifecycle Engine

ResearchOS tracks every extracted experiment through a formal lifecycle so the dashboard, workspace, sessions, timeline, and Research Copilot can agree on what should happen next.

## Stages

The canonical lifecycle stages are:

- Planning
- Approved
- Running
- Waiting
- Imaging
- Analysis
- Writing
- Submitted
- Published
- Archived
- Cancelled

Each stage has allowed transitions, completion criteria, and deterministic recommended next actions. These rules live in `backend/app/experiment_lifecycle.py`.

## Default Behavior

When an experiment first appears in ResearchOS, its lifecycle defaults to `Planning`. The first lifecycle lookup initializes a history record so the experiment timeline can show when lifecycle tracking began.

Lifecycle state is local-first and stored in SQLite:

- `experiment_lifecycles`
- `experiment_lifecycle_events`

## API

Get lifecycle state:

```bash
curl http://127.0.0.1:8001/experiments/NK_Expt_31/lifecycle
```

Transition an experiment:

```bash
curl -X POST http://127.0.0.1:8001/experiments/NK_Expt_31/transition \
  -H "Content-Type: application/json" \
  -d '{
    "to_stage": "Approved",
    "reason": "Plan reviewed with PI",
    "actor": "Nathan"
  }'
```

Invalid transitions return HTTP 400 with the allowed next stages.

## Timeline Integration

Every lifecycle transition becomes a timeline event with:

- timestamp
- event type `lifecycle_transition`
- from stage
- to stage
- reason
- actor

This makes lifecycle history visible in experiment workspaces and future audit views.

## Dashboard Integration

The Daily Dashboard includes an `Experiments by lifecycle stage` section. This groups indexed experiments by current stage and helps identify work stuck in planning, waiting, imaging, analysis, or writing.

## Research Copilot Integration

Research Copilot uses lifecycle state as context for deterministic next actions. Examples:

- `Running` without image assets: import or link microscopy/image assets when imaging is complete.
- `Analysis` without statistics: complete statistics before making final claims.
- `Writing` without conclusions: add experiment conclusions before submission or archive.

These recommendations are suggestions only. ResearchOS never advances or edits experiments without an explicit action.

## Sessions

Experiment Sessions are designed to drive lifecycle state. When a session attached to an extracted experiment ends, ResearchOS can advance a `Running` experiment to `Waiting` and records that transition with session provenance.

## OneNote

Read-only OneNote pages are still imported as source notebook documents. Lifecycle stages are associated at the ResearchOS experiment/workspace level, while notebook entries remain immutable source evidence. Future write-back can optionally include lifecycle stage labels in generated OneNote entries after separate UCSD IT approval.

## Workspace

Experiment Workspace responses include:

- current stage
- allowed transitions
- completion criteria
- recommended next actions
- remaining stages
- transition history

Example:

```bash
curl http://127.0.0.1:8001/experiments/NK_Expt_31/workspace?use_ai=false
```

## Design Notes

The lifecycle engine is intentionally deterministic. It does not use AI to decide whether an experiment has advanced. AI providers may summarize lifecycle context, but the recorded stage only changes through explicit transition logic.
