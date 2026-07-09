"""Provider-agnostic experiment design planning helpers."""

from __future__ import annotations

import csv
import io
import itertools
import re
from datetime import date, datetime, timedelta
from typing import Any


EVENT_TYPES = {
    "treatment",
    "media_change",
    "collection",
    "imaging",
    "fixation",
    "staining",
    "sequencing",
    "analysis",
    "custom",
}

DESIGN_STATUSES = {"draft", "active", "completed", "archived"}

DESIGN_EXPORT_FIELDS = [
    "design_id",
    "experiment_title",
    "experiment_type",
    "cell_line_or_model",
    "reporters",
    "condition",
    "replicate",
    "day",
    "event_type",
    "treatment",
    "dose",
    "units",
    "sample_id",
    "notes",
    "alert_enabled",
]


def parse_design_day(value: Any) -> int:
    """Return a numeric day from labels such as D0, Day32, or 9."""

    text = str(value or "0").strip()
    match = re.search(r"-?\d+", text)
    return int(match.group(0)) if match else 0


def day_label(value: Any) -> str:
    """Normalize day labels while preserving arbitrary input meaning."""

    text = str(value or "").strip()
    if not text:
        return "D0"
    if re.fullmatch(r"-?\d+", text):
        return f"D{text}"
    return text


def build_design_timeline(design: dict[str, Any]) -> dict[str, Any]:
    """Group design events into a day-by-day timeline."""

    conditions = {condition["condition_id"]: condition for condition in design.get("conditions", [])}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in design.get("events", []):
        entry = {
            **event,
            "condition": conditions.get(event.get("condition_id")),
            "day_number": parse_design_day(event.get("day")),
        }
        grouped.setdefault(day_label(event.get("day")), []).append(entry)
    days = [
        {"day": label, "day_number": parse_design_day(label), "events": events}
        for label, events in grouped.items()
    ]
    days.sort(key=lambda item: (item["day_number"], str(item["day"])))
    for item in days:
        item["event_types"] = sorted({str(event.get("event_type") or "custom") for event in item["events"]})
        item["required_count"] = sum(1 for event in item["events"] if event.get("required"))
    return {
        "design_id": design.get("design_id"),
        "title": design.get("title"),
        "days": days,
        "event_count": sum(len(item["events"]) for item in days),
    }


def design_calendar(design: dict[str, Any]) -> dict[str, Any]:
    """Return a compact calendar representation derived from the timeline."""

    timeline = build_design_timeline(design)
    return {
        "design_id": design.get("design_id"),
        "title": design.get("title"),
        "calendar": [
            {
                "label": day["day"],
                "events": [
                    {
                        "title": event.get("title"),
                        "event_type": event.get("event_type"),
                        "condition_name": (event.get("condition") or {}).get("condition_name"),
                        "required": event.get("required"),
                        "alert_enabled": event.get("alert_enabled"),
                    }
                    for event in day["events"]
                ],
            }
            for day in timeline["days"]
        ],
    }


def design_to_csv(design: dict[str, Any]) -> str:
    """Export a design into an Excel-friendly event/condition CSV."""

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=DESIGN_EXPORT_FIELDS)
    writer.writeheader()
    conditions = design.get("conditions", []) or [{}]
    events = design.get("events", []) or [{}]
    condition_by_id = {condition.get("condition_id"): condition for condition in conditions if condition.get("condition_id")}
    for condition in conditions:
        replicate_count = int(condition.get("replicate_count") or 1)
        condition_events = [
            event for event in events if not event.get("condition_id") or event.get("condition_id") == condition.get("condition_id")
        ] or [{}]
        for replicate in range(1, replicate_count + 1):
            for event in condition_events:
                active_condition = condition_by_id.get(event.get("condition_id")) or condition
                writer.writerow(
                    {
                        "design_id": design.get("design_id"),
                        "experiment_title": design.get("title"),
                        "experiment_type": design.get("experiment_type"),
                        "cell_line_or_model": design.get("cell_line_or_model"),
                        "reporters": "; ".join(design.get("reporters") or []),
                        "condition": active_condition.get("condition_name"),
                        "replicate": replicate,
                        "day": event.get("day") or active_condition.get("start_day"),
                        "event_type": event.get("event_type") or "custom",
                        "treatment": active_condition.get("treatment"),
                        "dose": active_condition.get("dose"),
                        "units": active_condition.get("units"),
                        "sample_id": f"{active_condition.get('condition_name', 'sample')}_R{replicate}",
                        "notes": " ".join(str(value or "") for value in [active_condition.get("notes"), event.get("description")]).strip(),
                        "alert_enabled": event.get("alert_enabled", False),
                    }
                )
    return output.getvalue()


def parse_design_csv(csv_text: str) -> list[dict[str, str]]:
    """Parse pasted CSV text for design import."""

    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    return [dict(row) for row in reader]


def preview_design_import(csv_text: str) -> dict[str, Any]:
    """Preview spreadsheet-style design import."""

    rows = parse_design_csv(csv_text)
    columns = list(rows[0].keys()) if rows else []
    warnings = [] if rows else ["No rows detected in CSV text."]
    inferred_conditions = sorted({row.get("condition") or row.get("condition_name") or row.get("Condition") for row in rows if any(row.values())})
    inferred_days = sorted({day_label(row.get("day") or row.get("Day")) for row in rows if row.get("day") or row.get("Day")}, key=parse_design_day)
    inferred_event_types = sorted({(row.get("event_type") or row.get("Event Type") or "custom").strip() for row in rows})
    return {
        "detected_columns": columns,
        "rows_preview": rows[:5],
        "row_count": len(rows),
        "warnings": warnings,
        "inferred_conditions": inferred_conditions,
        "inferred_days": inferred_days,
        "inferred_event_types": inferred_event_types,
    }


def event_due_date(design: dict[str, Any], event: dict[str, Any]) -> date:
    """Calculate a reminder date from design creation and event day."""

    created = str(design.get("start_date") or design.get("created_at") or date.today().isoformat())[:10]
    try:
        start = date.fromisoformat(created)
    except ValueError:
        start = date.today()
    offset = parse_design_day(event.get("day")) - int(event.get("reminder_offset_days") if event.get("reminder_offset_days") is not None else event.get("alert_offset_days") or 0)
    return start + timedelta(days=offset)


def reminder_payload(design: dict[str, Any], event: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    """Build an actionable reminder payload."""

    current = today or date.today()
    due_date = event_due_date(design, event) if design.get("start_date") else None
    status = str(event.get("reminder_status") or "pending")
    if event.get("completed"):
        status = "completed"
    elif event.get("dismissed_at"):
        status = "dismissed"
    elif due_date:
        if due_date < current:
            status = "overdue"
        elif due_date == current:
            status = "due"
        else:
            status = "pending"
    conditions = {condition.get("condition_id"): condition for condition in design.get("conditions", [])}
    condition = conditions.get(event.get("condition_id"))
    return {
        "design_id": design.get("design_id"),
        "design_title": design.get("title"),
        "design_status": design.get("status"),
        "event_id": event.get("event_id"),
        "condition": condition,
        "condition_name": (condition or {}).get("condition_name"),
        "day": event.get("day"),
        "event_type": event.get("event_type"),
        "title": event.get("title"),
        "description": event.get("description"),
        "calendar_date": due_date.isoformat() if due_date else None,
        "due_date": due_date.isoformat() if due_date else None,
        "relative_due": due_date is None,
        "reminder_enabled": bool(event.get("reminder_enabled") or event.get("alert_enabled")),
        "reminder_status": status,
        "completed_at": event.get("completed_at"),
        "dismissed_at": event.get("dismissed_at"),
        "design": design,
        "event": event,
    }


def due_events(
    designs: list[dict[str, Any]],
    days: int = 0,
    today: date | None = None,
    include_drafts: bool = False,
) -> list[dict[str, Any]]:
    """Return reminder-enabled events due today or within a future window."""

    current = today or date.today()
    end = current + timedelta(days=max(0, days))
    due: list[dict[str, Any]] = []
    for design in designs:
        if design.get("status") != "active" and not include_drafts:
            continue
        for event in design.get("events", []):
            if not (event.get("reminder_enabled") or event.get("alert_enabled")):
                continue
            reminder = reminder_payload(design, event, today=current)
            if reminder["reminder_status"] in {"completed", "dismissed"}:
                continue
            if reminder["due_date"] is None:
                if days > 0:
                    due.append(reminder)
                continue
            parsed_due = date.fromisoformat(str(reminder["due_date"]))
            if current <= parsed_due <= end:
                due.append(reminder)
            elif days == 0 and parsed_due < current:
                due.append(reminder)
    due.sort(key=lambda item: (item.get("due_date") or "9999-12-31", item.get("title") or ""))
    return due


def all_reminders(designs: list[dict[str, Any]], include_drafts: bool = False) -> list[dict[str, Any]]:
    """Return all reminder-enabled design events."""

    reminders = []
    for design in designs:
        if design.get("status") != "active" and not include_drafts:
            continue
        for event in design.get("events", []):
            if event.get("reminder_enabled") or event.get("alert_enabled"):
                reminders.append(reminder_payload(design, event))
    reminders.sort(key=lambda item: (item.get("due_date") or "9999-12-31", item.get("design_title") or "", item.get("title") or ""))
    return reminders


def full_factorial(factors: dict[str, list[str]]) -> dict[str, Any]:
    """Generate a full factorial condition table from arbitrary factors."""

    names = list(factors.keys())
    levels = [factors[name] for name in names]
    conditions = []
    for index, combo in enumerate(itertools.product(*levels), start=1):
        values = dict(zip(names, combo, strict=True))
        label = " + ".join(f"{name}={value}" for name, value in values.items())
        conditions.append({"condition_name": f"Condition {index}", "factors": values, "label": label})
    return {"factor_count": len(names), "condition_count": len(conditions), "conditions": conditions}


def check_design_balance(conditions: list[dict[str, Any]]) -> dict[str, Any]:
    """Flag missing controls and unbalanced replicate/sample counts."""

    replicate_counts = [int(condition.get("replicate_count") or 0) for condition in conditions]
    sample_counts = [int(condition.get("sample_count") or 0) for condition in conditions]
    names = " ".join(str(condition.get("condition_name") or "") for condition in conditions).lower()
    treatments = " ".join(str(condition.get("treatment") or "") for condition in conditions).lower()
    has_control = any(term in f"{names} {treatments}" for term in ["control", "vehicle", "dmso", "untreated", "baseline"])
    warnings = []
    if not has_control:
        warnings.append("No obvious control condition detected.")
    if len(set(replicate_counts)) > 1:
        warnings.append("Replicate counts are unbalanced.")
    if len(set(sample_counts)) > 1:
        warnings.append("Sample counts are unbalanced.")
    return {
        "condition_count": len(conditions),
        "has_control": has_control,
        "replicate_counts": replicate_counts,
        "sample_counts": sample_counts,
        "balanced_replicates": len(set(replicate_counts)) <= 1,
        "balanced_samples": len(set(sample_counts)) <= 1,
        "warnings": warnings,
    }


def copilot_design_checks(design: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic design-quality checks without scientific invention."""

    balance = check_design_balance(design.get("conditions", []))
    timeline = build_design_timeline(design)
    crowded_days = [
        {"day": day["day"], "event_count": len(day["events"])}
        for day in timeline["days"]
        if len(day["events"]) >= 5
    ]
    reminders = [
        event for event in design.get("events", [])
        if event.get("required") and not event.get("alert_enabled")
    ]
    return {
        "missing_controls": [] if balance["has_control"] else ["No obvious vehicle/untreated/control condition detected."],
        "unbalanced_replicates": [] if balance["balanced_replicates"] else ["Replicate counts vary across conditions."],
        "days_with_many_actions": crowded_days,
        "suggested_reminders": [
            {"event_id": event.get("event_id"), "title": event.get("title"), "day": event.get("day")}
            for event in reminders[:10]
        ],
        "limitations": ["Checks are deterministic and based only on structured design fields."],
    }
