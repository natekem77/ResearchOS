# Purchase Requests

Purchase requests are the pre-Oracle workflow for asking the lab to buy a reagent, consumable, or replacement inventory item.

ResearchOS does not connect directly to Oracle yet. The intended workflow is:

1. Lab member creates a request in ResearchOS.
2. Boss/admin reviews submitted requests.
3. Approved requests are ordered manually in Oracle.
4. Oracle purchase exports are imported back into ResearchOS as purchase records.
5. Received requests can update linked inventory quantities.

## Statuses

- `draft`: Request is being prepared.
- `submitted`: Ready for boss/admin review.
- `approved`: Approved for Oracle/manual ordering.
- `ordered`: Ordered outside ResearchOS.
- `received`: Item has arrived.
- `cancelled`: Request should not proceed.

## Inventory Integration

Low-stock inventory items can create a draft request through:

```bash
curl -X POST http://127.0.0.1:8001/inventory/{item_id}/request-reorder
```

The request stores the linked inventory item ID. When a request is marked received, the caller can optionally update the linked inventory quantity:

```bash
curl -X POST http://127.0.0.1:8001/purchase-requests/{request_id}/mark-received \
  -H "Content-Type: application/json" \
  -d '{"update_inventory_quantity":true}'
```

## API Examples

Create a request:

```bash
curl -X POST http://127.0.0.1:8001/purchase-requests \
  -H "Content-Type: application/json" \
  -d '{
    "item_name":"BMP4",
    "vendor":"DemoBio",
    "catalog_number":"BMP4-001",
    "quantity_requested":2,
    "estimated_cost":180,
    "grant_or_funding_source":"Vision Grant",
    "requested_by":"Nathan",
    "status":"draft",
    "notes":"Needed for next retinal organoid differentiation run."
  }'
```

Move through review:

```bash
curl -X POST http://127.0.0.1:8001/purchase-requests/{request_id}/submit
curl -X POST http://127.0.0.1:8001/purchase-requests/{request_id}/approve
curl -X POST http://127.0.0.1:8001/purchase-requests/{request_id}/mark-ordered
curl -X POST http://127.0.0.1:8001/purchase-requests/{request_id}/mark-received \
  -H "Content-Type: application/json" \
  -d '{"update_inventory_quantity":false}'
```

Export for review:

```bash
curl http://127.0.0.1:8001/purchase-requests/export-csv
```

## Oracle Boundary

Purchase requests are not Oracle purchase orders. They are lab-facing intent records. Oracle PO numbers, invoice numbers, and final costs still live in purchase records imported from Oracle/manual exports.
