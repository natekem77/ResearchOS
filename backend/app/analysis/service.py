"""Analysis dataset catalog, remote worker queue, and bulk-QC vertical slice."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import platform
import sqlite3
import statistics
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.storage import PROJECT_ROOT, SQLiteStore

from .workflows import list_workflows, validate_parameters, workflow_by_key

logger = logging.getLogger(__name__)


class AnalysisValidationError(ValueError):
    pass


class AnalysisAuthorizationError(PermissionError):
    pass


class AnalysisService:
    """SQLite-backed foundation for lab-hosted analysis workers."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.store = SQLiteStore(self.settings)
        self.data_dir = _resolve_data_dir(self.settings.data_dir)
        self.base_dir = self.data_dir / "analysis"
        self.outputs_dir = self.base_dir / "outputs"
        self.server_data_dir = self.base_dir / "server-data"
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self.server_data_dir.mkdir(parents=True, exist_ok=True)
        self.allowed_roots = _analysis_roots(self.data_dir, self.server_data_dir)
        self.worker_token = os.environ.get("MUNDI_COMPUTE_WORKER_TOKEN", "dev-compute-worker-token")
        self._ensure_schema()
        self._ensure_storage_locations()
        self._ensure_workflows()
        logger.debug(
            "analysis paths database=%s outputs=%s roots=%s",
            self.store.path,
            self.outputs_dir,
            [str(root) for root in self.allowed_roots],
        )

    def _connect(self) -> sqlite3.Connection:
        return self.store._connect()

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS analysis_workers (
                    worker_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    hostname TEXT,
                    operating_system TEXT,
                    architecture TEXT,
                    cpu_count INTEGER,
                    ram_gb REAL,
                    gpu_inventory_json TEXT NOT NULL DEFAULT '[]',
                    available_disk_gb REAL,
                    supported_runtimes_json TEXT NOT NULL DEFAULT '[]',
                    supported_workflows_json TEXT NOT NULL DEFAULT '[]',
                    software_versions_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    last_heartbeat TEXT NOT NULL,
                    running_job_count INTEGER NOT NULL DEFAULT 0,
                    maximum_concurrent_jobs INTEGER NOT NULL DEFAULT 1,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS analysis_storage_locations (
                    id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    root_path TEXT NOT NULL UNIQUE,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS analysis_datasets (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    modality TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    worker_id TEXT,
                    storage_location_id TEXT NOT NULL,
                    counts_path TEXT,
                    metadata_path TEXT,
                    organism TEXT,
                    genome_build TEXT,
                    assay TEXT,
                    sample_count INTEGER,
                    cell_count INTEGER,
                    features_count INTEGER,
                    metadata_summary_json TEXT NOT NULL DEFAULT '{}',
                    checksum TEXT,
                    access_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS analysis_workflows (
                    id TEXT PRIMARY KEY,
                    stable_key TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    workflow_version TEXT NOT NULL,
                    category TEXT NOT NULL,
                    modality TEXT NOT NULL,
                    parameter_schema_json TEXT NOT NULL DEFAULT '{}',
                    resource_request_json TEXT NOT NULL DEFAULT '{}',
                    supported_runtimes_json TEXT NOT NULL DEFAULT '[]',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS analysis_jobs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    dataset_id TEXT NOT NULL,
                    workflow_id TEXT NOT NULL,
                    workflow_version TEXT NOT NULL,
                    worker_id TEXT,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 0,
                    parameters_json TEXT NOT NULL DEFAULT '{}',
                    progress REAL NOT NULL DEFAULT 0,
                    current_stage TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    queued_at TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    error_summary TEXT,
                    cancellation_requested INTEGER NOT NULL DEFAULT 0,
                    resource_request_json TEXT NOT NULL DEFAULT '{}',
                    reproducibility_manifest_json TEXT NOT NULL DEFAULT '{}',
                    deleted_at TEXT
                );
                CREATE TABLE IF NOT EXISTS analysis_outputs (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    dataset_id TEXT NOT NULL,
                    registration_key TEXT,
                    output_type TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    storage_uri TEXT,
                    mime_type TEXT,
                    size_bytes INTEGER,
                    structured_json TEXT NOT NULL DEFAULT '{}',
                    viewer_config_json TEXT NOT NULL DEFAULT '{}',
                    provenance_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_analysis_outputs_registration
                    ON analysis_outputs(job_id, registration_key)
                    WHERE registration_key IS NOT NULL;
                CREATE TABLE IF NOT EXISTS analysis_notebook_references (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    notebook_id TEXT,
                    experiment_id TEXT,
                    output_id TEXT NOT NULL,
                    reference_type TEXT NOT NULL,
                    caption TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS analysis_audit_log (
                    id TEXT PRIMARY KEY,
                    actor_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            _ensure_column(connection, "analysis_outputs", "registration_key", "TEXT")

    def _ensure_storage_locations(self) -> None:
        with self._connect() as connection:
            for index, root in enumerate(self.allowed_roots):
                location_id = "analysis-storage:default" if index == 0 else f"analysis-storage:{hashlib.sha1(str(root).encode()).hexdigest()[:12]}"
                connection.execute(
                    """
                    INSERT INTO analysis_storage_locations (id, display_name, root_path, enabled)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(root_path) DO UPDATE SET enabled = 1
                    """,
                    (location_id, "Approved lab data root", str(root)),
                )

    def _ensure_workflows(self) -> None:
        with self._connect() as connection:
            for workflow in list_workflows():
                connection.execute(
                    """
                    INSERT INTO analysis_workflows
                        (id, stable_key, name, description, workflow_version, category, modality,
                         parameter_schema_json, resource_request_json, supported_runtimes_json, enabled)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(stable_key) DO UPDATE SET
                        name = excluded.name,
                        description = excluded.description,
                        workflow_version = excluded.workflow_version,
                        category = excluded.category,
                        modality = excluded.modality,
                        parameter_schema_json = excluded.parameter_schema_json,
                        resource_request_json = excluded.resource_request_json,
                        supported_runtimes_json = excluded.supported_runtimes_json,
                        enabled = 1,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        workflow["stable_key"],
                        workflow["stable_key"],
                        workflow["name"],
                        workflow["description"],
                        workflow["workflow_version"],
                        workflow["category"],
                        workflow["modality"],
                        json.dumps(workflow["parameter_schema"]),
                        json.dumps(workflow["resource_request"]),
                        json.dumps(workflow["supported_runtimes"]),
                    ),
                )

    def require_worker_token(self, token: str | None) -> None:
        if not token or token != self.worker_token:
            raise AnalysisAuthorizationError("Invalid compute worker credentials.")

    def list_workers(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM analysis_workers ORDER BY last_heartbeat DESC").fetchall()
        return [self._worker_payload(row) for row in rows]

    def register_worker(self, payload: dict[str, Any]) -> dict[str, Any]:
        worker_id = _clean_required(payload.get("worker_id"), "worker_id")
        display_name = str(payload.get("display_name") or worker_id).strip() or worker_id
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analysis_workers
                    (worker_id, display_name, hostname, operating_system, architecture, cpu_count, ram_gb,
                     gpu_inventory_json, available_disk_gb, supported_runtimes_json, supported_workflows_json,
                     software_versions_json, status, last_heartbeat, running_job_count, maximum_concurrent_jobs)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(worker_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    hostname = excluded.hostname,
                    operating_system = excluded.operating_system,
                    architecture = excluded.architecture,
                    cpu_count = excluded.cpu_count,
                    ram_gb = excluded.ram_gb,
                    gpu_inventory_json = excluded.gpu_inventory_json,
                    available_disk_gb = excluded.available_disk_gb,
                    supported_runtimes_json = excluded.supported_runtimes_json,
                    supported_workflows_json = excluded.supported_workflows_json,
                    software_versions_json = excluded.software_versions_json,
                    status = excluded.status,
                    last_heartbeat = excluded.last_heartbeat,
                    running_job_count = excluded.running_job_count,
                    maximum_concurrent_jobs = excluded.maximum_concurrent_jobs,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    worker_id,
                    display_name,
                    payload.get("hostname") or platform.node(),
                    payload.get("operating_system") or platform.platform(),
                    payload.get("architecture") or platform.machine(),
                    _optional_int(payload.get("cpu_count")),
                    _optional_float(payload.get("ram_gb")),
                    json.dumps(payload.get("gpu_inventory") or []),
                    _optional_float(payload.get("available_disk_gb")),
                    json.dumps(payload.get("supported_runtimes") or ["python"]),
                    json.dumps(payload.get("supported_workflows") or ["bulk_rnaseq_validation_qc"]),
                    json.dumps(payload.get("software_versions") or {}),
                    str(payload.get("status") or "ready"),
                    now,
                    _optional_int(payload.get("running_job_count")) or 0,
                    _optional_int(payload.get("maximum_concurrent_jobs")) or 1,
                ),
            )
        self._audit(worker_id, "worker.register", worker_id, {"status": payload.get("status") or "ready"})
        return self.get_worker(worker_id)

    def record_worker_heartbeat(self, worker_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        if self._worker_row(worker_id) is None:
            self.register_worker({"worker_id": worker_id, "display_name": worker_id})
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE analysis_workers
                SET status = ?, running_job_count = ?, last_heartbeat = ?, updated_at = CURRENT_TIMESTAMP
                WHERE worker_id = ?
                """,
                (
                    str(payload.get("status") or "ready"),
                    _optional_int(payload.get("running_job_count")) or 0,
                    _now(),
                    worker_id,
                ),
            )
        return self.get_worker(worker_id)

    def get_worker(self, worker_id: str) -> dict[str, Any]:
        row = self._worker_row(worker_id)
        if row is None:
            raise AnalysisValidationError("Compute worker not found.")
        return self._worker_payload(row)

    def _worker_row(self, worker_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM analysis_workers WHERE worker_id = ?", (worker_id,)).fetchone()

    def list_storage_locations(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM analysis_storage_locations WHERE enabled = 1 ORDER BY created_at ASC").fetchall()
        return [dict(row) | {"root_path": _display_root(row["root_path"])} for row in rows]

    def browse_storage_location(self, storage_location_id: str, relative_path: str = "") -> dict[str, Any]:
        root, clean_root_relative = self._resolve_location_path(storage_location_id, relative_path or ".")
        if not root.exists() or not root.is_dir():
            raise AnalysisValidationError("Approved data folder not found.")
        entries = []
        for child in sorted(root.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))[:200]:
            if child.name.startswith("."):
                continue
            relative = str((Path(clean_root_relative) / child.name) if clean_root_relative not in {"", "."} else Path(child.name))
            candidate = _dataset_candidate(child)
            entries.append(
                {
                    "name": child.name,
                    "relative_path": relative,
                    "is_directory": child.is_dir(),
                    "size_bytes": child.stat().st_size if child.is_file() else None,
                    "candidate": candidate,
                }
            )
        return {
            "storage_location_id": storage_location_id,
            "path": "" if clean_root_relative == "." else clean_root_relative,
            "entries": entries,
        }

    def register_server_dataset(self, *, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        display_name = _clean_required(payload.get("display_name"), "display_name")
        modality = str(payload.get("modality") or "bulk_rna_seq")
        source_type = str(payload.get("source_type") or "server_folder")
        storage_location_id = str(payload.get("storage_location_id") or "analysis-storage:default")
        counts_path = _clean_required(payload.get("counts_path"), "counts_path")
        metadata_path = _clean_required(payload.get("metadata_path"), "metadata_path")
        counts_abs, counts_rel = self._resolve_location_path(storage_location_id, counts_path)
        metadata_abs, metadata_rel = self._resolve_location_path(storage_location_id, metadata_path)
        if not counts_abs.exists() or not counts_abs.is_file():
            raise AnalysisValidationError("Count matrix path is not available under an approved data root.")
        if not metadata_abs.exists() or not metadata_abs.is_file():
            raise AnalysisValidationError("Sample metadata path is not available under an approved data root.")
        summary = _peek_bulk_dataset(counts_abs, metadata_abs)
        dataset_id = f"analysis-dataset:{uuid.uuid4().hex[:16]}"
        checksum = _fingerprint_paths([counts_abs, metadata_abs])
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analysis_datasets
                    (id, user_id, display_name, modality, source_type, worker_id, storage_location_id,
                     counts_path, metadata_path, organism, genome_build, assay, sample_count,
                     features_count, metadata_summary_json, checksum, access_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dataset_id,
                    user_id,
                    display_name,
                    modality,
                    source_type,
                    payload.get("worker_id"),
                    storage_location_id,
                    counts_rel,
                    metadata_rel,
                    payload.get("organism"),
                    payload.get("genome_build"),
                    payload.get("assay"),
                    summary["sample_count"],
                    summary["feature_count"],
                    json.dumps(summary),
                    checksum,
                    json.dumps({"owner": user_id}),
                ),
            )
        self._audit(user_id, "dataset.register", dataset_id, {"modality": modality})
        return self.get_dataset(user_id, dataset_id)

    def list_datasets(self, user_id: str, modality: str | None = None, query: str | None = None) -> list[dict[str, Any]]:
        where = "WHERE user_id = ?"
        params: list[Any] = [user_id]
        if modality:
            where += " AND modality = ?"
            params.append(modality)
        if query and query.strip():
            where += " AND lower(display_name) LIKE ?"
            params.append(f"%{query.strip().lower()}%")
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM analysis_datasets {where} ORDER BY updated_at DESC, created_at DESC",
                params,
            ).fetchall()
        return [self._dataset_payload(row) for row in rows]

    def get_dataset(self, user_id: str, dataset_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM analysis_datasets WHERE id = ? AND user_id = ?",
                (dataset_id, user_id),
            ).fetchone()
        if row is None:
            raise AnalysisValidationError("Analysis dataset not found.")
        return self._dataset_payload(row)

    def list_workflows(self, query: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if query and query.strip():
                rows = connection.execute(
                    """
                    SELECT * FROM analysis_workflows
                    WHERE enabled = 1 AND (lower(name) LIKE ? OR lower(category) LIKE ? OR lower(description) LIKE ?)
                    ORDER BY category, name
                    """,
                    (f"%{query.strip().lower()}%",) * 3,
                ).fetchall()
            else:
                rows = connection.execute("SELECT * FROM analysis_workflows WHERE enabled = 1 ORDER BY category, name").fetchall()
        return [self._workflow_payload(row) for row in rows]

    def create_job(self, *, user_id: str, dataset_id: str, workflow_key: str, parameters: dict[str, Any] | None = None, priority: int = 0) -> dict[str, Any]:
        dataset = self.get_dataset(user_id, dataset_id)
        workflow = workflow_by_key(workflow_key)
        if workflow is None:
            raise AnalysisValidationError("Unknown analysis workflow.")
        if workflow["stable_key"] != "bulk_rnaseq_validation_qc":
            raise AnalysisValidationError("This workflow is scaffolded but not executable in the current milestone.")
        if workflow["modality"] != dataset["modality"]:
            raise AnalysisValidationError("Workflow does not support this dataset modality.")
        try:
            clean_parameters = validate_parameters(workflow_key, parameters or {})
        except ValueError as exc:
            raise AnalysisValidationError(str(exc)) from exc
        job_id = f"analysis-job:{uuid.uuid4().hex[:16]}"
        manifest = {
            "dataset_id": dataset_id,
            "dataset_checksum": dataset.get("checksum"),
            "workflow_stable_key": workflow_key,
            "workflow_version": workflow["workflow_version"],
            "parameters": clean_parameters,
            "source_files_remain_server_local": True,
            "created_at": _now(),
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analysis_jobs
                    (id, user_id, dataset_id, workflow_id, workflow_version, status, priority,
                     parameters_json, progress, current_stage, queued_at, resource_request_json,
                     reproducibility_manifest_json)
                VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, 0, 'Queued', CURRENT_TIMESTAMP, ?, ?)
                """,
                (
                    job_id,
                    user_id,
                    dataset_id,
                    workflow_key,
                    workflow["workflow_version"],
                    priority,
                    json.dumps(clean_parameters),
                    json.dumps(workflow["resource_request"]),
                    json.dumps(manifest),
                ),
            )
        self._audit(user_id, "job.create", job_id, {"workflow": workflow_key})
        return self.get_job(user_id, job_id)

    def list_jobs(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM analysis_jobs WHERE user_id = ? AND deleted_at IS NULL ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [self._job_payload(row) for row in rows]

    def get_job(self, user_id: str, job_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM analysis_jobs WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                (job_id, user_id),
            ).fetchone()
        if row is None:
            raise AnalysisValidationError("Analysis job not found.")
        return self._job_payload(row)

    def claim_next_job(self, worker_id: str) -> dict[str, Any] | None:
        worker = self.get_worker(worker_id)
        if not worker.get("enabled", True):
            raise AnalysisValidationError("Compute worker is disabled.")
        supported = set(worker.get("supported_workflows") or [])
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM analysis_jobs WHERE status = 'queued' ORDER BY priority DESC, queued_at ASC"
            ).fetchall()
            selected = None
            for row in rows:
                if str(row["workflow_id"]) in supported:
                    selected = row
                    break
            logger.debug(
                "analysis worker queue worker_id=%s database=%s queued_jobs=%s claimed_job=%s",
                worker_id,
                self.store.path,
                len(rows),
                selected["id"] if selected is not None else None,
            )
            if selected is None:
                return None
            connection.execute(
                """
                UPDATE analysis_jobs
                SET status = 'claimed', worker_id = ?, progress = 0.05,
                    current_stage = 'Claimed by compute worker', started_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'queued'
                """,
                (worker_id, selected["id"]),
            )
        return self.get_job(str(selected["user_id"]), str(selected["id"]))

    def update_job_progress(self, worker_id: str, job_id: str, *, status: str | None = None, progress: float | None = None, current_stage: str | None = None) -> dict[str, Any]:
        row = self._job_for_worker(worker_id, job_id)
        next_status = status or row["status"]
        next_progress = _bounded_progress(progress if progress is not None else row["progress"])
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE analysis_jobs
                SET status = ?, progress = ?, current_stage = ?
                WHERE id = ? AND worker_id = ?
                """,
                (next_status, next_progress, current_stage or row["current_stage"], job_id, worker_id),
            )
        return self.get_job(str(row["user_id"]), job_id)

    def append_job_logs(self, worker_id: str, job_id: str, lines: list[str]) -> dict[str, Any]:
        row = self._job_for_worker(worker_id, job_id)
        job_dir = self.outputs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        log_path = job_dir / "worker.log"
        clean_lines = [_sanitize_log_line(line) for line in lines]
        with log_path.open("a", encoding="utf-8") as handle:
            for line in clean_lines:
                handle.write(line + "\n")
        with self._connect() as connection:
            self._insert_output(
                connection,
                job_id=str(row["id"]),
                dataset_id=str(row["dataset_id"]),
                output_type="log",
                display_name="Worker log",
                path=log_path,
                structured={},
                provenance={"worker_id": worker_id},
                replace_output_type=True,
            )
        return {"accepted": True, "line_count": len(clean_lines)}

    def complete_job(self, worker_id: str, job_id: str, outputs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        row = self._job_for_worker(worker_id, job_id)
        with self._connect() as connection:
            for output in outputs or []:
                self._insert_structured_worker_output(connection, row, output)
            connection.execute(
                """
                UPDATE analysis_jobs
                SET status = 'complete', progress = 1, current_stage = 'Complete', finished_at = CURRENT_TIMESTAMP
                WHERE id = ? AND worker_id = ?
                """,
                (job_id, worker_id),
            )
        return self.get_job(str(row["user_id"]), job_id)

    def fail_job(self, worker_id: str, job_id: str, error_summary: str) -> dict[str, Any]:
        row = self._job_for_worker(worker_id, job_id)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE analysis_jobs
                SET status = 'failed', progress = 1, current_stage = 'Failed',
                    error_summary = ?, finished_at = CURRENT_TIMESTAMP
                WHERE id = ? AND worker_id = ?
                """,
                (_sanitize_log_line(error_summary)[:500], job_id, worker_id),
            )
        return self.get_job(str(row["user_id"]), job_id)

    def cancel_job(self, user_id: str, job_id: str) -> dict[str, Any]:
        self.get_job(user_id, job_id)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE analysis_jobs
                SET cancellation_requested = 1,
                    status = CASE WHEN status = 'queued' THEN 'cancelled' ELSE status END,
                    finished_at = CASE WHEN status = 'queued' THEN CURRENT_TIMESTAMP ELSE finished_at END
                WHERE id = ? AND user_id = ?
                """,
                (job_id, user_id),
            )
        return self.get_job(user_id, job_id)

    def retry_job(self, user_id: str, job_id: str) -> dict[str, Any]:
        job = self.get_job(user_id, job_id)
        if job["status"] not in {"failed", "cancelled"}:
            raise AnalysisValidationError("Only failed or cancelled analysis jobs can be retried.")
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE analysis_jobs
                SET status = 'queued', worker_id = NULL, progress = 0, current_stage = 'Queued',
                    queued_at = CURRENT_TIMESTAMP, started_at = NULL, finished_at = NULL,
                    error_summary = NULL, cancellation_requested = 0
                WHERE id = ? AND user_id = ?
                """,
                (job_id, user_id),
            )
        return self.get_job(user_id, job_id)

    def delete_job(self, user_id: str, job_id: str) -> None:
        job = self.get_job(user_id, job_id)
        if job["status"] in {"claimed", "preparing", "running", "uploading_results"}:
            raise AnalysisValidationError("Running analysis jobs cannot be deleted. Cancel the job first.")
        with self._connect() as connection:
            connection.execute(
                "UPDATE analysis_jobs SET deleted_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
                (job_id, user_id),
            )

    def outputs_for_job(self, user_id: str, job_id: str) -> list[dict[str, Any]]:
        self.get_job(user_id, job_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM analysis_outputs WHERE job_id = ? ORDER BY created_at ASC",
                (job_id,),
            ).fetchall()
        return [self._output_payload(row) for row in rows]

    def get_output(self, user_id: str, output_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT o.* FROM analysis_outputs o
                JOIN analysis_jobs j ON j.id = o.job_id
                WHERE o.id = ? AND j.user_id = ?
                """,
                (output_id, user_id),
            ).fetchone()
        if row is None:
            raise AnalysisValidationError("Analysis output not found.")
        output = self._output_payload(row)
        return output | self._output_context(user_id, output)

    def rename_output(self, user_id: str, output_id: str, display_name: str) -> dict[str, Any]:
        clean = display_name.strip()
        if not clean:
            raise AnalysisValidationError("Output display name cannot be blank.")
        self.get_output(user_id, output_id)
        with self._connect() as connection:
            connection.execute(
                "UPDATE analysis_outputs SET display_name = ? WHERE id = ?",
                (clean, output_id),
            )
        self._audit(user_id, "output.rename", output_id, {"display_name": clean})
        return self.get_output(user_id, output_id)

    def references_for_output(self, user_id: str, output_id: str) -> list[dict[str, Any]]:
        self.get_output(user_id, output_id)
        return self._references_for_output_unchecked(user_id, output_id)

    def _references_for_output_unchecked(self, user_id: str, output_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM analysis_notebook_references
                WHERE user_id = ? AND output_id = ?
                ORDER BY created_at DESC
                """,
                (user_id, output_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_notebook_reference(
        self,
        user_id: str,
        *,
        output_id: str,
        notebook_id: str | None = None,
        experiment_id: str | None = None,
        reference_type: str = "linked",
        caption: str | None = None,
    ) -> dict[str, Any]:
        if reference_type not in {"linked", "snapshot"}:
            raise AnalysisValidationError("Unsupported analysis notebook reference type.")
        self.get_output(user_id, output_id)
        reference_id = f"analysis-reference:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analysis_notebook_references
                    (id, user_id, notebook_id, experiment_id, output_id, reference_type, caption)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (reference_id, user_id, notebook_id, experiment_id, output_id, reference_type, caption),
            )
            row = connection.execute(
                "SELECT * FROM analysis_notebook_references WHERE id = ?",
                (reference_id,),
            ).fetchone()
        self._audit(user_id, "output.notebook_reference", output_id, {"reference_type": reference_type})
        return dict(row)

    def delete_output(self, user_id: str, output_id: str, *, reference_mode: str = "block_if_referenced") -> dict[str, Any]:
        output = self.get_output(user_id, output_id)
        references = self.references_for_output(user_id, output_id)
        if references and reference_mode == "block_if_referenced":
            raise AnalysisValidationError("Analysis output is referenced by notebooks.")
        with self._connect() as connection:
            if reference_mode == "remove_references":
                connection.execute(
                    "DELETE FROM analysis_notebook_references WHERE user_id = ? AND output_id = ?",
                    (user_id, output_id),
                )
            elif reference_mode == "leave_placeholders":
                connection.execute(
                    """
                    UPDATE analysis_notebook_references
                    SET caption = COALESCE(caption, '') || ' [Output deleted]'
                    WHERE user_id = ? AND output_id = ?
                    """,
                    (user_id, output_id),
                )
            connection.execute("DELETE FROM analysis_outputs WHERE id = ?", (output_id,))
        storage_uri = output.get("storage_uri")
        if storage_uri:
            _safe_unlink(self.base_dir / str(storage_uri), self.base_dir)
        self._audit(user_id, "output.delete", output_id, {"reference_mode": reference_mode})
        return {"deleted": True, "references": references}

    def list_outputs(self, user_id: str, query: str | None = None) -> list[dict[str, Any]]:
        where = "WHERE j.user_id = ?"
        params: list[Any] = [user_id]
        if query and query.strip():
            where += " AND lower(o.display_name) LIKE ?"
            params.append(f"%{query.strip().lower()}%")
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT o.*, j.workflow_id AS job_workflow_id, j.workflow_version AS job_workflow_version,
                       j.status AS job_status, j.created_at AS job_created_at,
                       d.display_name AS dataset_name
                FROM analysis_outputs o
                JOIN analysis_jobs j ON j.id = o.job_id
                JOIN analysis_datasets d ON d.id = o.dataset_id
                {where}
                ORDER BY o.created_at DESC
                """,
                params,
            ).fetchall()
        return [self._output_payload(row) for row in rows]

    def output_groups(self, user_id: str) -> list[dict[str, Any]]:
        datasets = {dataset["id"]: dataset for dataset in self.list_datasets(user_id)}
        jobs = self.list_jobs(user_id)
        groups = []
        for job in jobs:
            outputs = self.outputs_for_job(user_id, str(job["id"]))
            if not outputs:
                continue
            groups.append(
                {
                    "dataset": datasets.get(job["dataset_id"], {"id": job["dataset_id"], "display_name": job["dataset_id"]}),
                    "job": job,
                    "outputs": outputs,
                }
            )
        return groups

    def demo_library(self) -> dict[str, Any]:
        return {"datasets": _demo_datasets(), "workspace": _demo_workspace_payload()}

    def install_demo_workspace(self, user_id: str) -> dict[str, Any]:
        demo_dir = self.allowed_roots[0] / "demo"
        bulk_dir = demo_dir / "bulk"
        bulk_dir.mkdir(parents=True, exist_ok=True)
        _write_demo_bulk_files(bulk_dir)
        installed = []
        for spec in _demo_datasets():
            if spec["modality"] != "bulk_rna_seq":
                installed.append(spec | {"status": "available_demo_only"})
                continue
            existing = self._dataset_by_name(user_id, spec["display_name"])
            if existing is None:
                dataset = self.register_server_dataset(
                    user_id=user_id,
                    payload={
                        "display_name": spec["display_name"],
                        "modality": "bulk_rna_seq",
                        "source_type": "demo_server_folder",
                        "counts_path": spec["counts_path"],
                        "metadata_path": spec["metadata_path"],
                        "organism": spec.get("organism"),
                        "assay": "RNA-seq",
                    },
                )
            else:
                dataset = self._dataset_payload(existing)
            if not self._completed_demo_job_exists(user_id, str(dataset["id"])):
                self.register_worker(
                    {
                        "worker_id": "demo-compute-worker",
                        "display_name": "Demo Compute Worker",
                        "supported_workflows": ["bulk_rnaseq_validation_qc"],
                        "supported_runtimes": ["python"],
                        "software_versions": {"python": platform.python_version()},
                        "status": "ready",
                    }
                )
                self.create_job(
                    user_id=user_id,
                    dataset_id=str(dataset["id"]),
                    workflow_key="bulk_rnaseq_validation_qc",
                    parameters={"sample_id_column": "sample", "group_column": "condition"},
                )
                self.run_claimed_job_once("demo-compute-worker")
            installed.append(dataset | {"status": "installed"})
        return {
            "workspace": _demo_workspace_payload(),
            "installed_datasets": installed,
            "jobs": self.list_jobs(user_id),
            "outputs": self.list_outputs(user_id),
        }

    def _dataset_by_name(self, user_id: str, display_name: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM analysis_datasets WHERE user_id = ? AND display_name = ?",
                (user_id, display_name),
            ).fetchone()

    def _completed_demo_job_exists(self, user_id: str, dataset_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM analysis_jobs
                WHERE user_id = ? AND dataset_id = ? AND workflow_id = 'bulk_rnaseq_validation_qc'
                  AND status = 'complete' AND deleted_at IS NULL
                LIMIT 1
                """,
                (user_id, dataset_id),
            ).fetchone()
        return row is not None

    def run_claimed_job_once(self, worker_id: str) -> dict[str, Any] | None:
        job = self.claim_next_job(worker_id)
        if job is None:
            return None
        try:
            self.update_job_progress(worker_id, str(job["id"]), status="preparing", progress=0.2, current_stage="Reading server-local dataset")
            outputs = self._execute_bulk_validation_qc(job, worker_id)
            self.update_job_progress(worker_id, str(job["id"]), status="uploading_results", progress=0.9, current_stage="Registering QC outputs")
            return self.complete_job(worker_id, str(job["id"]), outputs)
        except Exception as exc:  # pragma: no cover - worker boundary
            logger.exception("analysis worker failed job_id=%s worker_id=%s", job["id"], worker_id)
            return self.fail_job(worker_id, str(job["id"]), str(exc))

    def _execute_bulk_validation_qc(self, job: dict[str, Any], worker_id: str) -> list[dict[str, Any]]:
        if job["workflow_id"] != "bulk_rnaseq_validation_qc":
            raise AnalysisValidationError("Worker cannot execute this workflow.")
        dataset = self.get_dataset(str(job["user_id"]), str(job["dataset_id"]))
        counts_path, _ = self._resolve_location_path(str(dataset["storage_location_id"]), str(dataset["counts_path"]))
        metadata_path, _ = self._resolve_location_path(str(dataset["storage_location_id"]), str(dataset["metadata_path"]))
        parameters = dict(job.get("parameters") or {})
        report = _bulk_validation_report(
            counts_path,
            metadata_path,
            sample_id_column=str(parameters.get("sample_id_column") or "sample"),
            group_column=str(parameters.get("group_column") or "condition"),
        )
        job_dir = self.outputs_dir / str(job["id"])
        job_dir.mkdir(parents=True, exist_ok=True)
        report_path = job_dir / "bulk_qc_report.json"
        library_path = job_dir / "library_sizes.csv"
        provenance_path = job_dir / "provenance.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        with library_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["sample", "library_size", "detected_genes"])
            writer.writeheader()
            for row in report["sample_qc"]:
                writer.writerow(row)
        provenance = {
            "engine": "mundi-compute-agent",
            "worker_id": worker_id,
            "workflow_stable_key": job["workflow_id"],
            "workflow_version": job["workflow_version"],
            "dataset_id": dataset["id"],
            "dataset_checksum": dataset["checksum"],
            "parameters": parameters,
            "source_files_remain_server_local": True,
            "started_at": job.get("started_at"),
            "completed_at": _now(),
            "outputs": [
                {"filename": report_path.name, "checksum": _sha256_file(report_path)},
                {"filename": library_path.name, "checksum": _sha256_file(library_path)},
            ],
        }
        provenance_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
        return [
            {
                "output_type": "qc_report",
                "display_name": "Bulk RNA-seq QC Report",
                "path": str(report_path),
                "mime_type": "application/json",
                "structured": report,
                "provenance": provenance,
            },
            {
                "output_type": "table",
                "display_name": "Library Sizes",
                "path": str(library_path),
                "mime_type": "text/csv",
                "structured": {"columns": ["sample", "library_size", "detected_genes"], "rows": report["sample_qc"]},
                "provenance": provenance,
            },
            {
                "output_type": "provenance",
                "display_name": "Reproducibility Manifest",
                "path": str(provenance_path),
                "mime_type": "application/json",
                "structured": provenance,
                "provenance": provenance,
            },
        ]

    def _insert_structured_worker_output(self, connection: sqlite3.Connection, job: sqlite3.Row, output: dict[str, Any]) -> None:
        path_value = output.get("path")
        path = Path(str(path_value)).resolve() if path_value else None
        self._insert_output(
            connection,
            job_id=str(job["id"]),
            dataset_id=str(job["dataset_id"]),
            output_type=str(output.get("output_type") or "result"),
            display_name=str(output.get("display_name") or "Analysis result"),
            path=path,
            mime_type=str(output.get("mime_type") or "application/json"),
            structured=output.get("structured") if isinstance(output.get("structured"), dict) else {},
            provenance=output.get("provenance") if isinstance(output.get("provenance"), dict) else {},
        )

    def _insert_output(
        self,
        connection: sqlite3.Connection,
        *,
        job_id: str,
        dataset_id: str,
        output_type: str,
        display_name: str,
        path: Path | None = None,
        mime_type: str | None = None,
        structured: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        replace_output_type: bool = False,
        registration_key: str | None = None,
    ) -> None:
        storage_uri = None
        size_bytes = None
        if path is not None:
            resolved = path.resolve()
            if not _is_within(resolved, self.outputs_dir):
                raise AnalysisValidationError("Analysis output path must stay inside the analysis output directory.")
            storage_uri = str(resolved.relative_to(self.base_dir))
            size_bytes = resolved.stat().st_size if resolved.exists() else None
        if replace_output_type:
            connection.execute(
                "DELETE FROM analysis_outputs WHERE job_id = ? AND output_type = ?",
                (job_id, output_type),
            )
        key = registration_key or output_type
        connection.execute(
            "DELETE FROM analysis_outputs WHERE job_id = ? AND registration_key = ?",
            (job_id, key),
        )
        connection.execute(
            """
            INSERT INTO analysis_outputs
                (id, job_id, dataset_id, registration_key, output_type, display_name, storage_uri, mime_type,
                 size_bytes, structured_json, viewer_config_json, provenance_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?)
            """,
            (
                f"analysis-output:{uuid.uuid4().hex[:16]}",
                job_id,
                dataset_id,
                key,
                output_type,
                display_name,
                storage_uri,
                mime_type,
                size_bytes,
                json.dumps(structured or {}),
                json.dumps(provenance or {}),
            ),
        )

    def _resolve_location_path(self, storage_location_id: str, relative_path: str) -> tuple[Path, str]:
        clean = str(relative_path).strip().lstrip("/\\")
        if not clean or ".." in Path(clean).parts:
            raise AnalysisValidationError("Dataset paths must be safe relative paths under an approved data root.")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM analysis_storage_locations WHERE id = ? AND enabled = 1",
                (storage_location_id,),
            ).fetchone()
        if row is None:
            raise AnalysisValidationError("Approved analysis storage location not found.")
        root = Path(str(row["root_path"])).resolve()
        path = (root / clean).resolve()
        if not _is_within(path, root):
            raise AnalysisValidationError("Dataset path escapes the approved data root.")
        return path, clean

    def _job_for_worker(self, worker_id: str, job_id: str) -> sqlite3.Row:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM analysis_jobs WHERE id = ? AND worker_id = ?",
                (job_id, worker_id),
            ).fetchone()
        if row is None:
            raise AnalysisValidationError("Claimed analysis job not found.")
        return row

    def _audit(self, actor_id: str, action: str, target_id: str | None, metadata: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO analysis_audit_log (id, actor_id, action, target_id, metadata_json) VALUES (?, ?, ?, ?, ?)",
                (f"analysis-audit:{uuid.uuid4().hex[:16]}", actor_id, action, target_id, json.dumps(metadata)),
            )

    def _worker_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        status = str(row["status"] or "offline")
        connected = _is_fresh_heartbeat(str(row["last_heartbeat"]))
        if not connected and status not in {"maintenance"}:
            status = "offline"
        return dict(row) | {
            "enabled": bool(row["enabled"]),
            "connected": connected,
            "status": status,
            "status_label": status.replace("_", " ").title(),
            "gpu_inventory": json.loads(row["gpu_inventory_json"] or "[]"),
            "supported_runtimes": json.loads(row["supported_runtimes_json"] or "[]"),
            "supported_workflows": json.loads(row["supported_workflows_json"] or "[]"),
            "software_versions": json.loads(row["software_versions_json"] or "{}"),
        }

    def _dataset_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["metadata_summary"] = json.loads(row["metadata_summary_json"] or "{}")
        payload["access"] = json.loads(row["access_json"] or "{}")
        payload["server_local"] = True
        return payload

    def _workflow_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        stable_key = str(row["stable_key"])
        status = "installed" if stable_key == "bulk_rnaseq_validation_qc" else "available"
        return dict(row) | {
            "parameter_schema": json.loads(row["parameter_schema_json"] or "{}"),
            "resource_request": json.loads(row["resource_request_json"] or "{}"),
            "supported_runtimes": json.loads(row["supported_runtimes_json"] or "[]"),
            "enabled": bool(row["enabled"]),
            "status": status,
            "installed": status == "installed",
        }

    def _job_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        return dict(row) | {
            "parameters": json.loads(row["parameters_json"] or "{}"),
            "resource_request": json.loads(row["resource_request_json"] or "{}"),
            "reproducibility_manifest": json.loads(row["reproducibility_manifest_json"] or "{}"),
            "cancellation_requested": bool(row["cancellation_requested"]),
        }

    def _output_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        return dict(row) | {
            "structured": json.loads(row["structured_json"] or "{}"),
            "viewer_config": json.loads(row["viewer_config_json"] or "{}"),
            "provenance": json.loads(row["provenance_json"] or "{}"),
        }

    def _output_context(self, user_id: str, output: dict[str, Any]) -> dict[str, Any]:
        try:
            job = self.get_job(user_id, str(output["job_id"]))
            dataset = self.get_dataset(user_id, str(output["dataset_id"]))
        except AnalysisValidationError:
            return {"job": None, "dataset": None, "references": []}
        return {
            "job": job,
            "dataset": dataset,
            "references": self._references_for_output_unchecked(user_id, str(output["id"])),
        }


def _resolve_data_dir(data_dir: str) -> Path:
    path = Path(data_dir)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    if any(str(row["name"]) == column for row in rows):
        return
    connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _safe_unlink(path: Path, root: Path) -> None:
    resolved = path.resolve()
    if not _is_within(resolved, root.resolve()):
        return
    try:
        if resolved.is_file():
            resolved.unlink()
    except FileNotFoundError:
        return


def _analysis_roots(data_dir: Path, default_root: Path) -> list[Path]:
    raw = os.environ.get("MUNDI_ANALYSIS_DATA_ROOTS", "")
    roots = [item.strip() for item in raw.split(",") if item.strip()]
    result = []
    for item in roots:
        path = Path(item)
        if not path.is_absolute():
            path = data_dir / path
        path.mkdir(parents=True, exist_ok=True)
        result.append(path.resolve())
    if not result:
        default_root.mkdir(parents=True, exist_ok=True)
        result.append(default_root.resolve())
    return result


def _clean_required(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise AnalysisValidationError(f"{label} is required.")
    return text


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bounded_progress(value: object) -> float:
    try:
        progress = float(value)
    except (TypeError, ValueError) as exc:
        raise AnalysisValidationError("Invalid job progress.") from exc
    if progress < 0 or progress > 1:
        raise AnalysisValidationError("Job progress must be between 0 and 1.")
    return progress


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _display_root(path: object) -> str:
    return Path(str(path)).name or "Approved data root"


def _is_fresh_heartbeat(value: str) -> bool:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - timestamp < timedelta(seconds=90)


def _dataset_candidate(path: Path) -> dict[str, Any] | None:
    if path.is_dir():
        names = {child.name.lower() for child in path.iterdir() if not child.name.startswith(".")}
        if "filtered_feature_bc_matrix" in names or "matrix.mtx" in names:
            return {"modality": "single_cell_rna_seq", "source_type": "10x_or_matrix_market"}
        if {"counts.tsv", "samples.csv"}.issubset(names) or {"counts.csv", "samples.csv"}.issubset(names):
            return {"modality": "bulk_rna_seq", "source_type": "bulk_count_matrix"}
        return None
    suffix = path.suffix.lower()
    if suffix in {".h5ad", ".h5", ".loom", ".rds"}:
        return {"modality": "single_cell_rna_seq", "source_type": suffix.removeprefix(".")}
    if suffix in {".csv", ".tsv"}:
        return {"modality": "bulk_rna_seq", "source_type": "table"}
    return None


def _fingerprint_paths(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        stat = path.stat()
        digest.update(str(path.name).encode())
        digest.update(str(stat.st_size).encode())
        digest.update(str(int(stat.st_mtime)).encode())
    return digest.hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_table(path: Path) -> list[dict[str, str]]:
    delimiter = "\t" if path.suffix.lower() in {".tsv", ".txt"} else ","
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        return [{key: value for key, value in row.items()} for row in reader]


def _peek_bulk_dataset(counts_path: Path, metadata_path: Path) -> dict[str, Any]:
    delimiter = "\t" if counts_path.suffix.lower() in {".tsv", ".txt"} else ","
    with counts_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        header = next(reader, [])
        feature_count = sum(1 for _ in reader)
    metadata_rows = _read_table(metadata_path)
    return {
        "sample_count": max(len(header) - 1, 0),
        "feature_count": feature_count,
        "metadata_rows": len(metadata_rows),
        "metadata_columns": list(metadata_rows[0].keys()) if metadata_rows else [],
        "counts_filename": counts_path.name,
        "metadata_filename": metadata_path.name,
    }


def _bulk_validation_report(counts_path: Path, metadata_path: Path, *, sample_id_column: str, group_column: str) -> dict[str, Any]:
    delimiter = "\t" if counts_path.suffix.lower() in {".tsv", ".txt"} else ","
    with counts_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        header = next(reader, [])
        if len(header) < 2:
            raise AnalysisValidationError("Count matrix must include a feature column and at least one sample column.")
        samples = [item.strip() for item in header[1:]]
        library_sizes = {sample: 0 for sample in samples}
        detected_genes = {sample: 0 for sample in samples}
        genes: list[str] = []
        non_integer_values = 0
        for row in reader:
            if not row:
                continue
            gene = row[0].strip()
            genes.append(gene)
            values = row[1:]
            for index, sample in enumerate(samples):
                value_text = values[index].strip() if index < len(values) else ""
                try:
                    value = int(value_text)
                except ValueError:
                    non_integer_values += 1
                    continue
                library_sizes[sample] += value
                if value > 0:
                    detected_genes[sample] += 1
    metadata_rows = _read_table(metadata_path)
    metadata_samples = [str(row.get(sample_id_column) or "").strip() for row in metadata_rows]
    duplicate_genes = sorted({gene for gene in genes if genes.count(gene) > 1 and gene})
    missing_metadata = sorted(set(samples) - set(metadata_samples))
    metadata_without_counts = sorted(set(metadata_samples) - set(samples))
    groups: dict[str, int] = {}
    if group_column:
        for row in metadata_rows:
            group = str(row.get(group_column) or "Unspecified").strip() or "Unspecified"
            groups[group] = groups.get(group, 0) + 1
    sample_qc = [
        {
            "sample": sample,
            "library_size": library_sizes[sample],
            "detected_genes": detected_genes[sample],
        }
        for sample in samples
    ]
    library_values = [row["library_size"] for row in sample_qc]
    flags = []
    if missing_metadata:
        flags.append("Some count-matrix samples are missing metadata.")
    if metadata_without_counts:
        flags.append("Some metadata rows do not have matching count-matrix samples.")
    if non_integer_values:
        flags.append("The count matrix contains non-integer values.")
    if duplicate_genes:
        flags.append("Duplicate gene identifiers were detected.")
    return {
        "summary": {
            "sample_count": len(samples),
            "feature_count": len(genes),
            "metadata_rows": len(metadata_rows),
            "integer_counts_valid": non_integer_values == 0,
            "sample_names_match": not missing_metadata and not metadata_without_counts,
            "duplicate_gene_count": len(duplicate_genes),
            "library_size_min": min(library_values) if library_values else 0,
            "library_size_max": max(library_values) if library_values else 0,
            "library_size_median": statistics.median(library_values) if library_values else 0,
        },
        "sample_qc": sample_qc,
        "group_sizes": groups,
        "duplicate_genes": duplicate_genes[:100],
        "missing_metadata_samples": missing_metadata,
        "metadata_without_counts": metadata_without_counts,
        "flags": flags,
        "source": {
            "counts_filename": counts_path.name,
            "metadata_filename": metadata_path.name,
            "sample_id_column": sample_id_column,
            "group_column": group_column,
        },
    }


def _sanitize_log_line(line: object) -> str:
    text = str(line)
    token = os.environ.get("MUNDI_COMPUTE_WORKER_TOKEN", "")
    if token:
        text = text.replace(token, "[redacted]")
    return text[:1000]


def _demo_datasets() -> list[dict[str, Any]]:
    return [
        {
            "display_name": "GFP Fluorescence",
            "modality": "imaging",
            "description": "Small fluorescence image demo for preview and notebook linking.",
            "source": "Mundi generated demo",
            "organism": "human",
            "expected_analyses": ["Generate Preview"],
            "recommended_workflows": ["generate_preview"],
            "estimated_runtime": "under 1 minute",
        },
        {
            "display_name": "DAPI",
            "modality": "imaging",
            "description": "Single-channel nuclear stain demo.",
            "source": "Mundi generated demo",
            "organism": "human",
            "expected_analyses": ["Generate Preview"],
            "recommended_workflows": ["generate_preview"],
            "estimated_runtime": "under 1 minute",
        },
        {
            "display_name": "Multi-channel TIFF",
            "modality": "imaging",
            "description": "Small multi-channel TIFF demo placeholder.",
            "source": "Mundi generated demo",
            "organism": "human",
            "expected_analyses": ["Preview", "Channel display"],
            "recommended_workflows": ["generate_preview"],
            "estimated_runtime": "under 1 minute",
        },
        {
            "display_name": "Small Retina Bulk",
            "modality": "bulk_rna_seq",
            "description": "Tiny retinal-organoid bulk RNA-seq matrix for validation/QC.",
            "source": "Mundi generated demo",
            "organism": "human",
            "counts_path": "demo/bulk/small_retina_bulk_counts.tsv",
            "metadata_path": "demo/bulk/small_retina_bulk_samples.csv",
            "expected_analyses": ["Dataset Validation/QC"],
            "recommended_workflows": ["bulk_rnaseq_validation_qc"],
            "estimated_runtime": "under 1 minute",
        },
        {
            "display_name": "Small PBMC Bulk",
            "modality": "bulk_rna_seq",
            "description": "Tiny PBMC bulk RNA-seq matrix for validation/QC.",
            "source": "Mundi generated demo",
            "organism": "human",
            "counts_path": "demo/bulk/small_pbmc_bulk_counts.tsv",
            "metadata_path": "demo/bulk/small_pbmc_bulk_samples.csv",
            "expected_analyses": ["Dataset Validation/QC"],
            "recommended_workflows": ["bulk_rnaseq_validation_qc"],
            "estimated_runtime": "under 1 minute",
        },
        {
            "display_name": "PBMC 3k",
            "modality": "single_cell_rna_seq",
            "description": "Single-cell demo catalog record prepared for future Scanpy/Seurat workflows.",
            "source": "10x public demo reference",
            "organism": "human",
            "expected_analyses": ["QC", "UMAP", "Marker detection"],
            "recommended_workflows": ["scanpy_standard_pipeline"],
            "estimated_runtime": "future workflow",
        },
        {
            "display_name": "PBMC 10k",
            "modality": "single_cell_rna_seq",
            "description": "Larger single-cell demo catalog record.",
            "source": "10x public demo reference",
            "organism": "human",
            "expected_analyses": ["QC", "UMAP", "Marker detection"],
            "recommended_workflows": ["scanpy_standard_pipeline"],
            "estimated_runtime": "future workflow",
        },
        {
            "display_name": "Retina Organoid Demo",
            "modality": "single_cell_rna_seq",
            "description": "Retinal-organoid single-cell demo catalog record.",
            "source": "Mundi demo reference",
            "organism": "human",
            "expected_analyses": ["QC", "UMAP", "Cell-type markers"],
            "recommended_workflows": ["scanpy_standard_pipeline"],
            "estimated_runtime": "future workflow",
        },
        {
            "display_name": "Scanpy Demo",
            "modality": "single_cell_rna_seq",
            "description": "Prepared demonstration entry for Scanpy workflow testing.",
            "source": "Mundi demo reference",
            "organism": "human",
            "expected_analyses": ["Scanpy standard pipeline"],
            "recommended_workflows": ["scanpy_standard_pipeline"],
            "estimated_runtime": "future workflow",
        },
        {
            "display_name": "Seurat Demo",
            "modality": "single_cell_rna_seq",
            "description": "Prepared demonstration entry for Seurat workflow testing.",
            "source": "Mundi demo reference",
            "organism": "human",
            "expected_analyses": ["Seurat standard pipeline"],
            "recommended_workflows": ["seurat_standard_pipeline"],
            "estimated_runtime": "future workflow",
        },
        {
            "display_name": "beta-VAE Demo",
            "modality": "machine_learning",
            "description": "Expression-matrix model demo prepared for future beta-VAE execution.",
            "source": "Mundi generated demo",
            "organism": "human",
            "expected_analyses": ["Latent-space visualization"],
            "recommended_workflows": ["beta_vae_expression_model"],
            "estimated_runtime": "future workflow",
        },
    ]


def _demo_workspace_payload() -> dict[str, Any]:
    return {
        "display_name": "Demo Workspace",
        "description": "Notebook, protocols, images, RNA datasets, and example analysis records for regression testing.",
        "contains": ["notebook", "protocols", "images", "rna_datasets", "example_analyses"],
    }


def _write_demo_bulk_files(bulk_dir: Path) -> None:
    _write_counts_and_samples(
        bulk_dir / "small_retina_bulk_counts.tsv",
        bulk_dir / "small_retina_bulk_samples.csv",
        genes=[
            ("BMP4", [10, 28, 31]),
            ("POU4F2", [2, 9, 8]),
            ("RBPMS", [3, 12, 11]),
            ("GAPDH", [100, 110, 115]),
        ],
        samples=[("DMSO_1", "DMSO"), ("SAG_1", "SAG"), ("SAG_2", "SAG")],
    )
    _write_counts_and_samples(
        bulk_dir / "small_pbmc_bulk_counts.tsv",
        bulk_dir / "small_pbmc_bulk_samples.csv",
        genes=[
            ("MS4A1", [42, 39, 3]),
            ("CD3D", [5, 6, 57]),
            ("LYZ", [10, 12, 45]),
            ("ACTB", [120, 118, 130]),
        ],
        samples=[("Bcell_1", "B_cell"), ("Bcell_2", "B_cell"), ("Tcell_1", "T_cell")],
    )


def _write_counts_and_samples(
    counts_path: Path,
    samples_path: Path,
    *,
    genes: list[tuple[str, list[int]]],
    samples: list[tuple[str, str]],
) -> None:
    if not counts_path.exists():
        with counts_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t")
            writer.writerow(["gene", *[sample for sample, _group in samples]])
            for gene, values in genes:
                writer.writerow([gene, *values])
    if not samples_path.exists():
        with samples_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["sample", "condition"])
            writer.writeheader()
            for sample, group in samples:
                writer.writerow({"sample": sample, "condition": group})
