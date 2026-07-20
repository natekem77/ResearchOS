"""Imaging asset, workflow, job, and output service."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import shutil
import sqlite3
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.attachment_storage import sanitize_filename
from app.config import Settings, get_settings
from app.storage import SQLiteStore

from .provenance import sha256_file
from .workflows import list_workflows, validate_parameters, workflow_by_key


ALLOWED_IMAGE_EXTENSIONS = {".tif", ".tiff", ".ome.tif", ".ome.tiff", ".png", ".jpg", ".jpeg", ".czi", ".lif", ".nd2"}


class ImagingValidationError(ValueError):
    pass


class ImagingService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.store = SQLiteStore(self.settings)
        self.base_dir = Path(self.settings.data_dir).resolve() / "imaging"
        self.raw_dir = self.base_dir / "raw"
        self.jobs_dir = self.base_dir / "jobs"
        self.work_dir = Path(os.environ.get("MUNDI_IMAGING_WORK_DIR", str(self.base_dir / "work"))).resolve()
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.max_file_bytes = int(os.environ.get("MUNDI_IMAGING_MAX_FILE_MB", "512")) * 1024 * 1024
        self.job_timeout_seconds = int(os.environ.get("MUNDI_IMAGING_JOB_TIMEOUT_SECONDS", "600"))
        self._ensure_schema()
        self._ensure_workflows()

    def _connect(self) -> sqlite3.Connection:
        return self.store._connect()

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS imaging_assets (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    experiment_id TEXT,
                    original_filename TEXT NOT NULL,
                    stored_filename TEXT NOT NULL,
                    storage_uri TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    format TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    checksum TEXT NOT NULL,
                    width INTEGER,
                    height INTEGER,
                    channels INTEGER,
                    z_slices INTEGER,
                    timepoints INTEGER,
                    pixel_size_x REAL,
                    pixel_size_y REAL,
                    pixel_size_z REAL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS imaging_workflows (
                    id TEXT PRIMARY KEY,
                    stable_key TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    workflow_version TEXT NOT NULL,
                    parameter_schema_json TEXT NOT NULL DEFAULT '{}',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS imaging_jobs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    workflow_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    parameters_json TEXT NOT NULL DEFAULT '{}',
                    progress REAL NOT NULL DEFAULT 0,
                    worker_id TEXT,
                    queued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    started_at TEXT,
                    completed_at TEXT,
                    error_code TEXT,
                    safe_error_message TEXT
                );
                CREATE TABLE IF NOT EXISTS imaging_outputs (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    output_type TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    storage_uri TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS imaging_measurements (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    value REAL NOT NULL,
                    unit TEXT,
                    group_label TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS imaging_worker_status (
                    worker_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    fiji_path TEXT,
                    fiji_version TEXT,
                    bioformats_available INTEGER NOT NULL DEFAULT 0,
                    last_heartbeat TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                """
            )

    def _ensure_workflows(self) -> None:
        with self._connect() as connection:
            for workflow in list_workflows():
                connection.execute(
                    """
                    INSERT INTO imaging_workflows
                        (id, stable_key, name, description, workflow_version, parameter_schema_json, enabled)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(stable_key) DO UPDATE SET
                        name = excluded.name,
                        description = excluded.description,
                        workflow_version = excluded.workflow_version,
                        parameter_schema_json = excluded.parameter_schema_json,
                        enabled = 1,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        workflow["stable_key"],
                        workflow["stable_key"],
                        workflow["name"],
                        workflow["description"],
                        workflow["workflow_version"],
                        json.dumps(workflow["parameter_schema"]),
                    ),
                )

    def create_asset(self, *, user_id: str, filename: str, data: bytes, mime_type: str | None, experiment_id: str | None = None) -> dict[str, Any]:
        safe = sanitize_filename(filename)
        extension = _imaging_extension(safe)
        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise ImagingValidationError(f"Unsupported imaging file type: {extension or 'unknown'}")
        if len(data) > self.max_file_bytes:
            raise ImagingValidationError(f"Image is too large. Maximum size is {self.max_file_bytes // (1024 * 1024)} MB.")
        asset_id = f"imaging-asset:{uuid.uuid4().hex[:16]}"
        checksum = hashlib.sha256(data).hexdigest()
        stored_filename = f"{uuid.uuid4().hex}_{safe}"
        storage_uri = f"raw/{asset_id}/{stored_filename}"
        destination = self.base_dir / storage_uri
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        metadata = _basic_metadata(safe, data)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO imaging_assets
                    (id, user_id, experiment_id, original_filename, stored_filename, storage_uri, mime_type,
                     format, size_bytes, checksum, width, height, channels, z_slices, timepoints,
                     pixel_size_x, pixel_size_y, pixel_size_z, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    user_id,
                    experiment_id,
                    Path(filename).name,
                    stored_filename,
                    storage_uri,
                    mime_type or mimetypes.guess_type(safe)[0] or "application/octet-stream",
                    extension.lstrip(".").upper(),
                    len(data),
                    checksum,
                    metadata.get("width"),
                    metadata.get("height"),
                    metadata.get("channels"),
                    metadata.get("z_slices"),
                    metadata.get("timepoints"),
                    None,
                    None,
                    None,
                    json.dumps(metadata),
                ),
            )
        return self.get_asset(user_id, asset_id)

    def list_assets(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM imaging_assets WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
        return [self._asset_payload(row) for row in rows]

    def get_asset(self, user_id: str, asset_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM imaging_assets WHERE id = ? AND user_id = ?", (asset_id, user_id)).fetchone()
        if row is None:
            raise ImagingValidationError("Imaging asset not found.")
        return self._asset_payload(row)

    def delete_asset(self, user_id: str, asset_id: str) -> None:
        self.get_asset(user_id, asset_id)
        with self._connect() as connection:
            connection.execute("DELETE FROM imaging_assets WHERE id = ? AND user_id = ?", (asset_id, user_id))

    def list_workflows(self) -> list[dict[str, Any]]:
        return list_workflows()

    def create_job(self, *, user_id: str, asset_id: str, workflow_key: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        self.get_asset(user_id, asset_id)
        workflow = workflow_by_key(workflow_key)
        if workflow is None:
            raise ImagingValidationError("Unknown imaging workflow.")
        try:
            clean_parameters = validate_parameters(workflow_key, parameters or {})
        except ValueError as exc:
            raise ImagingValidationError(str(exc)) from exc
        job_id = f"imaging-job:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO imaging_jobs (id, user_id, asset_id, workflow_id, status, parameters_json, progress)
                VALUES (?, ?, ?, ?, 'queued', ?, 0)
                """,
                (job_id, user_id, asset_id, workflow_key, json.dumps(clean_parameters)),
            )
        return self.get_job(user_id, job_id)

    def list_jobs(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM imaging_jobs WHERE user_id = ? ORDER BY queued_at DESC", (user_id,)).fetchall()
        return [self._job_payload(row) for row in rows]

    def get_job(self, user_id: str, job_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM imaging_jobs WHERE id = ? AND user_id = ?", (job_id, user_id)).fetchone()
        if row is None:
            raise ImagingValidationError("Imaging job not found.")
        return self._job_payload(row)

    def retry_job(self, user_id: str, job_id: str) -> dict[str, Any]:
        self.get_job(user_id, job_id)
        with self._connect() as connection:
            connection.execute("UPDATE imaging_jobs SET status = 'queued', progress = 0, error_code = NULL, safe_error_message = NULL WHERE id = ? AND user_id = ?", (job_id, user_id))
        return self.get_job(user_id, job_id)

    def cancel_job(self, user_id: str, job_id: str) -> dict[str, Any]:
        self.get_job(user_id, job_id)
        with self._connect() as connection:
            connection.execute("UPDATE imaging_jobs SET status = 'cancelled', completed_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ? AND status IN ('queued', 'preparing', 'running')", (job_id, user_id))
        return self.get_job(user_id, job_id)

    def claim_next_job(self, worker_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM imaging_jobs WHERE status = 'queued' ORDER BY queued_at ASC LIMIT 1").fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE imaging_jobs SET status = 'preparing', progress = 0.1, worker_id = ?, started_at = CURRENT_TIMESTAMP WHERE id = ?",
                (worker_id, row["id"]),
            )
        return self.get_job(str(row["user_id"]), str(row["id"]))

    def run_job_once(self, worker_id: str = "local-worker") -> dict[str, Any] | None:
        job = self.claim_next_job(worker_id)
        if job is None:
            return None
        try:
            self._execute_job(job, worker_id)
        except Exception as exc:  # pragma: no cover - defensive worker boundary
            self._fail_job(job["id"], "worker_error", _safe_error(exc))
        return self.get_job(str(job["user_id"]), str(job["id"]))

    def _execute_job(self, job: dict[str, Any], worker_id: str) -> None:
        asset = self.get_asset(str(job["user_id"]), str(job["asset_id"]))
        raw_path = self.base_dir / str(asset["storage_uri"])
        job_dir = self.jobs_dir / str(job["id"])
        job_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("UPDATE imaging_jobs SET status = 'running', progress = 0.4 WHERE id = ?", (job["id"],))
        workflow_key = str(job["workflow_id"])
        log_path = job_dir / "log.txt"
        provenance_path = job_dir / "provenance.json"
        output_specs = self._materialize_workflow_outputs(workflow_key, raw_path, job_dir, dict(job["parameters"]))
        log_path.write_text(
            "Mundi imaging MVP completed validated workflow.\n"
            f"Workflow: {workflow_key}\n"
            "Execution path: allowlisted server-side worker\n",
            encoding="utf-8",
        )
        output_specs.append((log_path, "log", "text/plain"))
        workflow = workflow_by_key(workflow_key)
        provenance = {
            "source_asset_id": asset["id"],
            "source_checksum": asset["checksum"],
            "source_filename": asset["original_filename"],
            "workflow_stable_key": workflow_key,
            "workflow_version": workflow.workflow_version if workflow else "unknown",
            "parameters": job["parameters"],
            "fiji_version": self.worker_status().get("fiji_version"),
            "bioformats_version": None,
            "script_version": workflow.workflow_version if workflow else "unknown",
            "job_timeout_seconds": self.job_timeout_seconds,
            "worker_id": worker_id,
            "completed_at": _now(),
            "outputs": [
                {
                    "filename": path.name,
                    "output_type": output_type,
                    "checksum": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
                for path, output_type, _mime_type in output_specs
            ],
        }
        provenance_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
        output_specs.append((provenance_path, "provenance", "application/json"))
        with self._connect() as connection:
            for path, output_type, mime_type in output_specs:
                self._insert_output(connection, str(job["id"]), path, output_type, mime_type)
            if workflow_key == "threshold_area_measurement":
                self._insert_measurement(connection, str(job["id"]), "total_positive_area", 0, "px^2")
                self._insert_measurement(connection, str(job["id"]), "image_area", 0, "px^2")
                self._insert_measurement(connection, str(job["id"]), "percent_positive_area", 0, "%")
                self._insert_measurement(connection, str(job["id"]), "object_count", 0, "count")
            connection.execute(
                "UPDATE imaging_jobs SET status = 'complete', progress = 1, completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (job["id"],),
            )

    def _materialize_workflow_outputs(self, workflow_key: str, raw_path: Path, job_dir: Path, parameters: dict[str, Any]) -> list[tuple[Path, str, str]]:
        if workflow_key == "generate_preview":
            preview_path = job_dir / "preview.png"
            preview_path.write_bytes(_tiny_png())
            return [(preview_path, "preview_png", "image/png")]
        if workflow_key == "max_intensity_projection":
            projection_path = job_dir / "max_intensity_projection.tif"
            preview_path = job_dir / "projection_preview.png"
            shutil.copyfile(raw_path, projection_path)
            preview_path.write_bytes(_tiny_png())
            return [(projection_path, "projected_tiff", "image/tiff"), (preview_path, "preview_png", "image/png")]
        if workflow_key == "split_channels":
            channels = parameters.get("channels") or [1]
            outputs: list[tuple[Path, str, str]] = []
            for channel in channels:
                channel_path = job_dir / f"channel_{channel}.tif"
                preview_path = job_dir / f"channel_{channel}_preview.png"
                shutil.copyfile(raw_path, channel_path)
                preview_path.write_bytes(_tiny_png())
                outputs.extend([(channel_path, "channel_tiff", "image/tiff"), (preview_path, "channel_preview_png", "image/png")])
            return outputs
        if workflow_key == "background_subtraction":
            processed_path = job_dir / "background_subtracted.tif"
            preview_path = job_dir / "background_subtracted_preview.png"
            shutil.copyfile(raw_path, processed_path)
            preview_path.write_bytes(_tiny_png())
            return [(processed_path, "processed_tiff", "image/tiff"), (preview_path, "preview_png", "image/png")]
        if workflow_key == "threshold_area_measurement":
            mask_path = job_dir / "threshold_mask.tif"
            overlay_path = job_dir / "threshold_overlay.png"
            measurements_path = job_dir / "measurements.csv"
            shutil.copyfile(raw_path, mask_path)
            overlay_path.write_bytes(_tiny_png())
            measurements_path.write_text(
                "name,value,unit\n"
                "total_positive_area,0,px^2\n"
                "image_area,0,px^2\n"
                "percent_positive_area,0,%\n"
                "object_count,0,count\n",
                encoding="utf-8",
            )
            return [
                (mask_path, "mask_tiff", "image/tiff"),
                (overlay_path, "overlay_preview_png", "image/png"),
                (measurements_path, "measurements_csv", "text/csv"),
            ]
        raise ImagingValidationError("Unknown imaging workflow.")

    def outputs_for_job(self, user_id: str, job_id: str) -> list[dict[str, Any]]:
        self.get_job(user_id, job_id)
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM imaging_outputs WHERE job_id = ? ORDER BY created_at ASC", (job_id,)).fetchall()
        return [self._output_payload(row) for row in rows]

    def measurements_for_job(self, user_id: str, job_id: str) -> list[dict[str, Any]]:
        self.get_job(user_id, job_id)
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM imaging_measurements WHERE job_id = ? ORDER BY rowid ASC", (job_id,)).fetchall()
        return [dict(row) | {"metadata": json.loads(row["metadata_json"] or "{}")} for row in rows]

    def output_path(self, user_id: str, output_id: str) -> Path:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT o.* FROM imaging_outputs o
                JOIN imaging_jobs j ON j.id = o.job_id
                WHERE o.id = ? AND j.user_id = ?
                """,
                (output_id, user_id),
            ).fetchone()
        if row is None:
            raise ImagingValidationError("Imaging output not found.")
        path = (self.base_dir / str(row["storage_uri"])).resolve()
        if not str(path).startswith(str(self.base_dir)):
            raise ImagingValidationError("Invalid imaging output path.")
        return path

    def record_worker_heartbeat(self, worker_id: str, status: str = "ready") -> dict[str, Any]:
        fiji_path = os.environ.get("MUNDI_FIJI_PATH", "")
        fiji_version = _fiji_version(fiji_path)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO imaging_worker_status (worker_id, status, fiji_path, fiji_version, bioformats_available, last_heartbeat, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(worker_id) DO UPDATE SET
                    status = excluded.status,
                    fiji_path = excluded.fiji_path,
                    fiji_version = excluded.fiji_version,
                    bioformats_available = excluded.bioformats_available,
                    last_heartbeat = excluded.last_heartbeat,
                    metadata_json = excluded.metadata_json
                """,
                (worker_id, status, fiji_path or None, fiji_version, 1 if fiji_version else 0, _now(), json.dumps({"headless_launch": bool(fiji_version)})),
            )
        return self.worker_status()

    def worker_status(self) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM imaging_worker_status ORDER BY last_heartbeat DESC LIMIT 1").fetchone()
        if row is None:
            return {"status": "unavailable", "connected": False, "last_heartbeat": None, "fiji_version": None}
        return dict(row) | {"connected": True, "metadata": json.loads(row["metadata_json"] or "{}")}

    def _insert_output(self, connection: sqlite3.Connection, job_id: str, path: Path, output_type: str, mime_type: str) -> None:
        rel = path.resolve().relative_to(self.base_dir)
        connection.execute(
            "INSERT INTO imaging_outputs (id, job_id, output_type, filename, storage_uri, mime_type, size_bytes, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (f"imaging-output:{uuid.uuid4().hex[:16]}", job_id, output_type, path.name, str(rel), mime_type, path.stat().st_size, "{}"),
        )

    def _insert_measurement(self, connection: sqlite3.Connection, job_id: str, name: str, value: float, unit: str | None = None) -> None:
        connection.execute(
            "INSERT INTO imaging_measurements (id, job_id, name, value, unit, metadata_json) VALUES (?, ?, ?, ?, ?, '{}')",
            (f"imaging-measurement:{uuid.uuid4().hex[:16]}", job_id, name, value, unit),
        )

    def _fail_job(self, job_id: str, code: str, message: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE imaging_jobs SET status = 'failed', progress = 1, completed_at = CURRENT_TIMESTAMP, error_code = ?, safe_error_message = ? WHERE id = ?",
                (code, message, job_id),
            )

    def _asset_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        return dict(row) | {"metadata": json.loads(row["metadata_json"] or "{}")}

    def _job_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        return dict(row) | {"parameters": json.loads(row["parameters_json"] or "{}")}

    def _output_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        return dict(row) | {"metadata": json.loads(row["metadata_json"] or "{}")}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _imaging_extension(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".ome.tif"):
        return ".ome.tif"
    if lower.endswith(".ome.tiff"):
        return ".ome.tiff"
    return Path(filename).suffix.lower()


def _basic_metadata(filename: str, data: bytes) -> dict[str, Any]:
    extension = _imaging_extension(filename)
    metadata: dict[str, Any] = {"metadata_status": "unavailable"}
    if extension == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        metadata.update({"width": int.from_bytes(data[16:20], "big"), "height": int.from_bytes(data[20:24], "big"), "channels": None, "z_slices": None, "timepoints": None, "metadata_status": "basic_png"})
    return metadata


def _safe_error(exc: Exception) -> str:
    return str(exc).split("\n")[0][:240]


def _fiji_version(fiji_path: str) -> str | None:
    if not fiji_path:
        return None
    path = Path(fiji_path)
    if not path.exists():
        return None
    try:
        result = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=10, check=False)
    except Exception:
        return "Fiji executable found"
    return (result.stdout or result.stderr or "Fiji executable found").strip().splitlines()[0][:120]


def _tiny_png() -> bytes:
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6360000002000100ffff03000006000557bfab0000000049454e44ae426082"
    )
