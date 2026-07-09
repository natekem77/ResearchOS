# Experiment Design Planner

The Experiment Design Planner is a provider-agnostic planning tool for multi-condition biological experiments.

It is not limited to retinal organoids. It can represent organoids, assembloids, stem cells, RPE, standard cell culture, animal work, sequencing prep, imaging experiments, and future experiment types.

## Core Objects

An `ExperimentDesign` stores the study-level plan:

- title
- experiment type
- model or cell line
- reporters
- description
- start date
- status
- optional linked experiment ID

A `DesignCondition` stores one treatment/control group:

- condition name
- treatment
- dose and units
- start/end day
- replicate count
- sample count

A `DesignEvent` stores timeline actions:

- day such as `D0`, `D1`, `D9`, `D32`
- event type such as treatment, media change, imaging, collection, staining, sequencing, analysis, or custom
- title and description
- alert/reminder settings
- completion state

## Example: Organoid D1/D9 Treatment Design

```bash
curl -X POST http://127.0.0.1:8001/experiment-designs \
  -H "Content-Type: application/json" \
  -d '{
    "title":"D1 SAG + GRKi rescue",
    "experiment_type":"retinal organoid",
    "cell_line_or_model":"SIX6 reporter iPSC",
    "reporters":["SIX6","BRN3B"],
    "status":"active"
  }'
```

Add a control condition:

```bash
curl -X POST http://127.0.0.1:8001/experiment-designs/{design_id}/conditions \
  -H "Content-Type: application/json" \
  -d '{
    "condition_name":"DMSO control",
    "treatment":"DMSO",
    "start_day":"D1",
    "end_day":"D9",
    "replicate_count":3,
    "sample_count":6
  }'
```

Add timeline events:

```bash
curl -X POST http://127.0.0.1:8001/experiment-designs/{design_id}/events \
  -H "Content-Type: application/json" \
  -d '{
    "day":"D32",
    "event_type":"imaging",
    "title":"Image SIX6/BRN3B/DAPI",
    "alert_enabled":true
  }'
```

## Example: Generic Cell Culture Design

A generic cell culture design can use the same model:

- experiment type: `cell culture`
- model: `HEK293T`
- conditions: untreated, vehicle, treatment A, treatment B
- events: plate cells, treat, media change, collect RNA, analyze qPCR

No biology-specific terms are hardcoded.

## CSV Import and Export

Export:

```bash
curl http://127.0.0.1:8001/experiment-designs/{design_id}/export-csv
```

Expected columns:

```text
design_id,experiment_title,experiment_type,cell_line_or_model,reporters,condition,replicate,day,event_type,treatment,dose,units,sample_id,notes,alert_enabled
```

Minimal import example:

```text
condition,day,event_type,treatment,dose,units,replicate,alert_enabled
DMSO control,D1,treatment,DMSO,,,1,true
SAG,D1,treatment,SAG,100,nM,1,true
SAG,D32,imaging,SAG,100,nM,1,true
```

Preview import:

```bash
curl -X POST http://127.0.0.1:8001/experiment-designs/import-preview \
  -H "Content-Type: application/json" \
  -d '{"csv_text":"condition,day,event_type\nDMSO,D1,treatment\n"}'
```

Import:

```bash
curl -X POST http://127.0.0.1:8001/experiment-designs/import-csv \
  -H "Content-Type: application/json" \
  -d '{"title":"Imported design","csv_text":"condition,day,event_type\nDMSO,D1,treatment\n"}'
```

## Reminders

Active designs generate dashboard/mobile reminders from reminder-enabled events. Draft designs do not appear as due unless explicitly requested through lower-level APIs.

```bash
curl http://127.0.0.1:8001/experiment-designs/reminders
curl http://127.0.0.1:8001/experiment-designs/reminders/due-today
curl "http://127.0.0.1:8001/experiment-designs/reminders/upcoming?days=7"
```

Activate a design:

```bash
curl -X POST http://127.0.0.1:8001/experiment-designs/{design_id}/activate
```

Complete or dismiss a reminder:

```bash
curl -X POST http://127.0.0.1:8001/experiment-designs/reminders/{event_id}/complete
curl -X POST http://127.0.0.1:8001/experiment-designs/reminders/{event_id}/dismiss
```

If `start_date` exists, ResearchOS calculates real calendar dates from `start_date + D-number - reminder_offset_days`. If no start date exists, reminders remain relative-day reminders.

Example reminder events:

- D1 SAG treatment: event type `treatment`, day `D1`, reminder enabled.
- D9 SAG treatment: event type `treatment`, day `D9`, reminder enabled.
- D32 imaging: event type `imaging`, day `D32`, reminder enabled.
- Sample collection: event type `collection`, day `D32` or any custom day label, reminder enabled.

Push notifications and Google/Outlook calendar sync are intentionally not implemented yet.

## Design of Experiments Foundation

Current helpers are intentionally basic:

```bash
curl -X POST http://127.0.0.1:8001/experiment-designs/doe/full-factorial \
  -H "Content-Type: application/json" \
  -d '{"factors":{"compound":["SAG","BMP4"],"dose":["low","high"]}}'

curl -X POST http://127.0.0.1:8001/experiment-designs/doe/check-balance \
  -H "Content-Type: application/json" \
  -d '{"conditions":[{"condition_name":"DMSO control","replicate_count":3},{"condition_name":"SAG","replicate_count":2}]}'
```

Future DoE work can add randomization, blocking, power calculations, blinded sample labels, plate maps, and integration with statistics workflows.

## Future Roadmap

- calendar export
- push/mobile reminders
- session-event completion from Bench Mode
- linked experiment creation
- plate maps and sample labels
- randomization and blinding
- power analysis
- integration with inventory availability
- OneNote draft generation from design timelines
