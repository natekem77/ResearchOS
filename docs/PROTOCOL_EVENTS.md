# Protocol Events

Protocol events define baseline scientific workflow steps. They are reusable timeline atoms that experiments can inherit.

## Event Fields

- `event_id`
- `protocol_version_id`
- `title`
- `description`
- `relative_day`
- `relative_hour`
- `event_type`
- `default_duration`
- `required`
- `default_resource`
- `default_concentration`
- `default_units`
- `metadata`

## Supported Event Types

- `media_change`
- `compound`
- `collection`
- `imaging`
- `passage`
- `qc`
- `assay`
- `custom`

Existing generalized events may also use `protocol_step`, `treatment`, `observation`, or other future provider-defined event types.

## Inheritance

When an experiment starts from a protocol version, ResearchOS creates experiment events that preserve:

- source protocol version
- source protocol event ID
- event title/type/day
- source marker: `protocol`

If an experiment modifies a step later, the override should be stored on the experiment while the original protocol event remains unchanged.

## Example

```json
{
  "title": "BMP4",
  "relative_day": 6,
  "event_type": "compound",
  "default_concentration": "protocol-defined",
  "required": true
}
```

## Calendar and Timeline Use

Protocol events provide relative timing. Real calendar dates are calculated only after an experiment supplies a start date or nominal day zero.

