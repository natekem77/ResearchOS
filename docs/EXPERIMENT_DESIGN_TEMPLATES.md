# Experiment Design Templates

Experiment Design Templates let researchers save, reuse, and modify common experimental workflows.

Templates are useful for repeated work such as retinal organoid differentiation, D1/D9 treatment comparisons, immunostaining schedules, imaging schedules, sample collection timecourses, and generic cell culture treatment experiments.

## Template Model

An `ExperimentDesignTemplate` stores:

- template ID
- name
- description
- experiment type
- default cell line or model
- default reporters
- default conditions
- default events
- default reminders
- creator metadata
- tags

Templates are not active experiments. Creating from a template copies its default conditions and events into a new `ExperimentDesign`.

## Built-In Demo Templates

ResearchOS includes these built-in templates:

- Retinal organoid D1 vs D9 treatment
- Immunostaining and D32 imaging
- Generic cell culture treatment timecourse
- Sample collection timecourse

Built-in templates can be used directly but cannot be edited or deleted. To customize one, create a design from it, edit the design, then save that design as a new template.

## API

List templates:

```bash
curl http://127.0.0.1:8001/experiment-design-templates
```

Get one template:

```bash
curl http://127.0.0.1:8001/experiment-design-templates/builtin:retinal_organoid_d1_d9_treatment
```

Create a saved template:

```bash
curl -X POST http://127.0.0.1:8001/experiment-design-templates \
  -H "Content-Type: application/json" \
  -d '{
    "name":"D32 staining workflow",
    "description":"Fix, stain, image, and quantify around D32.",
    "experiment_type":"immunostaining",
    "default_reporters":["SIX6","BRN3B","DAPI"],
    "default_conditions":[{"condition_name":"Staining batch","start_day":"D32","sample_count":6}],
    "default_events":[
      {"day":"D32","event_type":"fixation","title":"Fix samples","reminder_enabled":true},
      {"day":"D35","event_type":"imaging","title":"Confocal imaging","reminder_enabled":true}
    ],
    "tags":["immunostaining","imaging"]
  }'
```

Create a new design from a template:

```bash
curl -X POST http://127.0.0.1:8001/experiment-design-templates/builtin:retinal_organoid_d1_d9_treatment/create-design \
  -H "Content-Type: application/json" \
  -d '{
    "title":"NK D1 vs D9 SAG comparison",
    "start_date":"2026-07-08",
    "cell_line_or_model":"SIX6 reporter iPSC",
    "reporters":["SIX6","BRN3B"],
    "status":"draft"
  }'
```

Save an existing design as a template:

```bash
curl -X POST http://127.0.0.1:8001/experiment-designs/{design_id}/save-template \
  -H "Content-Type: application/json" \
  -d '{"name":"My reusable D1 SAG workflow"}'
```

Update or delete a saved template:

```bash
curl -X PUT http://127.0.0.1:8001/experiment-design-templates/{template_id} \
  -H "Content-Type: application/json" \
  -d '{"name":"Updated template","default_conditions":[],"default_events":[]}'

curl -X DELETE http://127.0.0.1:8001/experiment-design-templates/{template_id}
```

## Create-Design Behavior

`create-design` copies:

- template conditions
- template events
- reminder flags from template events

It accepts overrides for:

- title
- start date
- cell line/model
- reporters
- status

The resulting object is a normal `ExperimentDesign`, so timeline, reminders, CSV export, and calendar export work the same way as manually created designs.

## UI Workflow

The web app includes a Design Templates page. Users can:

- preview built-in and saved templates
- create a design from a template
- save an existing design as a template
- delete saved templates

Built-in templates are read-only.
