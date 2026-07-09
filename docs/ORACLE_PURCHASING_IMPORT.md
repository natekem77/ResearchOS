# Oracle Purchasing Import

ResearchOS can import Oracle purchasing exports and lab-maintained purchasing spreadsheets without requiring live Oracle API access.

Current status:

- Provider scaffold: `oracle_purchasing`
- Supported import: CSV text
- Live Oracle authentication: not implemented
- Excel import: planned future extension

## Recommended Workflow

1. Export the Oracle or department purchasing report as CSV.
2. Open ResearchOS Purchasing.
3. Paste the CSV into the flexible import panel.
4. Click **Preview Import**.
5. Review detected columns and suggested mappings.
6. Edit mappings if needed.
7. Optionally save the mapping as a template.
8. Import the mapped CSV.

## Preview Endpoint

```bash
curl -X POST http://127.0.0.1:8001/purchases/import-preview \
  -H "Content-Type: application/json" \
  -d '{"csv_text":"Item Description,Supplier,Catalog #,Order Date,Total Cost,Qty,Project/Grant,Requester,PO Number\nSAG,Demo Vendor,SAG-001,2026-07-08,125.00,1,Vision Grant,Nathan,PO-123\n"}'
```

Returns:

- detected columns
- suggested field mappings
- row preview
- warnings
- missing required fields

## Mapped Import Endpoint

```bash
curl -X POST http://127.0.0.1:8001/purchases/import-mapped-csv \
  -H "Content-Type: application/json" \
  -d '{
    "csv_text":"Item Description,Supplier,Catalog #,Order Date,Total Cost,Qty,Project/Grant,Requester,PO Number\nSAG,Demo Vendor,SAG-001,2026-07-08,125.00,1,Vision Grant,Nathan,PO-123\n",
    "mapping":{
      "item_name":"Item Description",
      "vendor":"Supplier",
      "catalog_number":"Catalog #",
      "purchase_date":"Order Date",
      "cost":"Total Cost",
      "quantity":"Qty",
      "grant_or_funding_source":"Project/Grant",
      "purchaser":"Requester",
      "oracle_po_number":"PO Number"
    }
  }'
```

`item_name` is required. Rows missing an item name after mapping are skipped and reported.

## Common Column Aliases

ResearchOS suggests mappings for common names:

- `item_name`: Item, Item Name, Description, Item Description, Product, Product Name
- `vendor`: Vendor, Supplier, Supplier Name, Manufacturer
- `catalog_number`: Catalog, Catalog #, Cat #, Catalog Number, Part Number, SKU
- `purchase_date`: Date, Purchase Date, Order Date, PO Date
- `cost`: Cost, Price, Total, Total Cost, Amount, Extended Amount
- `quantity`: Qty, Quantity, Units
- `grant_or_funding_source`: Grant, Fund, Funding Source, Project, Project/Grant, Chartstring
- `purchaser`: Purchaser, Requester, Ordered By
- `oracle_po_number`: PO, PO Number, Purchase Order, Oracle PO
- `invoice_number`: Invoice, Invoice Number
- `status`: Status, Order Status

## Mapping Templates

List templates:

```bash
curl http://127.0.0.1:8001/purchases/import-templates
```

Save a template:

```bash
curl -X POST http://127.0.0.1:8001/purchases/import-templates \
  -H "Content-Type: application/json" \
  -d '{"name":"Lab Oracle Export","mapping":{"item_name":"Item Description","vendor":"Supplier","oracle_po_number":"PO Number"}}'
```

Delete a saved template:

```bash
curl -X DELETE http://127.0.0.1:8001/purchases/import-templates/purchase_import_template:ID
```

The built-in `Oracle Purchasing Export` template cannot be deleted.

## Future Oracle API Integration

A future Oracle provider can add:

- OAuth or institution-approved Oracle authentication
- scheduled report sync
- purchase order status refresh
- invoice matching
- grant/fund validation
- reconciliation from purchases into inventory

Until then, ResearchOS treats Oracle as a CSV/report source.
