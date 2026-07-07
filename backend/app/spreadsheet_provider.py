"""Generic quantitative spreadsheet provider for ResearchOS.

The provider is intentionally domain-agnostic. It detects spreadsheet structure,
column roles, entities, and quantitative summaries without hardcoded marker,
compound, or model-system lists. Optional lab ontology terms can be added in a
local JSON file later without changing this module.
"""

from __future__ import annotations

import csv
import json
import math
import re
import statistics
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from app.config import Settings, get_settings
from app.graphpad_provider import infer_experiment_id_from_filename
from app.storage import PROJECT_ROOT, SQLiteStore

SPREADSHEET_PROVIDER = "spreadsheet"
SUPPORTED_EXTENSIONS = (".xlsx", ".xls", ".csv", ".tsv")
GROUP_COLUMN_HINTS = {"group", "treatment", "condition", "dose", "timepoint", "time_point", "batch"}
IDENTIFIER_HINTS = {"id", "sample", "animal", "patient", "cluster", "well", "replicate", "experiment", "batch"}
DATE_HINTS = {"date", "time", "timestamp", "day"}
TEXT_ENTITY_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9+./_-]{2,}\b")


@dataclass(frozen=True)
class SpreadsheetScanResult:
    """Summary returned after scanning spreadsheet folders."""

    provider: str
    folders: list[str]
    supported_extensions: list[str]
    files_found: int
    assets_registered: int
    assets_skipped: int
    registered_assets: list[dict[str, Any]]
    skipped_assets: list[dict[str, Any]]


def spreadsheet_scan_folders(settings: Settings | None = None) -> list[Path]:
    """Return configured spreadsheet scan folders as absolute paths."""

    resolved_settings = settings or get_settings()
    raw_folders = re.split(r"[,;]", resolved_settings.spreadsheet_scan_folders)
    folders: list[Path] = []
    for raw_folder in raw_folders:
        if not raw_folder.strip():
            continue
        path = Path(raw_folder.strip())
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        folders.append(path.resolve())
    return folders


def spreadsheet_status(settings: Settings | None = None) -> dict[str, Any]:
    """Return provider readiness and registered spreadsheet count."""

    resolved_settings = settings or get_settings()
    store = SQLiteStore(settings=resolved_settings)
    assets = spreadsheet_assets(settings=resolved_settings)
    return {
        "provider": SPREADSHEET_PROVIDER,
        "status": "active",
        "folders": [{"path": str(folder), "exists": folder.exists()} for folder in spreadsheet_scan_folders(resolved_settings)],
        "supported_extensions": list(SUPPORTED_EXTENSIONS),
        "asset_count": len(assets),
        "message": "Generic spreadsheet provider parses local tabular data and stores summaries as asset metadata.",
    }


def scan_spreadsheet_assets(settings: Settings | None = None) -> SpreadsheetScanResult:
    """Discover supported spreadsheet files and register/update assets."""

    resolved_settings = settings or get_settings()
    store = SQLiteStore(settings=resolved_settings)
    folders = spreadsheet_scan_folders(resolved_settings)
    files = _discover_supported_files(folders)
    registered_assets: list[dict[str, Any]] = []
    skipped_assets: list[dict[str, Any]] = []

    for file_path in files:
        stored_path = str(file_path.resolve())
        inferred_experiment_id = infer_experiment_id_from_filename(file_path.name)
        metadata = parse_spreadsheet(file_path, folders, inferred_experiment_id)
        existing = store.get_asset_by_provider_path(SPREADSHEET_PROVIDER, stored_path)
        if existing is not None:
            if not existing.get("experiment_id") and inferred_experiment_id:
                existing = store.link_asset(str(existing["asset_id"]), inferred_experiment_id) or existing
            existing_metadata = existing.get("metadata") if isinstance(existing.get("metadata"), dict) else {}
            merged_metadata = dict(existing_metadata)
            merged_metadata.update(metadata)
            existing = store.update_asset_metadata(str(existing["asset_id"]), merged_metadata) or existing
            skipped_assets.append(existing)
            continue

        asset = store.register_asset(
            asset_type="spreadsheet",
            experiment_id=inferred_experiment_id,
            title=_title_for_file(file_path),
            filename=file_path.name,
            provider=SPREADSHEET_PROVIDER,
            path=stored_path,
            metadata=metadata,
        )
        registered_assets.append(asset)

    return SpreadsheetScanResult(
        provider=SPREADSHEET_PROVIDER,
        folders=[str(folder) for folder in folders],
        supported_extensions=list(SUPPORTED_EXTENSIONS),
        files_found=len(files),
        assets_registered=len(registered_assets),
        assets_skipped=len(skipped_assets),
        registered_assets=registered_assets,
        skipped_assets=skipped_assets,
    )


def spreadsheet_assets(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Return registered spreadsheet assets."""

    resolved_settings = settings or get_settings()
    store = SQLiteStore(settings=resolved_settings)
    return [
        asset
        for asset in store.list_assets(query=None)
        if asset.get("provider") == SPREADSHEET_PROVIDER
    ]


def spreadsheet_summary(asset_id: str, settings: Settings | None = None) -> dict[str, Any] | None:
    """Return parsed spreadsheet metadata and quantitative summary for one asset."""

    resolved_settings = settings or get_settings()
    store = SQLiteStore(settings=resolved_settings)
    asset = store.get_asset(asset_id)
    if asset is None or asset.get("provider") != SPREADSHEET_PROVIDER:
        return None
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    return {
        "asset_id": asset.get("asset_id"),
        "title": asset.get("title"),
        "filename": asset.get("filename"),
        "provider": asset.get("provider"),
        "experiment_id": asset.get("experiment_id"),
        "path": asset.get("path"),
        **metadata,
    }


def compact_spreadsheet_summary(asset_id: str, settings: Settings | None = None) -> dict[str, Any] | None:
    """Return a concise demo-friendly quantitative summary for one spreadsheet."""

    summary = spreadsheet_summary(asset_id=asset_id, settings=settings)
    if summary is None:
        return None

    entities = summary.get("entities") if isinstance(summary.get("entities"), dict) else {}
    tables = summary.get("detected_tables") if isinstance(summary.get("detected_tables"), list) else []
    key_numeric_measurements: list[dict[str, Any]] = []
    per_group_means: dict[str, Any] = {}
    n_per_group: dict[str, Any] = {}
    p_values: list[Any] = []

    for table in tables:
        if not isinstance(table, dict):
            continue
        for column, values in (table.get("numeric_summaries") or {}).items():
            if isinstance(values, dict):
                key_numeric_measurements.append(
                    {
                        "measurement": column,
                        "mean": values.get("mean"),
                        "median": values.get("median"),
                        "standard_deviation": values.get("standard_deviation"),
                        "sem": values.get("sem"),
                        "min": values.get("min"),
                        "max": values.get("max"),
                    }
                )
                if "p" in str(column).lower():
                    p_values.append(values.get("mean"))
        for group_column, groups in (table.get("grouped_summaries") or {}).items():
            if not isinstance(groups, dict):
                continue
            per_group_means.setdefault(group_column, {})
            n_per_group.setdefault(group_column, {})
            for group_name, measurements in groups.items():
                per_group_means[group_column].setdefault(group_name, {})
                n_per_group[group_column].setdefault(group_name, {})
                if not isinstance(measurements, dict):
                    continue
                for measurement, values in measurements.items():
                    if isinstance(values, dict) and values:
                        per_group_means[group_column][group_name][measurement] = values.get("mean")
                        n_per_group[group_column][group_name][measurement] = values.get("count")

    detected_treatments = sorted(
        set((entities.get("treatments") or []) + (entities.get("compounds") or []) + (entities.get("drugs") or []))
    )
    detected_markers = sorted(
        set((entities.get("markers") or []) + (entities.get("genes") or []) + (entities.get("proteins") or []))
    )
    group_names = sorted(
        {
            str(group_name)
            for group_sets in per_group_means.values()
            for group_name in group_sets.keys()
            if str(group_name)
        }
    )
    interpretation = _compact_interpretation(
        title=str(summary.get("title") or summary.get("filename") or "Spreadsheet"),
        measurements=key_numeric_measurements,
        group_names=group_names,
        detected_markers=detected_markers,
    )
    return {
        "asset_id": summary.get("asset_id"),
        "title": summary.get("title"),
        "experiment_id": summary.get("experiment_id"),
        "detected_markers_entities": detected_markers[:24],
        "detected_treatments_groups": (detected_treatments + group_names)[:24],
        "key_numeric_measurements": key_numeric_measurements[:12],
        "per_group_means": per_group_means,
        "n_per_group": n_per_group,
        "p_values": [value for value in p_values if value is not None],
        "short_interpretation": interpretation,
        "limitations": summary.get("limitations") or [],
        "source": "spreadsheet",
    }


def _compact_interpretation(
    title: str,
    measurements: list[dict[str, Any]],
    group_names: list[str],
    detected_markers: list[str],
) -> str:
    """Build short deterministic interpretation text."""

    pieces = [f"{title} contains quantitative table summaries"]
    if detected_markers:
        pieces.append(f"for {', '.join(detected_markers[:6])}")
    if group_names:
        pieces.append(f"across groups {', '.join(group_names[:6])}")
    if measurements:
        pieces.append(f"with {len(measurements)} numeric measurement(s)")
    return " ".join(pieces) + ". Review source rows before drawing conclusions."


def parse_spreadsheet(
    file_path: Path,
    folders: list[Path],
    inferred_experiment_id: str | None = None,
) -> dict[str, Any]:
    """Parse a spreadsheet into provider metadata and summaries."""

    stat = file_path.stat()
    extension = file_path.suffix.lower()
    tables = _read_tables(file_path)
    detected_tables = []
    all_entities: dict[str, list[str]] = {}
    total_rows = 0
    max_columns = 0

    for table in tables:
        analysis = _analyze_table(table["name"], table["rows"])
        detected_tables.append(analysis)
        total_rows += int(analysis["row_count"])
        max_columns = max(max_columns, int(analysis["column_count"]))
        for key, values in analysis["entities"].items():
            all_entities.setdefault(key, [])
            all_entities[key].extend(values)

    return {
        "experiment_id": inferred_experiment_id,
        "extension": extension,
        "source_folder": _source_folder_for_file(file_path, folders),
        "parser": "generic_spreadsheet",
        "sheet_names": [table["name"] for table in tables],
        "row_count": total_rows,
        "column_count": max_columns,
        "detected_tables": detected_tables,
        "entities": {key: sorted(set(values)) for key, values in all_entities.items()},
        "created_timestamp": _iso_timestamp(stat.st_ctime),
        "modified_timestamp": _iso_timestamp(stat.st_mtime),
        "limitations": _parser_limitations(extension, tables),
        "ontology_source": "dynamic_heuristics_plus_optional_lab_config",
    }


def _discover_supported_files(folders: list[Path]) -> list[Path]:
    """Recursively find supported spreadsheet files."""

    discovered: list[Path] = []
    for folder in folders:
        if not folder.exists() or not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                discovered.append(path.resolve())
    return sorted(discovered, key=lambda path: str(path).lower())


def _read_tables(file_path: Path) -> list[dict[str, Any]]:
    """Read tables from CSV, TSV, XLSX, or register XLS limitation."""

    extension = file_path.suffix.lower()
    if extension in {".csv", ".tsv"}:
        delimiter = "\t" if extension == ".tsv" else ","
        with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter=delimiter))
        return [{"name": file_path.stem, "rows": [_clean_row(row) for row in rows]}]
    if extension == ".xlsx":
        return _read_xlsx_tables(file_path)
    return [{"name": file_path.stem, "rows": []}]


def _read_xlsx_tables(file_path: Path) -> list[dict[str, Any]]:
    """Read basic cell text from XLSX files using the zipped OpenXML format."""

    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    tables: list[dict[str, Any]] = []
    with zipfile.ZipFile(file_path) as workbook_zip:
        shared_strings = _xlsx_shared_strings(workbook_zip, namespace)
        sheet_names = _xlsx_sheet_names(workbook_zip, namespace)
        sheet_paths = sorted(path for path in workbook_zip.namelist() if path.startswith("xl/worksheets/sheet") and path.endswith(".xml"))
        for index, sheet_path in enumerate(sheet_paths):
            sheet_name = sheet_names[index] if index < len(sheet_names) else Path(sheet_path).stem
            root = ElementTree.fromstring(workbook_zip.read(sheet_path))
            grid: dict[tuple[int, int], str] = {}
            for cell in root.findall(".//main:c", namespace):
                ref = str(cell.attrib.get("r") or "")
                row_index, column_index = _xlsx_cell_position(ref)
                value_node = cell.find("main:v", namespace)
                inline_node = cell.find("main:is/main:t", namespace)
                value = inline_node.text if inline_node is not None else value_node.text if value_node is not None else ""
                if cell.attrib.get("t") == "s" and value:
                    value = shared_strings[int(value)]
                grid[(row_index, column_index)] = str(value or "")
            tables.append({"name": sheet_name, "rows": _grid_to_rows(grid)})
    return tables


def _xlsx_shared_strings(workbook_zip: zipfile.ZipFile, namespace: dict[str, str]) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook_zip.namelist():
        return []
    root = ElementTree.fromstring(workbook_zip.read("xl/sharedStrings.xml"))
    return ["".join(text.itertext()) for text in root.findall(".//main:si", namespace)]


def _xlsx_sheet_names(workbook_zip: zipfile.ZipFile, namespace: dict[str, str]) -> list[str]:
    if "xl/workbook.xml" not in workbook_zip.namelist():
        return []
    root = ElementTree.fromstring(workbook_zip.read("xl/workbook.xml"))
    return [str(sheet.attrib.get("name") or "") for sheet in root.findall(".//main:sheet", namespace)]


def _xlsx_cell_position(reference: str) -> tuple[int, int]:
    match = re.match(r"([A-Z]+)(\d+)", reference)
    if not match:
        return (0, 0)
    column = 0
    for char in match.group(1):
        column = column * 26 + (ord(char) - ord("A") + 1)
    return (int(match.group(2)) - 1, column - 1)


def _grid_to_rows(grid: dict[tuple[int, int], str]) -> list[dict[str, str]]:
    if not grid:
        return []
    max_row = max(row for row, _ in grid)
    max_col = max(column for _, column in grid)
    header = [grid.get((0, column), f"column_{column + 1}") for column in range(max_col + 1)]
    rows = []
    for row_index in range(1, max_row + 1):
        rows.append({header[column]: grid.get((row_index, column), "") for column in range(max_col + 1)})
    return rows


def _analyze_table(name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    columns = list(rows[0].keys()) if rows else []
    column_profiles = [_profile_column(column, [row.get(column) for row in rows]) for column in columns]
    numeric_columns = [profile["name"] for profile in column_profiles if profile["type"] == "numeric"]
    group_columns = [
        profile["name"]
        for profile in column_profiles
        if profile["type"] == "categorical" and (_normalized(profile["name"]) in GROUP_COLUMN_HINTS or len(profile["unique_values"]) <= 12)
    ]
    return {
        "name": name,
        "row_count": len(rows),
        "column_count": len(columns),
        "columns": column_profiles,
        "numeric_summaries": {column: _numeric_summary([row.get(column) for row in rows]) for column in numeric_columns},
        "grouped_summaries": _grouped_summaries(rows, group_columns[:3], numeric_columns[:12]),
        "entities": _infer_entities(rows, columns),
    }


def _profile_column(column: str, values: list[Any]) -> dict[str, Any]:
    cleaned = [str(value or "").strip() for value in values]
    non_empty = [value for value in cleaned if value]
    numeric_values = [_to_float(value) for value in non_empty]
    numeric_count = sum(value is not None for value in numeric_values)
    unique_values = sorted(set(non_empty))[:50]
    column_key = _normalized(column)
    if non_empty and numeric_count / max(1, len(non_empty)) >= 0.8:
        column_type = "numeric"
    elif column_key in DATE_HINTS or any(_looks_like_date(value) for value in non_empty[:20]):
        column_type = "date_time"
    elif column_key in IDENTIFIER_HINTS or column_key.endswith("_id") or column_key.endswith("id"):
        column_type = "identifier"
    elif len(unique_values) <= max(20, math.sqrt(max(1, len(non_empty))) + 3):
        column_type = "categorical"
    else:
        column_type = "text"
    return {
        "name": column,
        "type": column_type,
        "missing_values": len(cleaned) - len(non_empty),
        "unique_count": len(set(non_empty)),
        "unique_values": unique_values[:20],
    }


def _numeric_summary(values: list[Any]) -> dict[str, Any]:
    numeric = sorted(value for value in (_to_float(value) for value in values) if value is not None)
    if not numeric:
        return {}
    stdev = statistics.stdev(numeric) if len(numeric) > 1 else 0.0
    return {
        "count": len(numeric),
        "mean": statistics.mean(numeric),
        "median": statistics.median(numeric),
        "standard_deviation": stdev,
        "sem": stdev / math.sqrt(len(numeric)) if numeric else 0.0,
        "min": min(numeric),
        "max": max(numeric),
        "quartiles": {
            "q1": _percentile(numeric, 0.25),
            "q3": _percentile(numeric, 0.75),
        },
        "missing_values": len(values) - len(numeric),
    }


def _grouped_summaries(rows: list[dict[str, Any]], group_columns: list[str], numeric_columns: list[str]) -> dict[str, Any]:
    grouped: dict[str, Any] = {}
    for group_column in group_columns:
        grouped[group_column] = {}
        group_values = sorted(set(str(row.get(group_column) or "").strip() for row in rows if str(row.get(group_column) or "").strip()))
        for group_value in group_values[:30]:
            group_rows = [row for row in rows if str(row.get(group_column) or "").strip() == group_value]
            grouped[group_column][group_value] = {
                column: _numeric_summary([row.get(column) for row in group_rows])
                for column in numeric_columns
            }
    return grouped


def _infer_entities(rows: list[dict[str, Any]], columns: list[str]) -> dict[str, list[str]]:
    """Infer scientific entities dynamically from column names and values."""

    entities: dict[str, set[str]] = {
        "genes": set(),
        "proteins": set(),
        "antibodies": set(),
        "markers": set(),
        "compounds": set(),
        "drugs": set(),
        "treatments": set(),
        "cell_lines": set(),
        "organoid_batches": set(),
        "sample_ids": set(),
        "animal_ids": set(),
        "patient_ids": set(),
        "sequencing_clusters": set(),
        "unknown_scientific_terms": set(),
    }
    ontology = _load_lab_ontology()
    for category, terms in ontology.items():
        entities.setdefault(category, set()).update(str(term) for term in terms)

    for column in columns:
        key = _normalized(column)
        values = [str(row.get(column) or "").strip() for row in rows if str(row.get(column) or "").strip()]
        if any(token in key for token in ["gene", "symbol"]):
            entities["genes"].update(values)
        elif "protein" in key:
            entities["proteins"].update(values)
        elif "antibody" in key or key in {"ab", "primary"}:
            entities["antibodies"].update(values)
        elif "marker" in key:
            entities["markers"].update(values)
        elif "compound" in key or "drug" in key:
            entities["compounds"].update(values)
        elif "treatment" in key or "condition" in key:
            entities["treatments"].update(values)
        elif "cell" in key and "line" in key:
            entities["cell_lines"].update(values)
        elif "batch" in key or "organoid" in key:
            entities["organoid_batches"].update(values)
        elif "sample" in key and "id" in key:
            entities["sample_ids"].update(values)
        elif "animal" in key and "id" in key:
            entities["animal_ids"].update(values)
        elif "patient" in key and "id" in key:
            entities["patient_ids"].update(values)
        elif "cluster" in key:
            entities["sequencing_clusters"].update(values)

        for value in values[:500]:
            for term in TEXT_ENTITY_PATTERN.findall(value):
                if _looks_scientific(term):
                    entities["unknown_scientific_terms"].add(term)

    return {key: sorted(value for value in values if value)[:100] for key, values in entities.items()}


def _load_lab_ontology() -> dict[str, list[str]]:
    """Load optional lab ontology terms from data/ontology_config.json."""

    path = PROJECT_ROOT / "data" / "ontology_config.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(key): list(value) for key, value in payload.items() if isinstance(value, list)}


def _clean_row(row: dict[str, Any]) -> dict[str, str]:
    return {str(key or "").strip(): str(value or "").strip() for key, value in row.items() if str(key or "").strip()}


def _to_float(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    index = (len(values) - 1) * fraction
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return values[int(index)]
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def _looks_like_date(value: str) -> bool:
    return bool(re.search(r"\b\d{4}-\d{1,2}-\d{1,2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b", value))


def _looks_scientific(term: str) -> bool:
    return bool(re.search(r"[A-Z].*[0-9]|[0-9].*[A-Z]|[A-Z]{2,}", term)) and len(term) <= 40


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _iso_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _parser_limitations(extension: str, tables: list[dict[str, Any]]) -> list[str]:
    limitations = ["Entity detection is heuristic and preserves unknown scientific terms for review."]
    if extension == ".xls":
        limitations.append("Legacy .xls files are registered but not deeply parsed without an optional binary Excel parser.")
    if not any(table["rows"] for table in tables):
        limitations.append("No rows were parsed from this file.")
    return limitations


def _title_for_file(path: Path) -> str:
    return re.sub(r"[_-]+", " ", path.stem).strip() or path.name


def _source_folder_for_file(path: Path, folders: list[Path]) -> str:
    resolved = path.resolve()
    for folder in folders:
        try:
            resolved.relative_to(folder)
            return str(folder)
        except ValueError:
            continue
    return ""
