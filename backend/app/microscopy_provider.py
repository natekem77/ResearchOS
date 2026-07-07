"""Microscopy/image provider skeleton for filename-based asset metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.storage import PROJECT_ROOT, SQLiteStore

MICROSCOPY_PROVIDER = "microscopy"
SUPPORTED_IMAGE_EXTENSIONS = (
    ".tif",
    ".tiff",
    ".png",
    ".jpg",
    ".jpeg",
    ".czi",
    ".lif",
    ".nd2",
    ".oir",
    ".svs",
)
MICROSCOPY_EXTENSIONS = {".tif", ".tiff", ".czi", ".lif", ".nd2", ".oir", ".svs"}
KNOWN_MARKERS = ("SIX6", "BRN3B", "DAPI", "RAX", "VSX2", "CRX", "RCVRN", "RBPMS", "POU4F2", "ISL1", "OTX2")


@dataclass(frozen=True)
class ImageScanResult:
    """Summary returned after scanning microscopy/image folders."""

    provider: str
    folders: list[str]
    supported_extensions: list[str]
    files_found: int
    assets_registered: int
    assets_skipped: int
    registered_assets: list[dict[str, Any]]
    skipped_assets: list[dict[str, Any]]


def microscopy_scan_folders(settings: Settings | None = None) -> list[Path]:
    """Return configured microscopy scan folders as absolute paths."""

    resolved_settings = settings or get_settings()
    raw_folders = re.split(r"[,;]", resolved_settings.microscopy_scan_folders)
    folders: list[Path] = []
    for raw_folder in raw_folders:
        if not raw_folder.strip():
            continue
        path = Path(raw_folder.strip())
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        folders.append(path.resolve())
    return folders


def microscopy_status(settings: Settings | None = None) -> dict[str, Any]:
    """Return local microscopy provider readiness and image asset count."""

    resolved_settings = settings or get_settings()
    folders = microscopy_scan_folders(resolved_settings)
    store = SQLiteStore(settings=resolved_settings)
    assets = store.list_assets(query=None)
    image_assets = [asset for asset in assets if asset.get("provider") == MICROSCOPY_PROVIDER]
    return {
        "provider": MICROSCOPY_PROVIDER,
        "status": "active",
        "folders": [{"path": str(folder), "exists": folder.exists()} for folder in folders],
        "supported_extensions": list(SUPPORTED_IMAGE_EXTENSIONS),
        "asset_count": len(image_assets),
        "message": "Microscopy provider extracts filename metadata only; image analysis is not implemented yet.",
    }


def scan_microscopy_assets(settings: Settings | None = None) -> ImageScanResult:
    """Discover supported image files and register/update image assets."""

    resolved_settings = settings or get_settings()
    store = SQLiteStore(settings=resolved_settings)
    folders = microscopy_scan_folders(resolved_settings)
    files = _discover_supported_files(folders)
    registered_assets: list[dict[str, Any]] = []
    skipped_assets: list[dict[str, Any]] = []

    for file_path in files:
        stored_path = str(file_path.resolve())
        inferred_experiment_id = infer_experiment_id_from_filename(file_path.name)
        metadata = _metadata_for_file(file_path, folders)
        existing = store.get_asset_by_provider_path(MICROSCOPY_PROVIDER, stored_path)
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
            provider=MICROSCOPY_PROVIDER,
            path=stored_path,
            metadata=metadata,
        )
        registered_assets.append(asset)

    return ImageScanResult(
        provider=MICROSCOPY_PROVIDER,
        folders=[str(folder) for folder in folders],
        supported_extensions=list(SUPPORTED_IMAGE_EXTENSIONS),
        files_found=len(files),
        assets_registered=len(registered_assets),
        assets_skipped=len(skipped_assets),
        registered_assets=registered_assets,
        skipped_assets=skipped_assets,
    )


def microscopy_assets(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Return registered microscopy/image assets."""

    resolved_settings = settings or get_settings()
    store = SQLiteStore(settings=resolved_settings)
    return [
        asset
        for asset in store.list_assets(query=None)
        if asset.get("provider") == MICROSCOPY_PROVIDER
        or asset.get("asset_type") in {"image", "microscopy"}
    ]


def infer_experiment_id_from_filename(filename: str) -> str | None:
    """Infer a human experiment ID from image filenames."""

    stem = Path(filename).stem
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_")
    nk_match = re.search(r"(?:^|_)NK_?Expt_?(\d+)(?:_|$)", normalized, flags=re.IGNORECASE)
    if nk_match:
        return f"NK_Expt_{nk_match.group(1)}"
    exp_match = re.search(r"(?:^|_)EXP_?(\d+)(?:_|$)", normalized, flags=re.IGNORECASE)
    if exp_match:
        return f"EXP_{exp_match.group(1)}"
    return None


def infer_markers_from_filename(filename: str) -> list[str]:
    """Infer marker names from filename tokens."""

    normalized = re.sub(r"[^A-Za-z0-9]+", "_", Path(filename).stem).upper()
    tokens = set(token for token in normalized.split("_") if token)
    return [marker for marker in KNOWN_MARKERS if marker.upper() in tokens]


def infer_timepoint_from_filename(filename: str) -> str | None:
    """Infer differentiation day/timepoint from filename tokens."""

    stem = Path(filename).stem
    match = re.search(r"(?:^|[^A-Za-z0-9])(?:D|DAY)[_-]?(\d{1,3})(?=$|[^A-Za-z0-9])", stem, flags=re.IGNORECASE)
    if match:
        return f"D{match.group(1)}"
    return None


def _discover_supported_files(folders: list[Path]) -> list[Path]:
    """Recursively find supported image files in existing scan folders."""

    discovered: list[Path] = []
    for folder in folders:
        if not folder.exists() or not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                discovered.append(path.resolve())
    return sorted(discovered, key=lambda path: str(path).lower())


def _metadata_for_file(file_path: Path, folders: list[Path]) -> dict[str, Any]:
    """Build filename-derived microscopy metadata."""

    return {
        "markers": infer_markers_from_filename(file_path.name),
        "timepoint": infer_timepoint_from_filename(file_path.name),
        "extension": file_path.suffix.lower(),
        "source_folder": _source_folder_for_file(file_path, folders),
        "parser": "filename_metadata",
    }


def _asset_type_for_file(path: Path) -> str:
    """Return image or microscopy asset type by extension."""

    return "microscopy" if path.suffix.lower() in MICROSCOPY_EXTENSIONS else "image"


def _title_for_file(path: Path) -> str:
    """Build a readable image asset title from filename."""

    return re.sub(r"[_-]+", " ", path.stem).strip() or path.name


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
