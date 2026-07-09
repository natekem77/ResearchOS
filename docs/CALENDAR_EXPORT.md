# Calendar Export

ResearchOS can export Experiment Design Planner reminders as `.ics` calendar files. Researchers can import these files into Outlook, Google Calendar, or Apple Calendar to put treatment, media change, collection, imaging, staining, sequencing, and analysis reminders on their calendar.

This is a one-time file export. ResearchOS does not perform live calendar sync yet, and it does not send push notifications.

## Requirements

Calendar export requires a design `start_date`. Relative day labels such as `D1`, `D9`, or `D32` are converted to real calendar dates from the start date.

If a design has no `start_date`, the export endpoint returns a helpful error instead of creating ambiguous calendar events.

## Endpoints

Export one design:

```bash
curl http://127.0.0.1:8001/experiment-designs/{design_id}/export-ics \
  -o researchos_design.ics
```

Export all active reminders:

```bash
curl http://127.0.0.1:8001/experiment-designs/reminders/export-ics \
  -o researchos_reminders.ics
```

Upcoming reminders remain available as JSON:

```bash
curl "http://127.0.0.1:8001/experiment-designs/reminders/upcoming?days=7"
```

## What Each Calendar Event Includes

Each exported calendar event includes:

- design title
- condition name when available
- event type
- day label
- real calendar date
- description
- ResearchOS design ID
- linked experiment ID when available
- reminder status

## Import Into Outlook

1. Download the `.ics` file from ResearchOS.
2. Open Outlook Calendar.
3. Choose import/open calendar from file.
4. Select the `.ics` file.
5. Review the imported ResearchOS reminders.

## Import Into Google Calendar

1. Download the `.ics` file from ResearchOS.
2. Open Google Calendar in a browser.
3. Go to Settings, then Import & export.
4. Choose the `.ics` file.
5. Select the target calendar.
6. Click Import.

## Import Into Apple Calendar

1. Download the `.ics` file from ResearchOS.
2. Open Calendar on macOS.
3. Choose File, then Import.
4. Select the `.ics` file.
5. Choose the destination calendar.

## Limitations

- Calendar export is not live sync.
- Editing an event in Outlook, Google Calendar, or Apple Calendar does not update ResearchOS.
- Completing or dismissing a ResearchOS reminder does not update an already-imported calendar event.
- Push notifications are not implemented yet.
- Designs without `start_date` cannot be exported.
