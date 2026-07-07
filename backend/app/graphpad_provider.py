"""GraphPad provider skeleton for local asset discovery.

This module deliberately avoids parsing proprietary Prism content. It only
discovers GraphPad-adjacent files and registers them as ResearchOS assets so
they can be linked to experiments.
"""

from __future__ import annotations

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
        existing = store.get_asset_by_provider_path(GRAPHPAD_PROVIDER, stored_path)
        if existing is not None:
            if not existing.get("experiment_id") and inferred_experiment_id:
                existing = store.link_asset(str(existing["asset_id"]), inferred_experiment_id) or existing
            skipped_assets.append(existing)
            continue

        asset = store.register_asset(
            asset_type=_asset_type_for_file(file_path),
            experiment_id=inferred_experiment_id,
            title=_title_for_file(file_path),
            filename=file_path.name,
            provider=GRAPHPAD_PROVIDER,
            path=stored_path,
            metadata={
                "extension": _normalized_extension(file_path),
                "source_folder": _source_folder_for_file(file_path, folders),
                "parser": "not_implemented",
            },
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
