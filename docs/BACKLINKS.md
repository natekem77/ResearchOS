# Backlinks

Backlinks answer: “Who references this object?”

Examples:

- BMP4 used in protocol materials
- SAG referenced in experiments, notebooks, GraphPad files, and chat
- Meyer protocol linked to experiments
- Inventory item used in methods and sessions

## API

```bash
curl "http://127.0.0.1:8001/objects/entity:BMP4/backlinks"
curl "http://127.0.0.1:8001/objects/NK_Expt_26/references"
```

## Explicit and Implicit Backlinks

Explicit backlinks come from the `research_object_references` table.

Implicit backlinks are detected from visible object titles and metadata. They are useful for previews but should not replace explicit references in notebooks or chat.

## Permissions

Backlinks only include visible source objects. Private notebooks and private chats are excluded unless the current user is authorized to read them.

## Knowledge Graph

References can be used to refresh or augment Knowledge Graph relationships. The object linker provides stable source and target IDs so future graph updates can avoid fragile free-text matching.
