# Methods Reagent Builder

ResearchOS can generate paper-ready reagent and materials text from local inventory records.

The builder is conservative:

- It never invents missing vendor names.
- It never invents catalog numbers.
- It never invents RRIDs.
- It never invents lot numbers.
- It returns warnings when citation-critical metadata is missing.

## Build Text from Inventory Items

```bash
curl -X POST http://127.0.0.1:8001/methods/reagents \
  -H "Content-Type: application/json" \
  -d '{
    "inventory_item_ids":["inventory:ITEM_ID"],
    "style":"paper"
  }'
```

Supported styles:

- `paper`: manuscript-style paragraph
- `grant`: concise grant materials sentence
- `protocol`: bullet list for protocols

Optional fields:

- `include_lot_numbers`: default `true`
- `include_storage_locations`: default `false`

## Experiment Reagent Context

```bash
curl http://127.0.0.1:8001/experiments/NK_Expt_31/reagents
```

This returns inventory items and ResearchOS resources linked to an experiment.

Matching currently uses:

- explicit inventory-to-resource links
- resource usages linked to the experiment
- resource names/aliases matching experiment compounds, markers, antibodies, treatments, cell lines, or organoid batches

## Draft Materials/Reagents Section

```bash
curl http://127.0.0.1:8001/experiments/NK_Expt_31/methods-materials
```

This returns a draft section plus warnings.

Example text:

```text
Reagents and materials used in this study included Anti-BRN3B (DemoBio, catalog AB-123, RRID RRID:AB_123, lot LOT-85).
```

## Manuscript Safety

Before using generated text in a manuscript:

1. Review all warnings.
2. Confirm vendor and catalog numbers against the reagent label or purchase record.
3. Confirm RRIDs for antibodies when available.
4. Decide whether lot numbers should be included in the manuscript, supplement, or internal protocol only.

## Future Extensions

Future versions should connect this builder to:

- protocol methods sections
- manuscript workspaces
- grant workspaces
- inventory reorder workflows
- Oracle purchasing records
- OneNote notebook draft generation
