# Inventory Usage Tracking

ResearchOS tracks where inventory items and reagents are used across experiments, sessions, protocols, and methods sections.

## Usage Model

Each usage record stores:

- `usage_id`
- `inventory_item_id`
- `experiment_id`
- `session_id`
- `protocol_id`
- `amount_used`
- `units`
- `date_used`
- `used_by`
- `purpose`
- `notes`

## Record Usage by Experiment

```bash
curl -X POST http://127.0.0.1:8001/experiments/NK_Expt_31/inventory-usage \
  -H "Content-Type: application/json" \
  -d '{
    "inventory_item_id":"inventory:ITEM_ID",
    "amount_used":0.5,
    "units":"vial",
    "purpose":"SAG treatment",
    "notes":"Used during D1 treatment.",
    "decrement_quantity":false
  }'
```

`decrement_quantity` is optional and defaults to `false`. When enabled, ResearchOS subtracts `amount_used` from the inventory quantity.

## Record Usage by Item

```bash
curl -X POST http://127.0.0.1:8001/inventory/inventory:ITEM_ID/usage \
  -H "Content-Type: application/json" \
  -d '{
    "experiment_id":"NK_Expt_31",
    "amount_used":1,
    "units":"aliquot",
    "purpose":"Immunostaining"
  }'
```

## View Usage

```bash
curl http://127.0.0.1:8001/inventory/inventory:ITEM_ID/usage
curl http://127.0.0.1:8001/experiments/NK_Expt_31/inventory-usage
```

## Timeline and Methods Integration

When a usage record includes `session_id`, ResearchOS appends a session timeline event.

Experiment timelines include reagent-use events automatically.

Experiment Materials/Reagents drafts prefer actual usage records when available, then fall back to inventory/resource links inferred from the experiment metadata.

## Knowledge Graph and Resources

If an inventory item is linked to a ResearchOS Resource, recording usage creates a resource usage link to the experiment. This allows future Knowledge Graph, manuscript, and grant workflows to trace reagent usage back to a structured inventory record.

## Bench Mode

The mobile Bench Mode includes a **Use Reagent** action. It records reagent usage against the active experiment session using the same backend endpoint.

## Current Limitations

- Barcode scanning is not implemented yet.
- Lot selection is manual.
- Protocol-level usage is stored as metadata but no protocol UI workflow exists yet.
- Oracle purchasing remains CSV/import based; no live Oracle integration is implemented.
