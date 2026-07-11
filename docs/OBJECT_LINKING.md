# Universal Scientific Object Linking

Object linking lets ResearchOS reference scientific records instead of duplicating them.

Examples:

- `@BMP4`
- `@Meyer Protocol`
- `[[NK_Expt_26]]`
- `[[inventory:...]]`
- `[[chat-message:...]]`

The backend resolves these references through `ResearchObjectService`.

## API

```bash
curl "http://127.0.0.1:8001/objects?limit=25"
curl "http://127.0.0.1:8001/objects/autocomplete?q=BMP4"
curl "http://127.0.0.1:8001/objects/resolve?ref=@BMP4"
curl "http://127.0.0.1:8001/objects/entity:BMP4/hover-card"
curl "http://127.0.0.1:8001/objects/entity:BMP4/backlinks"
```

Create an explicit link:

```bash
curl -X POST http://127.0.0.1:8001/references \
  -H "Content-Type: application/json" \
  -d '{
    "source_object_id": "notebook:researcher-a",
    "source_object_type": "Notebook",
    "target_object_id": "entity:BMP4",
    "reference_text": "@BMP4",
    "context": "Planning note"
  }'
```

## Rich Notes and Chat

Notebook saves and chat messages can be scanned for `@` and `[[ ]]` references. Resolved references become backlinks. Unresolved references remain visible to the user but are not converted into invented objects.

## No Duplication

The reference table stores only relationships:

- source object
- target object
- reference text
- context

The source scientific records remain in their provider tables.

