"""Plate and sample layout planning helpers."""

from __future__ import annotations

import csv
import io
import random
from typing import Any


PLATE_FORMATS: dict[str, tuple[int, int]] = {
    "6-well": (2, 3),
    "12-well": (3, 4),
    "24-well": (4, 6),
    "48-well": (6, 8),
    "96-well": (8, 12),
    "384-well": (16, 24),
    "tube_rack": (8, 12),
}

LAYOUT_CSV_FIELDS = [
    "well_id",
    "row",
    "column",
    "position",
    "condition",
    "replicate",
    "sample_id",
    "treatment",
    "dose",
    "units",
    "day",
    "notes",
]


def layout_dimensions(format_name: str, rows: int | None = None, columns: int | None = None) -> tuple[int, int]:
    """Return layout dimensions for a standard or custom plate/rack."""

    if format_name == "custom":
        return max(1, int(rows or 1)), max(1, int(columns or 1))
    return PLATE_FORMATS.get(format_name, PLATE_FORMATS["96-well"])


def row_label(index: int) -> str:
    """Return spreadsheet-style row labels: A, B, ..., Z, AA."""

    label = ""
    value = index + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        label = chr(65 + remainder) + label
    return label


def empty_wells(rows: int, columns: int) -> list[dict[str, Any]]:
    """Create empty well slots for a plate/rack."""

    wells = []
    for row_index in range(rows):
        label = row_label(row_index)
        for column in range(1, columns + 1):
            position = f"{label}{column}"
            wells.append(
                {
                    "well_id": position,
                    "row": label,
                    "column": column,
                    "position": position,
                    "condition": None,
                    "replicate": None,
                    "sample_id": None,
                    "treatment": None,
                    "dose": None,
                    "units": None,
                    "day": None,
                    "notes": None,
                }
            )
    return wells


def _condition_assignments(design: dict[str, Any], balanced: bool = False) -> list[dict[str, Any]]:
    """Create condition/replicate assignments from design conditions."""

    conditions = list(design.get("conditions") or [])
    if balanced:
        max_replicates = max((int(condition.get("replicate_count") or 1) for condition in conditions), default=1)
        assignments: list[dict[str, Any]] = []
        for replicate in range(1, max_replicates + 1):
            for condition in conditions:
                replicate_count = int(condition.get("replicate_count") or 1)
                if replicate <= replicate_count:
                    assignments.append(_assignment_from_condition(condition, replicate))
        return assignments
    assignments = []
    for condition in conditions:
        replicate_count = int(condition.get("replicate_count") or 1)
        for replicate in range(1, replicate_count + 1):
            assignments.append(_assignment_from_condition(condition, replicate))
    return assignments


def _assignment_from_condition(condition: dict[str, Any], replicate: int) -> dict[str, Any]:
    """Convert one condition replicate into a well assignment payload."""

    condition_name = str(condition.get("condition_name") or "Condition")
    sample_id = f"{condition_name.replace(' ', '_')}_R{replicate}"
    return {
        "condition": condition_name,
        "replicate": replicate,
        "sample_id": sample_id,
        "treatment": condition.get("treatment"),
        "dose": condition.get("dose"),
        "units": condition.get("units"),
        "day": condition.get("start_day"),
        "notes": condition.get("notes"),
    }


def generate_plate_layout(
    design: dict[str, Any],
    format_name: str = "96-well",
    rows: int | None = None,
    columns: int | None = None,
    randomized: bool = False,
    grouped_by_condition: bool = True,
    balanced: bool = False,
    title: str | None = None,
) -> dict[str, Any]:
    """Generate a practical plate/rack layout from an experiment design."""

    resolved_rows, resolved_columns = layout_dimensions(format_name, rows, columns)
    wells = empty_wells(resolved_rows, resolved_columns)
    assignments = _condition_assignments(design, balanced=balanced)
    if randomized:
        rng = random.Random(str(design.get("design_id") or design.get("title") or "researchos"))
        rng.shuffle(assignments)
    elif not grouped_by_condition and not balanced:
        assignments = _condition_assignments(design, balanced=True)
    warnings = layout_warnings(design, assignments, len(wells))
    for index, assignment in enumerate(assignments[: len(wells)]):
        wells[index].update(assignment)
    return {
        "design_id": design.get("design_id"),
        "title": title or f"{design.get('title') or 'Experiment design'} layout",
        "format": format_name,
        "rows": resolved_rows,
        "columns": resolved_columns,
        "wells": wells,
        "warnings": warnings,
    }


def layout_warnings(design: dict[str, Any], assignments: list[dict[str, Any]], capacity: int) -> list[str]:
    """Return deterministic Research Copilot-style layout warnings."""

    warnings: list[str] = []
    conditions = list(design.get("conditions") or [])
    condition_text = " ".join(str(condition.get("condition_name") or condition.get("treatment") or "") for condition in conditions).lower()
    if not any(term in condition_text for term in ["control", "vehicle", "dmso", "untreated", "baseline"]):
        warnings.append("No obvious control condition detected.")
    if len(assignments) > capacity:
        warnings.append(f"Not enough wells: {len(assignments)} assignments for {capacity} positions. Extra assignments were omitted.")
    replicate_counts = [int(condition.get("replicate_count") or 1) for condition in conditions]
    if len(set(replicate_counts)) > 1:
        warnings.append("Replicate counts are unbalanced across conditions.")
    return warnings


def plate_layout_to_csv(layout: dict[str, Any]) -> str:
    """Export a plate/rack layout to CSV."""

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=LAYOUT_CSV_FIELDS)
    writer.writeheader()
    for well in layout.get("wells", []):
        writer.writerow({field: well.get(field) for field in LAYOUT_CSV_FIELDS})
    return output.getvalue()
