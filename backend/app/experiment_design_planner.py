"""Provider-agnostic experiment design planning helpers."""

from __future__ import annotations

import csv
import io
import itertools
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4


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

DESIGN_IMPORT_ALIASES = {
    "title": ["title", "experiment", "experiment title", "design", "study"],
    "experiment_type": ["experiment type", "type", "study type", "model type"],
    "cell_line_or_model": ["cell line", "model", "line", "organoid line", "cell model"],
    "reporters": ["reporter", "reporters", "genotype"],
    "condition_name": ["condition", "group", "treatment group"],
    "treatment": ["treatment", "compound", "drug", "perturbation"],
    "dose": ["dose", "concentration", "conc"],
    "units": ["units", "unit"],
    "day": ["day", "timepoint", "time point", "collection day", "imaging day"],
    "event_type": ["event", "action", "procedure", "assay"],
    "sample_id": ["sample", "sample id", "well", "tube"],
    "replicate": ["replicate", "rep", "n"],
    "notes": ["notes", "note", "description", "details"],
    "alert_enabled": ["alert", "alert enabled", "reminder", "reminder enabled"],
}

DEFAULT_DESIGN_IMPORT_TEMPLATES = [
    {
        "template_id": "default:experiment_design_standard",
        "name": "Experiment Design Standard",
        "provider": "experiment_designs",
        "mapping": {
            "title": "Experiment",
            "experiment_type": "Type",
            "cell_line_or_model": "Cell Line",
            "reporters": "Reporters",
            "condition_name": "Condition",
            "treatment": "Treatment",
            "dose": "Dose",
            "units": "Units",
            "day": "Day",
            "event_type": "Event",
            "sample_id": "Sample ID",
            "replicate": "Replicate",
            "notes": "Notes",
            "alert_enabled": "Reminder",
        },
        "is_default": True,
    }
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


def _ics_escape(value: Any) -> str:
    """Escape text for RFC 5545 calendar fields."""

    text = str(value or "")
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_fold(line: str) -> list[str]:
    """Fold long ICS lines using the continuation format calendars expect."""

    if len(line) <= 75:
        return [line]
    folded = [line[:75]]
    remaining = line[75:]
    while remaining:
        folded.append(f" {remaining[:74]}")
        remaining = remaining[74:]
    return folded


def _ics_date(value: date) -> str:
    """Format a date as an all-day ICS date."""

    return value.strftime("%Y%m%d")


def _ics_timestamp() -> str:
    """Return a UTC timestamp for DTSTAMP."""

    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _calendar_event_description(design: dict[str, Any], event: dict[str, Any], condition: dict[str, Any] | None) -> str:
    """Create a traceable description for a calendar reminder."""

    parts = [
        str(event.get("description") or "").strip(),
        f"Design ID: {design.get('design_id')}",
        f"Linked experiment: {design.get('linked_experiment_id') or 'not linked'}",
        f"Day: {day_label(event.get('day'))}",
        f"Event type: {event.get('event_type') or 'custom'}",
        f"Status: {event.get('reminder_status') or 'pending'}",
    ]
    if condition:
        parts.extend(
            [
                f"Condition: {condition.get('condition_name')}",
                f"Treatment: {' '.join(str(value or '') for value in [condition.get('treatment'), condition.get('dose'), condition.get('units')]).strip() or 'not specified'}",
            ]
        )
    return "\n".join(part for part in parts if part)


def design_to_ics(design: dict[str, Any]) -> str:
    """Export one design's dated reminder events as an ICS calendar."""

    if not design.get("start_date"):
        raise ValueError("Calendar export requires a design start_date so relative design days can become real calendar dates.")

    reminders = all_reminders([design], include_drafts=True)
    return reminders_to_ics(
        reminders,
        calendar_name=f"ResearchOS - {design.get('title') or 'Experiment Design'}",
        filename_hint=str(design.get("design_id") or "experiment_design"),
    )


def reminders_to_ics(
    reminders: list[dict[str, Any]],
    calendar_name: str = "ResearchOS Experiment Design Reminders",
    filename_hint: str = "experiment_design_reminders",
    require_all_dates: bool = True,
) -> str:
    """Export dated reminder payloads as an ICS calendar file."""

    missing = sorted(
        {
            str(reminder.get("design_id") or "unknown design")
            for reminder in reminders
            if not reminder.get("due_date")
        }
    )
    if missing and require_all_dates:
        raise ValueError(
            "Calendar export requires start_date on every exported design. "
            f"Missing calendar dates for: {', '.join(missing)}."
        )
    dated_reminders = [reminder for reminder in reminders if reminder.get("due_date")]
    if not dated_reminders:
        missing_text = f" Missing calendar dates for: {', '.join(missing)}." if missing else ""
        raise ValueError(f"Calendar export requires at least one reminder with a real calendar date.{missing_text}")

    timestamp = _ics_timestamp()
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ResearchOS//Experiment Design Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_ics_escape(calendar_name)}",
        f"X-RESEARCHOS-FILE:{_ics_escape(filename_hint)}",
    ]
    for reminder in dated_reminders:
        design = reminder.get("design") or {}
        event = reminder.get("event") or {}
        condition = reminder.get("condition") or {}
        due = date.fromisoformat(str(reminder["due_date"]))
        end = due + timedelta(days=1)
        condition_name = reminder.get("condition_name") or condition.get("condition_name")
        title_parts = [
            design.get("title") or reminder.get("design_title") or "Experiment design",
            condition_name,
            event.get("event_type") or reminder.get("event_type") or "event",
            day_label(event.get("day") or reminder.get("day")),
        ]
        summary = " - ".join(str(part) for part in title_parts if part)
        description = _calendar_event_description(design, event, condition)
        uid = f"{event.get('event_id') or uuid4()}@researchos.local"
        event_lines = [
            "BEGIN:VEVENT",
            f"UID:{_ics_escape(uid)}",
            f"DTSTAMP:{timestamp}",
            f"DTSTART;VALUE=DATE:{_ics_date(due)}",
            f"DTEND;VALUE=DATE:{_ics_date(end)}",
            f"SUMMARY:{_ics_escape(summary)}",
            f"DESCRIPTION:{_ics_escape(description)}",
            f"CATEGORIES:{_ics_escape(event.get('event_type') or reminder.get('event_type') or 'experiment_design')}",
            f"STATUS:{'CANCELLED' if reminder.get('reminder_status') == 'dismissed' else 'CONFIRMED'}",
            "END:VEVENT",
        ]
        lines.extend(line for event_line in event_lines for line in _ics_fold(event_line))
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def parse_design_csv(csv_text: str) -> list[dict[str, str]]:
    """Parse pasted CSV text for design import."""

    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    return [dict(row) for row in reader]


def _normalize_header(value: str) -> str:
    """Normalize a spreadsheet header for alias matching."""

    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()


def suggest_design_import_mapping(columns: list[str]) -> dict[str, str]:
    """Suggest ResearchOS field mappings from flexible spreadsheet column names."""

    normalized = {_normalize_header(column): column for column in columns}
    suggestions: dict[str, str] = {}
    for field, aliases in DESIGN_IMPORT_ALIASES.items():
        for alias in aliases:
            match = normalized.get(_normalize_header(alias))
            if match:
                suggestions[field] = match
                break
    return suggestions


def mapped_design_row(row: dict[str, str], mapping: dict[str, str]) -> dict[str, str]:
    """Apply a ResearchOS field-to-column mapping to one CSV row."""

    normalized_row = {_normalize_header(key): value for key, value in row.items()}
    mapped: dict[str, str] = {}
    for field, column in mapping.items():
        value = row.get(column)
        if value is None:
            value = normalized_row.get(_normalize_header(column))
        mapped[field] = str(value or "").strip()
    return mapped


def preview_design_import(csv_text: str) -> dict[str, Any]:
    """Preview spreadsheet-style design import."""

    rows = parse_design_csv(csv_text)
    columns = list(rows[0].keys()) if rows else []
    suggested_mapping = suggest_design_import_mapping(columns)
    mapped_rows = [mapped_design_row(row, suggested_mapping) for row in rows]
    warnings = [] if rows else ["No rows detected in CSV text."]
    required_fields = ["condition_name", "day"]
    missing_required = [field for field in required_fields if field not in suggested_mapping]
    if missing_required:
        warnings.append(f"Missing suggested mapping for: {', '.join(missing_required)}.")
    inferred_conditions = sorted({row.get("condition_name") or "Condition" for row in mapped_rows if any(row.values())})
    inferred_days = sorted({day_label(row.get("day")) for row in mapped_rows if row.get("day")}, key=parse_design_day)
    inferred_event_types = sorted({(row.get("event_type") or "custom").strip() for row in mapped_rows})
    return {
        "detected_columns": columns,
        "suggested_mappings": suggested_mapping,
        "rows_preview": rows[:5],
        "preview_rows": rows[:5],
        "row_count": len(rows),
        "warnings": warnings,
        "missing_required_fields": missing_required,
        "inferred_conditions": inferred_conditions,
        "inferred_event_days": inferred_days,
        "inferred_days": inferred_days,
        "inferred_event_types": inferred_event_types,
    }


def import_design_rows(csv_text: str, mapping: dict[str, str] | None = None) -> dict[str, Any]:
    """Normalize mapped design CSV rows into design, condition, and event payloads."""

    rows = parse_design_csv(csv_text)
    if not rows:
        return {"rows": [], "mapping": mapping or {}, "warnings": ["No rows detected in CSV text."]}
    active_mapping = mapping or suggest_design_import_mapping(list(rows[0].keys()))
    normalized_rows = [mapped_design_row(row, active_mapping) for row in rows]
    warnings: list[str] = []
    if "condition_name" not in active_mapping:
        warnings.append("Mapping does not include condition_name; rows will use a generic condition.")
    if "day" not in active_mapping:
        warnings.append("Mapping does not include day; events will default to D0.")
    return {"rows": normalized_rows, "mapping": active_mapping, "warnings": warnings}


def truthy_design_value(value: Any) -> bool:
    """Return whether a CSV value represents an enabled reminder/alert."""

    return str(value or "").strip().lower() in {"true", "1", "yes", "y", "enabled", "reminder", "alert"}


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
