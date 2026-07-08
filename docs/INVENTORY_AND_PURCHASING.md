# Inventory and Purchasing

ResearchOS includes a local-first inventory and purchasing foundation for lab operations, reagent tracking, paper methods sections, grant tracking, and future Oracle purchasing integration.

This milestone does not connect to Oracle directly. It supports manual entry and imported CSV reports.

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

Excel import is a future extension. For now, export Oracle/department purchasing reports as CSV before importing.

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
