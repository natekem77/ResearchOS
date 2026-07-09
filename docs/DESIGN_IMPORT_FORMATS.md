# Experiment Design Import Formats

ResearchOS can import existing experiment design spreadsheets even when column names differ across labs or projects.

The importer is local-first and creates a new `ExperimentDesign` with `DesignConditions` and `DesignEvents`. It does not overwrite existing designs unless a future workflow explicitly adds confirmation behavior.

## Preview Endpoint

```bash
curl -X POST http://127.0.0.1:8001/experiment-designs/import-preview \
  -H "Content-Type: application/json" \
  -d '{"csv_text":"Experiment,Condition,Day,Event\nD1 SAG,DMSO,D1,treatment\n"}'
```

The preview response includes:

- detected columns
- suggested mappings
- preview rows
- inferred conditions
- inferred event days
- inferred event types
- warnings
- missing required fields

## Mapped Import Endpoint

```bash
curl -X POST http://127.0.0.1:8001/experiment-designs/import-mapped-csv \
  -H "Content-Type: application/json" \
  -d '{
    "csv_text":"Experiment,Type,Cell Line,Condition,Day,Event,Treatment,Dose,Units,Replicate,Reminder\nD1 SAG,organoid,SIX6 reporter,DMSO,D1,treatment,DMSO,,,1,true\n",
    "mapping":{
      "title":"Experiment",
      "experiment_type":"Type",
      "cell_line_or_model":"Cell Line",
      "condition_name":"Condition",
      "day":"Day",
      "event_type":"Event",
      "treatment":"Treatment",
      "dose":"Dose",
      "units":"Units",
      "replicate":"Replicate",
      "alert_enabled":"Reminder"
    }
  }'
```

Required mapped fields:

- `condition_name`
- `day`

Optional mapped fields:

- `title`
- `experiment_type`
- `cell_line_or_model`
- `reporters`
- `treatment`
- `dose`
- `units`
- `event_type`
- `sample_id`
- `replicate`
- `notes`
- `alert_enabled`

## Supported Aliases

ResearchOS suggests mappings from these common headers:

- `title`: Experiment, Experiment Title, Design, Study
- `cell_line_or_model`: Cell Line, Model, Line, Organoid Line, Cell Model
- `reporters`: Reporter, Reporters, Genotype
- `condition_name`: Condition, Group, Treatment Group
- `treatment`: Treatment, Compound, Drug, Perturbation
- `day`: Day, Timepoint, Time Point, Collection Day, Imaging Day
- `event_type`: Event, Action, Procedure, Assay
- `sample_id`: Sample, Sample ID, Well, Tube
- `replicate`: Replicate, Rep, N

Additional practical aliases are also recognized for dose, units, notes, and reminders.

## Saved Templates

List templates:

```bash
curl http://127.0.0.1:8001/experiment-designs/import-templates
```

Save a template:

```bash
curl -X POST http://127.0.0.1:8001/experiment-designs/import-templates \
  -H "Content-Type: application/json" \
  -d '{"name":"Lab design spreadsheet","mapping":{"condition_name":"Group","day":"Time Point","event_type":"Action","alert_enabled":"Reminder"}}'
```

Delete a saved template:

```bash
curl -X DELETE http://127.0.0.1:8001/experiment-designs/import-templates/{template_id}
```

Default templates are built in and cannot be deleted.

## Reminder Columns

If a mapped `alert_enabled` or reminder-style column contains values such as `true`, `1`, `yes`, `enabled`, `reminder`, or `alert`, ResearchOS creates reminder-enabled design events.

Calendar export still requires the resulting design to have a `start_date`.
