# Inventory Labels and Barcodes

ResearchOS inventory supports barcode, QR, and internal-label metadata for phone lookup, freezer organization, and reagent tracking.

No external barcode library is required in this milestone. ResearchOS stores barcode/QR values as plain text and returns printable label data.

## Inventory Fields

Optional inventory fields:

- `barcode`
- `qr_code`
- `internal_label`
- `freezer_box`
- `freezer_position`
- `shelf`
- `room`

These are useful for:

- freezer box maps
- reagent labels
- phone lookup
- future camera-based QR scanning
- matching physical tubes or boxes to ResearchOS inventory records

## Assign a Code

```bash
curl -X POST http://127.0.0.1:8001/inventory/inventory:ITEM_ID/assign-code \
  -H "Content-Type: application/json" \
  -d '{
    "barcode":"BC-SAG-001",
    "qr_code":"QR-SAG-001",
    "internal_label":"NK-SAG-A1",
    "freezer_box":"Box A",
    "freezer_position":"A1",
    "shelf":"Shelf 2",
    "room":"Lab 310"
  }'
```

## Lookup by Code

```bash
curl "http://127.0.0.1:8001/inventory/lookup?code=QR-SAG-001"
```

Lookup checks:

- barcode
- QR code
- internal label

Inventory search also includes barcode, QR, internal label, freezer box, freezer position, shelf, and room.

## Printable Label Data

```bash
curl http://127.0.0.1:8001/inventory/inventory:ITEM_ID/label
```

The label response includes:

- name
- vendor
- catalog number
- lot number
- expiration
- storage location
- freezer box and position
- QR/barcode value
- internal label
- printable text lines

## Future Phone Scanning Workflow

The Flutter mobile app includes a **Scan Inventory** placeholder and manual code lookup.

Future implementation should:

1. Use the phone camera to scan a QR code or barcode.
2. Call `/inventory/lookup?code=...`.
3. Open the matching inventory item.
4. Let the scientist record usage, location changes, or reorder requests.

## Label Printing

Current label output is JSON for local printing workflows. Future versions may add:

- PDF label sheets
- Zebra/Dymo label printer support
- QR image generation
- freezer box map printing
- batch label generation

ResearchOS intentionally does not generate physical labels yet; it returns structured label data that can be rendered by future web/mobile/print workflows.
