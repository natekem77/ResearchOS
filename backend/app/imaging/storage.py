"""Storage conventions for immutable imaging inputs and derived outputs."""

from __future__ import annotations

from pathlib import Path


def raw_asset_directory(base_dir: Path, asset_id: str) -> Path:
    return base_dir / "raw" / asset_id


def job_output_directory(base_dir: Path, job_id: str) -> Path:
    return base_dir / "jobs" / job_id

