"""Inventory and purchasing helpers for ResearchOS lab operations."""

from __future__ import annotations

import csv
import io
from typing import Any


INVENTORY_CSV_FIELDS = [
    "item_id",
    "name",
    "category",
    "vendor",
    "catalog_number",
    "lot_number",
    "rrid",
    "price",
    "unit",
    "storage_location",
    "quantity",
    "reorder_threshold",
    "expiration_date",
    "notes",
    "linked_resource_id",
]

PURCHASE_CSV_FIELDS = [
    "purchase_id",
    "item_name",
    "vendor",
    "catalog_number",
    "purchase_date",
    "cost",
    "quantity",
    "grant_or_funding_source",
    "purchaser",
    "oracle_po_number",
    "invoice_number",
    "status",
    "notes",
]

ORACLE_PURCHASING_PROVIDER = {
    "provider": "oracle_purchasing",
    "status": "csv_import_only",
    "live_api_enabled": False,
    "supported_imports": ["csv"],
    "future_imports": ["xlsx", "xls", "Oracle API"],
}

ORACLE_FIELD_ALIASES = {
    "po number": "oracle_po_number",
    "po_number": "oracle_po_number",
    "purchase order": "oracle_po_number",
    "purchase order number": "oracle_po_number",
    "supplier": "vendor",
    "vendor name": "vendor",
    "item": "item_name",
    "item description": "item_name",
    "description": "item_name",
    "amount": "cost",
    "total cost": "cost",
    "price": "cost",
    "fund": "grant_or_funding_source",
    "grant": "grant_or_funding_source",
    "funding source": "grant_or_funding_source",
    "ordered by": "purchaser",
    "buyer": "purchaser",
    "invoice": "invoice_number",
    "invoice number": "invoice_number",
}


def normalize_purchase_csv_row(row: dict[str, Any]) -> dict[str, Any]:
    """Map Oracle-style CSV headers into ResearchOS purchase fields."""

    normalized: dict[str, Any] = {}
    for key, value in row.items():
        clean_key = str(key or "").strip().lower().replace("-", " ").replace("_", " ")
        field = ORACLE_FIELD_ALIASES.get(clean_key) or clean_key.replace(" ", "_")
        if field in PURCHASE_CSV_FIELDS:
            normalized[field] = value
    if "status" not in normalized:
        normalized["status"] = "imported"
    return normalized


def records_to_csv(records: list[dict[str, Any]], fields: list[str]) -> str:
    """Serialize records to CSV with stable headers."""

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        writer.writerow({field: record.get(field) for field in fields})
    return output.getvalue()


def parse_csv_text(csv_text: str) -> list[dict[str, str]]:
    """Parse CSV text into dictionaries."""

    input_file = io.StringIO(csv_text)
    reader = csv.DictReader(input_file)
    return [dict(row) for row in reader]


def methods_citation(item: dict[str, Any], linked_resource: dict[str, Any] | None = None) -> str:
    """Format a reusable reagent citation for paper methods sections."""

    name = item.get("name") or (linked_resource or {}).get("name") or "Reagent"
    vendor = item.get("vendor") or (linked_resource or {}).get("vendor")
    catalog = item.get("catalog_number") or (linked_resource or {}).get("catalog_number")
    rrid = item.get("rrid") or (linked_resource or {}).get("rrid")
    lot = item.get("lot_number") or (linked_resource or {}).get("lot_number")
    parts = [str(name)]
    details = []
    if vendor:
        details.append(str(vendor))
    if catalog:
        details.append(f"catalog {catalog}")
    if rrid:
        details.append(f"RRID {rrid}")
    if lot:
        details.append(f"lot {lot}")
    if details:
        parts.append(f"({', '.join(details)})")
    return " ".join(parts)
