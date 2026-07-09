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

The preview endpoint detects columns, suggests mappings, shows preview rows, infers conditions/event days/event types, reports missing required fields, and returns warnings.

Import:

```bash
curl -X POST http://127.0.0.1:8001/experiment-designs/import-csv \
  -H "Content-Type: application/json" \
  -d '{"title":"Imported design","csv_text":"condition,day,event_type\nDMSO,D1,treatment\n"}'
```

Import with explicit mappings:

```bash
curl -X POST http://127.0.0.1:8001/experiment-designs/import-mapped-csv \
  -H "Content-Type: application/json" \
  -d '{
    "csv_text":"Experiment,Condition,Day,Event,Treatment,Replicate,Reminder\nD1 SAG,DMSO,D1,treatment,DMSO,1,true\n",
    "mapping":{
      "title":"Experiment",
      "condition_name":"Condition",
      "day":"Day",
      "event_type":"Event",
      "treatment":"Treatment",
      "replicate":"Replicate",
      "alert_enabled":"Reminder"
    }
  }'
```

Saved mapping templates:

```bash
curl http://127.0.0.1:8001/experiment-designs/import-templates
curl -X POST http://127.0.0.1:8001/experiment-designs/import-templates \
  -H "Content-Type: application/json" \
  -d '{"name":"Organoid design sheet","mapping":{"condition_name":"Group","day":"Timepoint","event_type":"Action"}}'
```

See [DESIGN_IMPORT_FORMATS.md](DESIGN_IMPORT_FORMATS.md) for supported aliases and examples.

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

## Calendar Export

ResearchOS can export dated design reminders as `.ics` calendar files for Outlook, Google Calendar, and Apple Calendar.

```bash
curl http://127.0.0.1:8001/experiment-designs/{design_id}/export-ics
curl http://127.0.0.1:8001/experiment-designs/reminders/export-ics
```

Calendar export requires `start_date` on each exported design. If a single design has no `start_date`, ResearchOS returns a clear error because relative labels such as `D1` or `D32` cannot be placed on a real calendar. The all-reminders export includes dated reminders and skips undated relative reminders.

This creates a one-time calendar file. It does not create live Google Calendar, Outlook, Apple Calendar, or push-notification sync.

See [CALENDAR_EXPORT.md](CALENDAR_EXPORT.md) for import instructions.

## Design Templates

Reusable design templates can store common condition/event/reminder patterns for repeated workflows.

```bash
curl http://127.0.0.1:8001/experiment-design-templates
curl http://127.0.0.1:8001/experiment-design-templates/builtin:retinal_organoid_d1_d9_treatment
curl -X POST http://127.0.0.1:8001/experiment-design-templates/builtin:retinal_organoid_d1_d9_treatment/create-design \
  -H "Content-Type: application/json" \
  -d '{"title":"My D1/D9 treatment comparison","start_date":"2026-07-08","cell_line_or_model":"SIX6 reporter iPSC","reporters":["SIX6","BRN3B"]}'
```

The built-in demo templates include retinal organoid D1/D9 treatment, immunostaining/D32 imaging, generic cell culture treatment timecourse, and sample collection timecourse.

Existing designs can also be saved as templates:

```bash
curl -X POST http://127.0.0.1:8001/experiment-designs/{design_id}/save-template \
  -H "Content-Type: application/json" \
  -d '{"name":"My reusable staining workflow"}'
```

See [EXPERIMENT_DESIGN_TEMPLATES.md](EXPERIMENT_DESIGN_TEMPLATES.md) for the full template workflow.

## Plate and Sample Layouts

Experiment designs can generate practical plate, well, tube rack, or custom sample layouts.

```bash
curl -X POST http://127.0.0.1:8001/experiment-designs/{design_id}/generate-plate-layout \
  -H "Content-Type: application/json" \
  -d '{"format":"96-well","balanced":true,"grouped_by_condition":true}'

curl http://127.0.0.1:8001/plate-layouts/{layout_id}/export-csv
```

See [PLATE_LAYOUT_PLANNER.md](PLATE_LAYOUT_PLANNER.md) for 96-well and 24-well examples.

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

- push/mobile reminders
- live Google/Outlook/Apple Calendar sync
- session-event completion from Bench Mode
- linked experiment creation
- plate maps and sample labels
- randomization and blinding
- power analysis
- integration with inventory availability
- OneNote draft generation from design timelines
