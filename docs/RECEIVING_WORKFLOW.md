# Receiving Workflow

Receiving records document items that have arrived in the lab after manual or Oracle purchasing.

The workflow is:

1. Create or submit a purchase request in ResearchOS.
2. Boss/admin orders the item through Oracle or another purchasing process.
3. When the item arrives, create a receiving record.
4. Convert the receiving record into a new inventory item or update an existing inventory quantity.
5. Add barcode/internal label and storage details for freezer or shelf organization.

ResearchOS does not connect directly to Oracle yet. Oracle PO, invoice, and grant details remain in purchase records and imported Oracle CSV reports.

## API Examples

Create a receiving record:

```bash
curl -X POST http://127.0.0.1:8001/receiving \
  -H "Content-Type: application/json" \
  -d '{
    "purchase_request_id":"purchase-request:example",
    "item_name":"BMP4",
    "vendor":"DemoBio",
    "catalog_number":"BMP4-001",
    "lot_number":"LOT-123",
    "quantity_received":2,
    "units":"vial",
    "received_by":"Nathan",
    "received_date":"2026-07-09",
    "expiration_date":"2027-01-01",
    "storage_location":"-20C freezer Box A",
    "barcode_or_label":"BMP4-A1"
  }'
```

Convert receiving into inventory:

```bash
curl -X POST http://127.0.0.1:8001/receiving/{receiving_id}/create-or-update-inventory \
  -H "Content-Type: application/json" \
  -d '{"update_existing":true}'
```

Export receiving records:

```bash
curl http://127.0.0.1:8001/receiving/export-csv
```

## Purchase Request Integration

When marking a purchase request received, ResearchOS can optionally create a receiving record:

```bash
curl -X POST http://127.0.0.1:8001/purchase-requests/{request_id}/mark-received \
  -H "Content-Type: application/json" \
  -d '{"create_receiving_record":true,"update_inventory_quantity":false}'
```

Use the receiving record as the review step before inventory intake when lot number, expiration, barcode, and storage location need to be confirmed.

## Future Barcode Intake

The mobile app currently shows a receiving placeholder. Future work will add phone camera scanning so a user can scan the package or internal label, confirm lot/expiration/storage, and create inventory from the bench or freezer.
