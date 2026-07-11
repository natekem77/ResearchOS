# Reference System

ResearchOS supports two reference syntaxes:

- `@Name`
- `[[object_id or title]]`

`@` references are optimized for fast typing and autocomplete. `[[ ]]` references are stable and copyable.

## Autocomplete

When a user types `@`, clients should call:

```http
GET /objects/autocomplete?q=BMP4
```

Results include:

- icon
- title
- subtitle
- object type
- recent usage count
- pinned/favorited flags for future personalization

## Resolution

Resolution is stricter than autocomplete. Fuzzy candidates can appear in autocomplete, but a reference is only marked resolved when confidence is high enough.

```http
GET /objects/resolve?ref=@BMP4
POST /references/resolve
```

## Unavailable Objects

If a user lacks permission to see a target, the backend does not return object metadata. The UI should show the reference as unavailable.

## AI Context

Future AI features should pass object IDs where possible:

```json
{
  "question": "What do we know about this?",
  "object_ids": ["entity:BMP4", "NK_Expt_26"]
}
```

This gives AI systems structured context without relying only on free text.

