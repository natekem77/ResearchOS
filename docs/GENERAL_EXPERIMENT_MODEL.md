# General Experiment Model

ResearchOS now separates experiment work into two synchronized layers:

1. **Narrative workspace**: free-form scientific notes that researchers control.
2. **Structured plan**: cohorts, conditions, interventions, assays, protocol references, and timeline events.

Structured data must never overwrite notebook notes.

## ExperimentWorkspace

Core fields:

- `experiment_id`
- `lab_id`
- `owner_user_id`
- `title`
- `short_description`
- `status`: `draft`, `planned`, `active`, `paused`, `completed`, `archived`
- `biological_system`
- `sample_unit_type`
- `sample_unit_label`
- `start_date`
- `nominal_day_zero`
- `expected_end_day`
- `expected_end_date`
- `primary_protocol_id`
- `primary_protocol_version_id`

The model is system-agnostic. It supports organoids, assembloids, primary cells, tissue culture, biochemical assays, animal studies, sequencing experiments, imaging studies, and future systems.

## Structured Plan Objects

- `ExperimentCohort`
- `ExperimentCondition`
- `ExperimentIntervention`
- `ExperimentEvent`
- `ExperimentAssay`
- `ExperimentProtocolReference`

Events can represent protocol steps, treatments, media changes, collections, imaging, assays, observations, milestones, endpoints, reminders, or custom events.

## Migration

Legacy extracted experiments remain intact. A compatibility migration creates generalized workspace records where possible:

- organoid experiments become `biological_system = retinal organoid`
- organoid samples become `sample_unit_type = organoid`
- existing IDs remain valid where feasible

