# New Experiment Wizard

The New Experiment Wizard is the primary entry point for starting scientific work in ResearchOS. It guides scientists through planning an experiment before work begins at the bench.

## Purpose

The wizard reduces typing, encourages consistent metadata, and prepares experiments for future OneNote synchronization without writing to OneNote automatically.

It creates standard ResearchOS objects:

- Experiment
- ResearchDocument planning note
- Experiment Workflow
- Experiment Workspace
- Timeline/workflow history
- Knowledge Graph relationships through normal metadata indexing
- Optional pending notebook draft
- Optional active Bench Mode session

## Workflow

### Step 1: Experiment Information

Fields:

- Experiment title
- Experiment ID
- Project
- Workspace
- Principal investigator
- Researcher
- Date
- Notes

Experiment title and Experiment ID are required.

### Step 2: Protocol

Scientists can select an existing protocol or create a new protocol planning reference.

The current implementation stores the selected or new protocol information in the planning document and experiment metadata. Full protocol creation/versioning remains part of Protocol Intelligence.

### Step 3: Experimental Design

Fields:

- Cell line
- Organoid batch
- Treatments
- Compounds
- Concentrations
- Timepoints
- Replicates
- Controls

Controls are required before continuing. This is a gentle planning guardrail, not a production policy engine.

### Step 4: Expected Readouts

Fields:

- Markers/entities
- Microscopy
- GraphPad
- RNA-seq
- Flow cytometry
- Other readouts

The wizard does not hardcode marker names. It uses Knowledge Graph search so existing ontology terms can be reused, while still allowing new scientific terms to be preserved.

### Step 5: Timeline

The default timeline includes:

- Notebook
- Media changes
- Treatment
- Imaging
- Statistics

Users can add or remove milestones before creation.

### Step 6: Summary

The summary step shows the planned experiment and lets the user jump back to edit any section.

Options:

- Create notebook draft
- Start Bench Mode session

Save to OneNote remains disabled until OneNote write-back is approved.

## API

Create from desktop/backend:

```bash
curl -X POST http://127.0.0.1:8001/experiments/create \
  -H "Content-Type: application/json" \
  -d '{
    "title":"Early SAG + GRKi retinal rescue",
    "experiment_id":"NK_Expt_81",
    "project":"Retinal organoids",
    "researcher":"Nathan",
    "date":"2026-07-08",
    "cell_line":"SIX6 reporter iPSC",
    "organoid_batch":"Batch D32",
    "compounds":["SAG","GRKi"],
    "concentrations":["100 nM","250 nM"],
    "timepoints":["D1","D32"],
    "controls":["DMSO"],
    "readouts":["microscopy","quantification"],
    "markers":["SIX6","BRN3B"],
    "microscopy":true,
    "graphpad":true,
    "create_notebook_draft":true,
    "start_session":false
  }'
```

Create from mobile:

```bash
curl -X POST http://127.0.0.1:8001/mobile/experiments/create \
  -H "Content-Type: application/json" \
  -d '{"title":"Wizard smoke experiment","experiment_id":"WIZARD-1","controls":["DMSO"],"readouts":["microscopy"]}'
```

## OneNote Behavior

The wizard never writes directly to OneNote.

Current safe options:

- Create ResearchOS notebook draft
- Copy/export draft Markdown through pending-entry workflow

Future option:

- Save to OneNote after UCSD IT approves Notes.Create or Notes.ReadWrite.

## Research Copilot

The local deterministic Copilot checks:

- Missing controls
- Missing replicate count
- Missing readouts
- GraphPad selected without replicate information
- Related previous experiments based on shared entities

It does not invent observations.

## Testing

Recommended checks:

```bash
cd backend
python -m pytest tests/test_new_experiment_wizard.py
```

Full regression:

```bash
RESEARCHOS_OPEN_BROWSER=0 ./scripts/demo.sh && ./scripts/smoke_test.sh
```

Flutter:

```bash
cd mobile/researchos_mobile
flutter analyze
flutter test
```
