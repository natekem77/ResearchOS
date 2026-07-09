"""Inventory and purchasing helpers for ResearchOS lab operations."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
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
    "barcode",
    "qr_code",
    "internal_label",
    "freezer_box",
    "freezer_position",
    "shelf",
    "room",
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

PURCHASE_REQUEST_CSV_FIELDS = [
    "request_id",
    "item_name",
    "vendor",
    "catalog_number",
    "quantity_requested",
    "estimated_cost",
    "grant_or_funding_source",
    "requested_by",
    "request_date",
    "status",
    "notes",
    "linked_inventory_item_id",
]

PURCHASE_REQUEST_STATUSES = {
    "draft",
    "submitted",
    "approved",
    "ordered",
    "received",
    "cancelled",
}

ORACLE_PURCHASING_PROVIDER = {
    "provider": "oracle_purchasing",
    "status": "csv_import_only",
    "live_api_enabled": False,
    "supported_imports": ["csv"],
    "future_imports": ["xlsx", "xls", "Oracle API"],
}

ORACLE_FIELD_ALIASES = {
    "item name": "item_name",
    "product": "item_name",
    "product name": "item_name",
    "po number": "oracle_po_number",
    "po": "oracle_po_number",
    "po_number": "oracle_po_number",
    "oracle po": "oracle_po_number",
    "purchase order": "oracle_po_number",
    "purchase order number": "oracle_po_number",
    "supplier": "vendor",
    "supplier name": "vendor",
    "manufacturer": "vendor",
    "vendor": "vendor",
    "vendor name": "vendor",
    "item": "item_name",
    "item description": "item_name",
    "description": "item_name",
    "catalog": "catalog_number",
    "catalog #": "catalog_number",
    "cat #": "catalog_number",
    "catalog number": "catalog_number",
    "part number": "catalog_number",
    "sku": "catalog_number",
    "date": "purchase_date",
    "purchase date": "purchase_date",
    "order date": "purchase_date",
    "po date": "purchase_date",
    "cost": "cost",
    "amount": "cost",
    "extended amount": "cost",
    "total": "cost",
    "total cost": "cost",
    "price": "cost",
    "qty": "quantity",
    "quantity": "quantity",
    "units": "quantity",
    "project": "grant_or_funding_source",
    "project/grant": "grant_or_funding_source",
    "chartstring": "grant_or_funding_source",
    "fund": "grant_or_funding_source",
    "grant": "grant_or_funding_source",
    "funding source": "grant_or_funding_source",
    "purchaser": "purchaser",
    "requester": "purchaser",
    "ordered by": "purchaser",
    "buyer": "purchaser",
    "invoice": "invoice_number",
    "invoice number": "invoice_number",
    "status": "status",
    "order status": "status",
}

PURCHASE_IMPORT_REQUIRED_FIELDS = ["item_name"]

DEFAULT_PURCHASE_IMPORT_TEMPLATES = [
    {
        "template_id": "default:oracle_purchasing_export",
        "name": "Oracle Purchasing Export",
        "provider": "oracle_purchasing",
        "mapping": {
            "item_name": "Item Description",
            "vendor": "Supplier",
            "catalog_number": "Catalog #",
            "purchase_date": "Order Date",
            "cost": "Total Cost",
            "quantity": "Qty",
            "grant_or_funding_source": "Project/Grant",
            "purchaser": "Requester",
            "oracle_po_number": "PO Number",
            "invoice_number": "Invoice Number",
            "status": "Status",
        },
        "is_default": True,
    }
]


def normalize_header(value: str) -> str:
    """Normalize spreadsheet headers for alias matching."""

    return " ".join(str(value or "").strip().lower().replace("-", " ").replace("_", " ").split())


def normalize_purchase_csv_row(row: dict[str, Any]) -> dict[str, Any]:
    """Map Oracle-style CSV headers into ResearchOS purchase fields."""

    normalized: dict[str, Any] = {}
    for key, value in row.items():
        clean_key = normalize_header(str(key or ""))
        field = ORACLE_FIELD_ALIASES.get(clean_key) or clean_key.replace(" ", "_")
        if field in PURCHASE_CSV_FIELDS:
            normalized[field] = clean_purchase_value(field, value)
    if "status" not in normalized:
        normalized["status"] = "imported"
    return normalized


def clean_purchase_value(field: str, value: Any) -> Any:
    """Normalize optional and numeric CSV values for purchase requests."""

    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if field in {"cost", "quantity"}:
        try:
            return float(str(value).replace("$", "").replace(",", "").strip())
        except ValueError:
            return None
    return value


def suggest_purchase_mapping(columns: list[str]) -> dict[str, str]:
    """Suggest ResearchOS purchase fields for a set of CSV columns."""

    normalized_columns = {normalize_header(column): column for column in columns}
    mapping: dict[str, str] = {}
    for normalized, original in normalized_columns.items():
        field = ORACLE_FIELD_ALIASES.get(normalized)
        if field and field not in mapping and field in PURCHASE_CSV_FIELDS:
            mapping[field] = original
    return mapping


def apply_purchase_mapping(row: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    """Apply a user-provided CSV column mapping to one purchase row."""

    normalized_row = {normalize_header(key): value for key, value in row.items()}
    mapped: dict[str, Any] = {}
    for field, source_column in mapping.items():
        if field not in PURCHASE_CSV_FIELDS or field == "purchase_id":
            continue
        mapped[field] = clean_purchase_value(field, normalized_row.get(normalize_header(source_column)))
    if "status" not in mapped or not mapped.get("status"):
        mapped["status"] = "imported"
    return mapped


def purchase_import_preview(csv_text: str) -> dict[str, Any]:
    """Inspect a CSV import before saving records."""

    rows = parse_csv_text(csv_text)
    columns = list(rows[0].keys()) if rows else []
    suggested = suggest_purchase_mapping(columns)
    missing = [field for field in PURCHASE_IMPORT_REQUIRED_FIELDS if field not in suggested]
    warnings: list[str] = []
    if not rows:
        warnings.append("No rows detected in CSV text.")
    if missing:
        warnings.append("Missing required mapping for: " + ", ".join(missing))
    return {
        "detected_columns": columns,
        "suggested_mapping": suggested,
        "rows_preview": rows[:5],
        "warnings": warnings,
        "missing_required_fields": missing,
        "row_count": len(rows),
    }


def inventory_item_status(item: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    """Derive stock and expiration status flags for one inventory item."""

    current = today or date.today()
    quantity = _float_or_none(item.get("quantity"))
    threshold = _float_or_none(item.get("reorder_threshold"))
    expiration = _parse_date(item.get("expiration_date"))
    expired = bool(expiration and expiration < current)
    days_until_expiration = (expiration - current).days if expiration else None
    expiring_soon = bool(days_until_expiration is not None and 0 <= days_until_expiration <= 90)
    expiring_window = None
    if days_until_expiration is not None and 0 <= days_until_expiration <= 30:
        expiring_window = "30_days"
    elif days_until_expiration is not None and 31 <= days_until_expiration <= 60:
        expiring_window = "60_days"
    elif days_until_expiration is not None and 61 <= days_until_expiration <= 90:
        expiring_window = "90_days"
    low_stock = bool(quantity is not None and threshold is not None and quantity <= threshold)
    in_stock = bool(quantity is None or quantity > 0)
    reorder_needed = low_stock
    return {
        **item,
        "in_stock": in_stock,
        "low_stock": low_stock,
        "expired": expired,
        "expiring_soon": expiring_soon,
        "reorder_needed": reorder_needed,
        "days_until_expiration": days_until_expiration,
        "expiring_window": expiring_window,
    }


def inventory_status_summary(items: list[dict[str, Any]], today: date | None = None) -> dict[str, Any]:
    """Summarize inventory operational status."""

    enriched = [inventory_item_status(item, today=today) for item in items]
    return {
        "total_items": len(enriched),
        "in_stock_count": sum(1 for item in enriched if item["in_stock"]),
        "low_stock_count": sum(1 for item in enriched if item["low_stock"]),
        "expired_count": sum(1 for item in enriched if item["expired"]),
        "expiring_soon_count": sum(1 for item in enriched if item["expiring_soon"]),
        "reorder_needed_count": sum(1 for item in enriched if item["reorder_needed"]),
        "expiring_windows": {
            "30_days": sum(1 for item in enriched if item["expiring_window"] == "30_days"),
            "60_days": sum(1 for item in enriched if item["expiring_window"] == "60_days"),
            "90_days": sum(1 for item in enriched if item["expiring_window"] == "90_days"),
        },
        "items": enriched,
        "low_stock": [item for item in enriched if item["low_stock"]],
        "reorder_needed": [item for item in enriched if item["reorder_needed"]],
        "expired": [item for item in enriched if item["expired"]],
        "expiring_soon": [item for item in enriched if item["expiring_soon"]],
    }


def purchase_summary(records: list[dict[str, Any]], recent_limit: int = 10) -> dict[str, Any]:
    """Summarize purchasing spend by grant, vendor, and month."""

    total_spend = sum(_purchase_total(record) for record in records)
    by_grant = _group_spend(records, "grant_or_funding_source", "Unassigned")
    by_vendor = _group_spend(records, "vendor", "Unknown vendor")
    by_month: dict[str, dict[str, Any]] = {}
    for record in records:
        month = _purchase_month(record.get("purchase_date")) or "No date"
        bucket = by_month.setdefault(month, {"month": month, "total_spend": 0.0, "purchase_count": 0})
        bucket["total_spend"] += _purchase_total(record)
        bucket["purchase_count"] += 1
    recent = sorted(records, key=lambda record: str(record.get("purchase_date") or record.get("created_at") or ""), reverse=True)[:recent_limit]
    return {
        "total_spend": round(total_spend, 2),
        "purchase_count": len(records),
        "spend_by_grant": by_grant,
        "spend_by_vendor": by_vendor,
        "spend_by_month": sorted(by_month.values(), key=lambda item: str(item["month"]), reverse=True),
        "recent_purchases": recent,
    }


def inventory_label_data(item: dict[str, Any]) -> dict[str, Any]:
    """Return printable label data for one inventory item."""

    code_value = item.get("qr_code") or item.get("barcode") or item.get("internal_label") or item.get("item_id")
    storage_parts = [
        item.get("room"),
        item.get("shelf"),
        item.get("freezer_box"),
        item.get("freezer_position"),
    ]
    storage_detail = " / ".join(str(part) for part in storage_parts if part)
    return {
        "item_id": item.get("item_id"),
        "name": item.get("name"),
        "vendor": item.get("vendor"),
        "catalog_number": item.get("catalog_number"),
        "lot_number": item.get("lot_number"),
        "expiration": item.get("expiration_date"),
        "storage_location": item.get("storage_location"),
        "storage_detail": storage_detail,
        "barcode": item.get("barcode"),
        "qr_code": item.get("qr_code"),
        "code_value": code_value,
        "internal_label": item.get("internal_label"),
        "freezer_box": item.get("freezer_box"),
        "freezer_position": item.get("freezer_position"),
        "shelf": item.get("shelf"),
        "room": item.get("room"),
        "print_lines": [
            str(item.get("name") or "Inventory item"),
            " | ".join(str(part) for part in [item.get("vendor"), item.get("catalog_number")] if part),
            " | ".join(str(part) for part in [f"Lot {item.get('lot_number')}" if item.get("lot_number") else None, f"Exp {item.get('expiration_date')}" if item.get("expiration_date") else None] if part),
            storage_detail or str(item.get("storage_location") or ""),
            str(code_value or ""),
        ],
    }


def records_to_csv(records: list[dict[str, Any]], fields: list[str]) -> str:
    """Serialize records to CSV with stable headers."""

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        writer.writerow({field: record.get(field) for field in fields})
    return output.getvalue()


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _purchase_total(record: dict[str, Any]) -> float:
    return _float_or_none(record.get("cost")) or 0.0


def _group_spend(records: list[dict[str, Any]], field: str, fallback: str) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        key = str(record.get(field) or fallback)
        bucket = grouped.setdefault(key, {"name": key, "total_spend": 0.0, "purchase_count": 0})
        bucket["total_spend"] += _purchase_total(record)
        bucket["purchase_count"] += 1
    return sorted(
        [
            {**bucket, "total_spend": round(float(bucket["total_spend"]), 2)}
            for bucket in grouped.values()
        ],
        key=lambda item: float(item["total_spend"]),
        reverse=True,
    )


def _purchase_month(value: Any) -> str | None:
    parsed = _parse_date(value)
    return parsed.strftime("%Y-%m") if parsed else None


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


def reagent_methods_entry(
    item: dict[str, Any],
    linked_resource: dict[str, Any] | None = None,
    *,
    include_lot: bool = True,
    include_storage: bool = False,
) -> dict[str, Any]:
    """Build one paper-ready reagent entry without inventing missing fields."""

    name = item.get("name") or (linked_resource or {}).get("name") or "Unnamed reagent"
    vendor = item.get("vendor") or (linked_resource or {}).get("vendor")
    catalog = item.get("catalog_number") or (linked_resource or {}).get("catalog_number")
    rrid = item.get("rrid") or (linked_resource or {}).get("rrid")
    lot = item.get("lot_number") or (linked_resource or {}).get("lot_number")
    concentration = (linked_resource or {}).get("concentration")
    units = (linked_resource or {}).get("units") or item.get("unit")
    storage = item.get("storage_location") or (linked_resource or {}).get("storage_location")

    details = []
    if vendor:
        details.append(str(vendor))
    if catalog:
        details.append(f"catalog {catalog}")
    if rrid:
        details.append(f"RRID {rrid}")
    if include_lot and lot:
        details.append(f"lot {lot}")
    if concentration:
        concentration_text = f"{concentration} {units}".strip() if units else str(concentration)
        details.append(f"used at {concentration_text}")
    if include_storage and storage:
        details.append(f"stored at {storage}")

    warnings = []
    if not vendor:
        warnings.append(f"{name}: vendor is missing.")
    if not catalog:
        warnings.append(f"{name}: catalog number is missing.")
    if not rrid and str(item.get("category") or (linked_resource or {}).get("resource_type") or "").lower() in {"antibody", "marker"}:
        warnings.append(f"{name}: RRID is missing.")

    text = str(name)
    if details:
        text = f"{name} ({', '.join(details)})"
    return {
        "item_id": item.get("item_id"),
        "linked_resource_id": item.get("linked_resource_id") or (linked_resource or {}).get("resource_id"),
        "name": name,
        "text": text,
        "warnings": warnings,
        "fields": {
            "vendor": vendor,
            "catalog_number": catalog,
            "rrid": rrid,
            "lot_number": lot if include_lot else None,
            "concentration": concentration,
            "units": units,
            "storage_location": storage if include_storage else None,
        },
    }


def build_reagent_methods_text(
    entries: list[dict[str, Any]],
    *,
    style: str = "paper",
) -> dict[str, Any]:
    """Format a complete reagent/materials section from entry records."""

    normalized_style = style if style in {"paper", "grant", "protocol"} else "paper"
    texts = [str(entry.get("text") or "").strip().rstrip(".") for entry in entries if entry.get("text")]
    warnings = [warning for entry in entries for warning in entry.get("warnings", [])]
    if not texts:
        return {
            "style": normalized_style,
            "text": "No reagent inventory items were provided.",
            "entries": entries,
            "warnings": ["No inventory items were available to format."],
        }
    if normalized_style == "protocol":
        body = "\n".join(f"- {text}." for text in texts)
        text = f"Materials and reagents:\n{body}"
    elif normalized_style == "grant":
        text = "Key reagents and materials include " + "; ".join(texts) + "."
    else:
        text = "Reagents and materials used in this study included " + "; ".join(texts) + "."
    return {
        "style": normalized_style,
        "text": text,
        "entries": entries,
        "warnings": warnings,
    }
