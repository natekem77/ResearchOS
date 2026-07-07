"""GraphPad provider skeleton for local asset discovery.

This module deliberately avoids parsing proprietary Prism content. It only
discovers GraphPad-adjacent files and registers them as ResearchOS assets so
they can be linked to experiments.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.storage import PROJECT_ROOT, SQLiteStore

GRAPHPAD_PROVIDER = "graphpad"
SUPPORTED_EXTENSIONS = (
    ".prism",
    ".pzfx",
    ".pzfx.zip",
    ".csv",
    ".xlsx",
    ".xls",
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".pdf",
)


@dataclass(frozen=True)
class GraphPadScanResult:
    """Summary returned after scanning GraphPad folders."""

    provider: str
    folders: list[str]
    supported_extensions: list[str]
    files_found: int
    assets_registered: int
    assets_skipped: int
    registered_assets: list[dict[str, Any]]
    skipped_assets: list[dict[str, Any]]


def graphpad_scan_folders(settings: Settings | None = None) -> list[Path]:
    """Return configured GraphPad scan folders as absolute paths."""

    resolved_settings = settings or get_settings()
    raw_folders = re.split(r"[,;]", resolved_settings.graphpad_scan_folders)
    folders: list[Path] = []
    for raw_folder in raw_folders:
        if not raw_folder.strip():
            continue
        path = Path(raw_folder.strip())
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        folders.append(path.resolve())
    return folders


def graphpad_status(settings: Settings | None = None) -> dict[str, Any]:
    """Return local GraphPad provider readiness and asset counts."""

    resolved_settings = settings or get_settings()
    folders = graphpad_scan_folders(resolved_settings)
    store = SQLiteStore(settings=resolved_settings)
    assets = store.list_assets(query=None)
    graphpad_assets = [asset for asset in assets if asset.get("provider") == GRAPHPAD_PROVIDER]
    return {
        "provider": GRAPHPAD_PROVIDER,
        "status": "active",
        "folders": [
            {
                "path": str(folder),
                "exists": folder.exists(),
            }
            for folder in folders
        ],
        "supported_extensions": list(SUPPORTED_EXTENSIONS),
        "asset_count": len(graphpad_assets),
        "message": "GraphPad provider scans local files and registers assets only; Prism parsing is not implemented yet.",
    }


def scan_graphpad_assets(settings: Settings | None = None) -> GraphPadScanResult:
    """Discover supported GraphPad-related files and register new assets."""

    resolved_settings = settings or get_settings()
    store = SQLiteStore(settings=resolved_settings)
    folders = graphpad_scan_folders(resolved_settings)
    files = _discover_supported_files(folders)
    registered_assets: list[dict[str, Any]] = []
    skipped_assets: list[dict[str, Any]] = []

    for file_path in files:
        stored_path = str(file_path.resolve())
        inferred_experiment_id = infer_experiment_id_from_filename(file_path.name)
        metadata = _metadata_for_file(file_path, folders, inferred_experiment_id)
        existing = store.get_asset_by_provider_path(GRAPHPAD_PROVIDER, stored_path)
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
            asset_type=_asset_type_for_file(file_path),
            experiment_id=inferred_experiment_id,
            title=_title_for_file(file_path),
            filename=file_path.name,
            provider=GRAPHPAD_PROVIDER,
            path=stored_path,
            metadata=metadata,
        )
        registered_assets.append(asset)

    return GraphPadScanResult(
        provider=GRAPHPAD_PROVIDER,
        folders=[str(folder) for folder in folders],
        supported_extensions=list(SUPPORTED_EXTENSIONS),
        files_found=len(files),
        assets_registered=len(registered_assets),
        assets_skipped=len(skipped_assets),
        registered_assets=registered_assets,
        skipped_assets=skipped_assets,
    )


def infer_experiment_id_from_filename(filename: str) -> str | None:
    """Infer a human experiment ID from common lab filename patterns."""

    stem = _stem_without_supported_extension(filename)
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_")

    nk_match = re.search(r"(?:^|_)NK_?Expt_?(\d+)(?:_|$)", normalized, flags=re.IGNORECASE)
    if nk_match:
        return f"NK_Expt_{nk_match.group(1)}"

    exp_match = re.search(r"(?:^|_)EXP_?(\d+)(?:_|$)", normalized, flags=re.IGNORECASE)
    if exp_match:
        return f"EXP_{exp_match.group(1)}"

    return None


def graphpad_statistics_assets(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Return GraphPad assets with parsed CSV statistics metadata."""

    resolved_settings = settings or get_settings()
    store = SQLiteStore(settings=resolved_settings)
    return [
        asset
        for asset in store.list_assets(query=None)
        if asset.get("provider") == GRAPHPAD_PROVIDER
        and isinstance(asset.get("metadata"), dict)
        and isinstance(asset["metadata"].get("statistics"), dict)
    ]


def graphpad_asset_statistics_summary(
    asset_id: str,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Return parsed statistics metadata for one GraphPad asset."""

    resolved_settings = settings or get_settings()
    store = SQLiteStore(settings=resolved_settings)
    asset = store.get_asset(asset_id)
    if asset is None or asset.get("provider") != GRAPHPAD_PROVIDER:
        return None
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    statistics = metadata.get("statistics") if isinstance(metadata.get("statistics"), dict) else None
    if statistics is None:
        return {
            "asset_id": asset["asset_id"],
            "title": asset["title"],
            "filename": asset["filename"],
            "provider": asset["provider"],
            "experiment_id": asset.get("experiment_id"),
            "parsed": False,
            "message": "No parsed GraphPad CSV statistics metadata is available for this asset.",
        }
    return {
        "asset_id": asset["asset_id"],
        "title": asset["title"],
        "filename": asset["filename"],
        "provider": asset["provider"],
        "experiment_id": asset.get("experiment_id"),
        "parsed": True,
        **statistics,
    }


def compact_graphpad_statistics_summary(
    asset_id: str,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Return a concise demo-friendly summary for parsed GraphPad statistics."""

    summary = graphpad_asset_statistics_summary(asset_id=asset_id, settings=settings)
    if summary is None:
        return None
    if not summary.get("parsed"):
        return {
            "asset_id": summary.get("asset_id"),
            "title": summary.get("title"),
            "experiment_id": summary.get("experiment_id"),
            "detected_markers_entities": [],
            "detected_treatments_groups": [],
            "key_numeric_measurements": [],
            "per_group_means": {},
            "n_per_group": {},
            "p_values": [],
            "short_interpretation": summary.get("message") or "No parsed statistics are available.",
            "limitations": summary.get("limitations") or ["No parsed GraphPad statistics metadata is available."],
            "source": "graphpad_statistics",
        }

    variables = [str(value) for value in summary.get("variables", []) if value]
    groups = [str(value) for value in summary.get("group_names", []) if value]
    rows = summary.get("rows") if isinstance(summary.get("rows"), list) else []
    per_group_means: dict[str, dict[str, Any]] = {}
    n_per_group: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        group = str(row.get("group") or "ungrouped")
        variable = str(row.get("variable") or "measurement")
        per_group_means.setdefault(group, {})[variable] = row.get("mean")
        n_per_group.setdefault(group, {})[variable] = row.get("n")

    measurements = []
    for variable in variables:
        related_rows = [row for row in rows if isinstance(row, dict) and row.get("variable") == variable]
        means = [row.get("mean") for row in related_rows if row.get("mean") is not None]
        measurements.append(
            {
                "measurement": variable,
                "mean": sum(means) / len(means) if means else None,
                "groups": [str(row.get("group")) for row in related_rows if row.get("group")],
            }
        )

    p_values = [value for value in summary.get("p_values", []) if value is not None]
    tests = [str(value) for value in summary.get("statistical_tests", []) if value]
    interpretation = (
        f"{summary.get('title') or summary.get('filename')} reports {len(variables)} variable(s)"
        f" across {len(groups)} group(s)."
    )
    if p_values:
        interpretation += f" Parsed p-values include {', '.join(str(value) for value in p_values[:4])}."
    if tests:
        interpretation += f" Statistical test: {', '.join(tests[:3])}."
    return {
        "asset_id": summary.get("asset_id"),
        "title": summary.get("title"),
        "experiment_id": summary.get("experiment_id"),
        "detected_markers_entities": variables,
        "detected_treatments_groups": groups,
        "key_numeric_measurements": measurements[:12],
        "per_group_means": per_group_means,
        "n_per_group": n_per_group,
        "p_values": p_values,
        "short_interpretation": interpretation,
        "limitations": summary.get("limitations") or ["GraphPad summary depends on exported CSV structure."],
        "source": "graphpad_statistics",
    }


def _discover_supported_files(folders: list[Path]) -> list[Path]:
    """Recursively find supported files in existing scan folders."""

    discovered: list[Path] = []
    for folder in folders:
        if not folder.exists() or not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if path.is_file() and _normalized_extension(path) in SUPPORTED_EXTENSIONS:
                discovered.append(path.resolve())
    return sorted(discovered, key=lambda path: str(path).lower())


def _metadata_for_file(
    file_path: Path,
    folders: list[Path],
    inferred_experiment_id: str | None,
) -> dict[str, Any]:
    """Build provider metadata and parse CSV statistics when possible."""

    extension = _normalized_extension(file_path)
    metadata: dict[str, Any] = {
        "extension": extension,
        "source_folder": _source_folder_for_file(file_path, folders),
        "parser": "not_implemented",
    }
    if extension == ".csv":
        statistics = parse_graphpad_csv_statistics(file_path, inferred_experiment_id)
        metadata["parser"] = "graphpad_csv_statistics"
        metadata["statistics"] = statistics
    return metadata


def parse_graphpad_csv_statistics(
    file_path: Path,
    inferred_experiment_id: str | None = None,
) -> dict[str, Any]:
    """Extract basic statistics metadata from a GraphPad-associated CSV file."""

    with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.DictReader(handle, dialect=dialect))

    normalized_rows = [_normalize_csv_row(row) for row in rows]
    group_names = unique_preserve_order(
        str(row[key])
        for row in normalized_rows
        for key in ("group", "condition", "treatment")
        if row.get(key)
    )
    variables = unique_preserve_order(
        str(row[key])
        for row in normalized_rows
        for key in ("marker", "variable", "analyte", "measure")
        if row.get(key)
    )
    statistical_tests = unique_preserve_order(
        str(row[key])
        for row in normalized_rows
        for key in ("test", "statistical_test", "analysis")
        if row.get(key)
    )
    comparison_labels = unique_preserve_order(
        _comparison_label(row)
        for row in normalized_rows
        if _comparison_label(row)
    )

    parsed_rows = [_statistics_row(row) for row in normalized_rows]
    p_values = [
        row["p_value"]
        for row in parsed_rows
        if row.get("p_value") is not None
    ]

    return {
        "experiment_id": inferred_experiment_id,
        "group_names": group_names,
        "variables": variables,
        "sample_sizes": [
            row["n"]
            for row in parsed_rows
            if row.get("n") is not None
        ],
        "means": [
            row["mean"]
            for row in parsed_rows
            if row.get("mean") is not None
        ],
        "standard_deviations": [
            row["sd"]
            for row in parsed_rows
            if row.get("sd") is not None
        ],
        "standard_errors": [
            row["sem"]
            for row in parsed_rows
            if row.get("sem") is not None
        ],
        "p_values": p_values,
        "statistical_tests": statistical_tests,
        "comparison_labels": comparison_labels,
        "rows": parsed_rows,
        "row_count": len(parsed_rows),
        "limitations": [
            "CSV parsing is best-effort and depends on exported column headers.",
            "Proprietary Prism .prism/.pzfx files are not parsed in this milestone.",
        ],
    }


def _normalize_csv_row(row: dict[str, Any]) -> dict[str, str]:
    """Normalize CSV headers to lowercase snake_case-like keys."""

    normalized: dict[str, str] = {}
    for raw_key, raw_value in row.items():
        key = re.sub(r"[^a-z0-9]+", "_", str(raw_key or "").strip().lower()).strip("_")
        normalized[key] = str(raw_value or "").strip()
    return normalized


def _statistics_row(row: dict[str, str]) -> dict[str, Any]:
    """Convert a normalized CSV row into consistent statistics fields."""

    return {
        "group": _first_value(row, "group", "condition", "treatment"),
        "variable": _first_value(row, "marker", "variable", "analyte", "measure"),
        "comparison": _comparison_label(row),
        "n": _float_value(_first_value(row, "n", "sample_size", "sample_n")),
        "mean": _float_value(_first_value(row, "mean", "mean_intensity", "average")),
        "sd": _float_value(_first_value(row, "sd", "standard_deviation", "stdev")),
        "sem": _float_value(_first_value(row, "sem", "standard_error", "standard_error_of_mean")),
        "p_value": _float_value(_first_value(row, "p_value", "p", "adjusted_p_value", "adj_p")),
        "test": _first_value(row, "test", "statistical_test", "analysis"),
    }


def _comparison_label(row: dict[str, str]) -> str | None:
    """Return comparison label from explicit or paired group columns."""

    explicit = _first_value(row, "comparison", "comparison_label", "contrast")
    if explicit:
        return explicit
    group_a = _first_value(row, "group_a", "comparison_group_1")
    group_b = _first_value(row, "group_b", "comparison_group_2")
    if group_a and group_b:
        return f"{group_a} vs {group_b}"
    return None


def _first_value(row: dict[str, str], *keys: str) -> str | None:
    """Return first non-empty row value for candidate keys."""

    for key in keys:
        value = row.get(key)
        if value:
            return value
    return None


def _float_value(value: str | None) -> float | None:
    """Parse a numeric value, tolerating p-value strings like '<0.001'."""

    if not value:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?(?:e-?\d+)?", value, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def unique_preserve_order(values: Any) -> list[Any]:
    """Return unique, truthy values in first-seen order."""

    seen: set[Any] = set()
    output: list[Any] = []
    for value in values:
        if value in {None, ""} or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _normalized_extension(path: Path) -> str:
    """Return supported extension, including compound .pzfx.zip."""

    name = path.name.lower()
    if name.endswith(".pzfx.zip"):
        return ".pzfx.zip"
    return path.suffix.lower()


def _asset_type_for_file(path: Path) -> str:
    """Map a GraphPad-related file extension to ResearchOS asset type."""

    extension = _normalized_extension(path)
    if extension in {".prism", ".pzfx", ".pzfx.zip"}:
        return "graphpad"
    if extension in {".csv", ".xlsx", ".xls"}:
        return "spreadsheet"
    if extension in {".png", ".jpg", ".jpeg", ".svg"}:
        return "image"
    if extension == ".pdf":
        return "pdf"
    return "other"


def _stem_without_supported_extension(filename: str) -> str:
    """Remove known extensions while handling .pzfx.zip as one extension."""

    lower = filename.lower()
    for extension in sorted(SUPPORTED_EXTENSIONS, key=len, reverse=True):
        if lower.endswith(extension):
            return filename[: -len(extension)]
    return Path(filename).stem


def _title_for_file(path: Path) -> str:
    """Build a readable asset title from a filename."""

    stem = _stem_without_supported_extension(path.name)
    return re.sub(r"[_-]+", " ", stem).strip() or path.name


def _source_folder_for_file(path: Path, folders: list[Path]) -> str:
    """Return the configured folder that contains a discovered file."""

    resolved = path.resolve()
    for folder in folders:
        try:
            resolved.relative_to(folder)
            return str(folder)
        except ValueError:
            continue
    return ""
