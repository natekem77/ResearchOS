# Workflow Engine

The ResearchOS Workflow Engine is the generic orchestration layer for research progress. Experiments are the first supported workflow, but the same model is designed for future workflows such as protocol development, RNA-seq analysis, microscopy analysis, manuscripts, grants, patents, publications, collaborations, and review/approval flows.

## Core Objects

- `WorkflowDefinition`: the reusable definition for a workflow type.
- `WorkflowState`: the current stage for one workflow subject.
- `WorkflowTransition`: a validated move from one stage to another.
- `WorkflowHistory`: immutable transition history.
- Workflow notes: stage-associated notes that preserve context without editing source notebooks.

The implementation lives in `backend/app/workflow_engine.py`. Generic workflow state is stored locally in SQLite tables:

- `workflow_states`
- `workflow_history`
- `workflow_notes`

## Experiment Workflow

The first workflow type is `experiment`.

Canonical stages:

- Planning
- Approved
- Running
- Media Changes
- Treatment
- Waiting
- Imaging
- Quantification
- Statistics
- Interpretation
- Writing
- Submitted
- Published
- Archived
- Cancelled

Each stage defines:

- Description
- Allowed transitions
- Completion criteria
- Required assets
- Recommended actions
- Blocking issues

Example progression:

```text
Planning -> Approved -> Running -> Media Changes -> Treatment -> Waiting
-> Imaging -> Quantification -> Statistics -> Interpretation -> Writing
-> Submitted -> Published
```

## API

List workflows:

```bash
curl http://127.0.0.1:8001/workflows
```

View workflow definitions:

```bash
curl http://127.0.0.1:8001/workflows/definitions
```

Get one workflow:

```bash
curl http://127.0.0.1:8001/workflows/workflow:experiment:experiment:abc123
```

Get the workflow for an experiment reference:

```bash
curl http://127.0.0.1:8001/workflows/experiment/NK_Expt_31
```

Transition a workflow:

```bash
curl -X POST http://127.0.0.1:8001/workflows/workflow:experiment:experiment:abc123/transition \
  -H "Content-Type: application/json" \
  -d '{
    "to_stage": "Approved",
    "reason": "Plan reviewed with PI",
    "actor": "Nathan"
  }'
```

Append a workflow note:

```bash
curl -X POST http://127.0.0.1:8001/workflows/workflow:experiment:experiment:abc123/note \
  -H "Content-Type: application/json" \
  -d '{
    "note": "Need to confirm media-change timing before treatment.",
    "actor": "Nathan"
  }'
```

## Event Integration

Workflow transitions publish `WorkflowTransitioned`.

Workflow notes publish `WorkflowNoteAdded`.

The Automation Engine treats these as upstream events and emits derived updates such as:

- `TimelineUpdated`
- `KnowledgeGraphUpdated`
- `DashboardUpdated`
- `SearchIndexUpdated`
- `WorkspaceUpdated`

This allows future providers and agents to react to workflow changes without coupling directly to experiment-specific code.

## Timeline Integration

Experiment timelines include workflow transition events with:

- timestamp
- event type `workflow_transition`
- from stage
- to stage
- reason
- actor

## Dashboard Integration

The Daily Dashboard groups experiments by workflow stage. This supports views such as:

- Running
- Waiting
- Needs Imaging
- Needs Statistics
- Ready for Writing

Current implementation groups by current workflow stage and uses provider evidence to calculate blocking issues and suggested next actions.

## Workspace Integration

Experiment Workspace responses include:

- Current workflow stage
- Progress indicator
- Completed stages
- Remaining stages
- Suggested next actions
- Blocking issues
- Workflow history
- Workflow notes

Source notebook entries remain read-only, but workspace notebook records are associated with the current workflow stage for context.

## Research Copilot Integration

Research Copilot consumes workflow context and remains deterministic when AI is not configured.

Examples:

- Images but no GraphPad/quantification: suggest running GraphPad analysis or importing a quantification spreadsheet.
- GraphPad assets but no notebook observations: suggest completing notebook observations.
- Statistics available at Statistics or Interpretation stage: suggest reviewing statistical significance and limitations.

Copilot must not invent observations. Workflow suggestions are labeled as suggested actions.

## Sessions

Experiment Sessions can update workflows automatically when appropriate. For example, ending a session attached to an extracted experiment can move a `Running` workflow to `Waiting` and records the transition with session provenance.

## OneNote

OneNote remains read-only in the current MVP. Imported notebook pages become source documents. Workflow stage associations are maintained in ResearchOS workspace metadata and workflow notes rather than by modifying OneNote.

Future OneNote write-back can include workflow context after separate UCSD IT approval for write permissions.

## Future Workflow Types

The engine is designed so future definitions can be added without redesigning storage:

- Protocol Development
- RNA-seq Analysis
- Microscopy Analysis
- Manuscript
- Grant
- Patent
- Publication
- Collaboration/review workflows

Future providers should publish events and contribute evidence. Workflows should orchestrate state and next actions.
