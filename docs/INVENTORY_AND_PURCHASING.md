# Inventory and Purchasing

ResearchOS includes a local-first inventory and purchasing foundation for lab operations, reagent tracking, paper methods sections, grant tracking, and future Oracle purchasing integration.

This milestone does not connect to Oracle directly. It supports manual entry, exported CSV reports, flexible import mappings, and saved mapping templates.

## Inventory

Inventory items track:

- name
- category
- vendor
- catalog number
- lot number
- RRID
- price
- unit
- storage location
- quantity
- reorder threshold
- expiration date
- notes
- linked ResearchOS resource

Inventory can be exported as CSV:

```bash
curl http://127.0.0.1:8001/inventory/export-csv
```

## Inventory Status and Reordering

ResearchOS derives operational inventory status without changing the stored inventory schema:

- `in_stock`
- `low_stock`
- `expired`
- `expiring_soon`
- `reorder_needed`

Reorder logic:

- `reorder_needed` is true when `quantity <= reorder_threshold`.
- `expired` is true when `expiration_date` is in the past.
- `expiring_soon` is true when `expiration_date` is within 90 days.
- Expiring windows are grouped into 30, 60, and 90 day buckets.

Endpoints:

```bash
curl http://127.0.0.1:8001/inventory/status
curl http://127.0.0.1:8001/inventory/reorder-needed
curl http://127.0.0.1:8001/inventory/expiring
```

## Purchasing

Purchase records track:

- item name
- vendor
- catalog number
- purchase date
- cost
- quantity
- grant or funding source
- purchaser
- Oracle PO number
- invoice number
- status
- notes

Purchases can be exported as CSV:

```bash
curl http://127.0.0.1:8001/purchases/export-csv
```

## Grant Spend Dashboard

Purchasing summaries are computed from local purchase records and imported CSV reports:

```bash
curl http://127.0.0.1:8001/purchases/summary
curl http://127.0.0.1:8001/purchases/by-grant
```

The summary includes:

- total spend
- spend by grant or funding source
- spend by vendor
- spend by month
- recent purchases

This is intended for day-to-day lab tracking and grant review. It is not a live Oracle balance and does not replace official institutional financial reporting.

## Oracle-Ready CSV Import

The current provider scaffold is:

- provider: `oracle_purchasing`
- mode: CSV import/export only
- live Oracle API: not implemented

ResearchOS preserves Oracle-style fields such as PO number, purchase date, item, vendor, cost, and grant/funding source.

Example:

```bash
curl -X POST http://127.0.0.1:8001/purchases/import-csv \
  -H "Content-Type: application/json" \
  -d '{"csv_text":"PO Number,Supplier,Item,Amount,Grant\nPO-123,Demo Vendor,SAG,125.00,Vision Grant\n"}'
```

Flexible imports are available when Oracle reports or lab-maintained spreadsheets use different column names:

```bash
curl -X POST http://127.0.0.1:8001/purchases/import-preview \
  -H "Content-Type: application/json" \
  -d '{"csv_text":"Item Description,Supplier,Catalog #,Order Date,Total Cost\nSAG,Demo Vendor,SAG-001,2026-07-08,125.00\n"}'
```

Then import with an explicit mapping:

```bash
curl -X POST http://127.0.0.1:8001/purchases/import-mapped-csv \
  -H "Content-Type: application/json" \
  -d '{
    "csv_text":"Item Description,Supplier,Catalog #,Order Date,Total Cost\nSAG,Demo Vendor,SAG-001,2026-07-08,125.00\n",
    "mapping":{
      "item_name":"Item Description",
      "vendor":"Supplier",
      "catalog_number":"Catalog #",
      "purchase_date":"Order Date",
      "cost":"Total Cost"
    }
  }'
```

Excel import is a future extension. For now, export Oracle/department purchasing reports as CSV before importing.

See [ORACLE_PURCHASING_IMPORT.md](ORACLE_PURCHASING_IMPORT.md) for mapping templates and troubleshooting.

## Methods Citation Helper

Inventory items can generate reusable reagent text for paper methods sections:

```bash
curl http://127.0.0.1:8001/inventory/inventory:ITEM_ID/methods-citation
```

Example output:

```text
Anti-BRN3B (DemoBio, catalog AB-123, RRID RRID:AB_123, lot LOT-85)
```

This helps keep vendor, catalog number, RRID, and lot details consistent across manuscripts and protocols.

## Reagent Methods Builder

ResearchOS can combine multiple inventory records into a draft reagent/materials paragraph:

```bash
curl -X POST http://127.0.0.1:8001/methods/reagents \
  -H "Content-Type: application/json" \
  -d '{"inventory_item_ids":["inventory:ITEM_ID"],"style":"paper"}'
```

Experiment-linked reagent context is available with:

```bash
curl http://127.0.0.1:8001/experiments/NK_Expt_31/reagents
curl http://127.0.0.1:8001/experiments/NK_Expt_31/methods-materials
```

ResearchOS does not invent catalog numbers, RRIDs, lot numbers, or concentrations. Missing fields are returned as warnings so the lab can clean up inventory records before using the text in a manuscript.

See [METHODS_REAGENT_BUILDER.md](METHODS_REAGENT_BUILDER.md) for details.

## Relationship to Resources

Inventory items may link to first-class ResearchOS Resources. Resources represent reusable scientific materials across experiments, protocols, sessions, notebooks, statistics, microscopy, literature, and future manuscript drafting.

Inventory answers operational questions such as:

- How much is left?
- Where is it stored?
- Should we reorder?
- Which lot did we use?

Resources answer scientific context questions such as:

- Which experiments used this reagent?
- Which protocols mention it?
- Which methods section should cite it?

## Shared Spreadsheet Replacement

The CSV export endpoints are designed so labs can keep using shared spreadsheets during transition:

- Export from ResearchOS to CSV
- Import purchasing reports from Oracle/exported spreadsheets
- Keep ResearchOS as the structured source over time

## Future Oracle Integration

Future Oracle integration should add:

- authenticated Oracle provider
- scheduled purchase report sync
- PO status updates
- invoice matching
- grant/fund validation
- purchase-to-inventory reconciliation

No Oracle authentication or API calls are implemented yet.
