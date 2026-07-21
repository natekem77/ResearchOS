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
from datetime import datetime, timezone
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

    def list_datasets(self, user_id: str, modality: str | None = None) -> list[dict[str, Any]]:
        where = "WHERE user_id = ?"
        params: list[Any] = [user_id]
        if modality:
            where += " AND modality = ?"
            params.append(modality)
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

    def list_workflows(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
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
        return self._output_payload(row)

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
        connection.execute(
            """
            INSERT INTO analysis_outputs
                (id, job_id, dataset_id, output_type, display_name, storage_uri, mime_type,
                 size_bytes, structured_json, viewer_config_json, provenance_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?)
            """,
            (
                f"analysis-output:{uuid.uuid4().hex[:16]}",
                job_id,
                dataset_id,
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
        return dict(row) | {
            "enabled": bool(row["enabled"]),
            "connected": True,
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
        return dict(row) | {
            "parameter_schema": json.loads(row["parameter_schema_json"] or "{}"),
            "resource_request": json.loads(row["resource_request_json"] or "{}"),
            "supported_runtimes": json.loads(row["supported_runtimes_json"] or "[]"),
            "enabled": bool(row["enabled"]),
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


def _resolve_data_dir(data_dir: str) -> Path:
    path = Path(data_dir)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


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
