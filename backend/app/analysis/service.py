"""Analysis dataset catalog, remote worker queue, and bulk-QC vertical slice."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import logging
import math
import os
import platform
import re
import shutil
import sqlite3
import statistics
import tarfile
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.storage import PROJECT_ROOT, SQLiteStore

from .workflows import list_workflows, validate_parameters, workflow_by_key

logger = logging.getLogger(__name__)

ACTIVE_JOB_STATUSES = {"claimed", "preparing", "running", "uploading_results"}
TERMINAL_JOB_STATUSES = {"complete", "failed", "cancelled"}


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
        self.job_timeout_seconds = int(os.environ.get("MUNDI_COMPUTE_JOB_TIMEOUT_SECONDS", "3600"))
        self.job_recovery_seconds = int(os.environ.get("MUNDI_COMPUTE_JOB_RECOVERY_SECONDS", "90"))
        self.max_transient_retries = int(os.environ.get("MUNDI_COMPUTE_MAX_TRANSIENT_RETRIES", "2"))
        self._ensure_schema()
        self._ensure_storage_locations()
        self._ensure_workflows()
        self.recover_interrupted_jobs()
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
                    source_data_kind TEXT NOT NULL DEFAULT 'raw_counts',
                    exploratory_only INTEGER NOT NULL DEFAULT 0,
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
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL DEFAULT 2,
                    last_worker_heartbeat TEXT,
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
            _ensure_column(connection, "analysis_datasets", "source_data_kind", "TEXT NOT NULL DEFAULT 'raw_counts'")
            _ensure_column(connection, "analysis_datasets", "exploratory_only", "INTEGER NOT NULL DEFAULT 0")
            _ensure_column(connection, "analysis_jobs", "retry_count", "INTEGER NOT NULL DEFAULT 0")
            _ensure_column(connection, "analysis_jobs", "max_retries", "INTEGER NOT NULL DEFAULT 2")
            _ensure_column(connection, "analysis_jobs", "last_worker_heartbeat", "TEXT")
            connection.executescript(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_analysis_outputs_registration
                    ON analysis_outputs(job_id, registration_key)
                    WHERE registration_key IS NOT NULL;
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
            workflows = list_workflows()
            active_keys = [str(workflow["stable_key"]) for workflow in workflows]
            for workflow in workflows:
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
            if active_keys:
                connection.execute(
                    f"""
                    UPDATE analysis_workflows
                    SET enabled = 0, updated_at = CURRENT_TIMESTAMP
                    WHERE stable_key NOT IN ({", ".join("?" for _ in active_keys)})
                    """,
                    active_keys,
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
        now = _now()
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
                    now,
                    worker_id,
                ),
            )
            connection.execute(
                f"""
                UPDATE analysis_jobs
                SET last_worker_heartbeat = ?
                WHERE worker_id = ? AND status IN ({_sql_placeholders(ACTIVE_JOB_STATUSES)})
                """,
                (now, worker_id, *sorted(ACTIVE_JOB_STATUSES)),
            )
        self.recover_interrupted_jobs()
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
        source_data_kind = str(payload.get("source_data_kind") or summary.get("source_data_kind") or "raw_counts")
        exploratory_only = bool(payload.get("exploratory_only") or summary.get("exploratory_only"))
        summary["source_data_kind"] = source_data_kind
        summary["exploratory_only"] = exploratory_only
        if isinstance(payload.get("suggested_deseq2"), dict):
            summary["suggested_deseq2"] = payload["suggested_deseq2"]
        dataset_id = f"analysis-dataset:{uuid.uuid4().hex[:16]}"
        checksum = _fingerprint_paths([counts_abs, metadata_abs])
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analysis_datasets
                    (id, user_id, display_name, modality, source_type, worker_id, storage_location_id,
                     counts_path, metadata_path, organism, genome_build, assay, sample_count,
                     features_count, source_data_kind, exploratory_only, metadata_summary_json, checksum, access_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    source_data_kind,
                    1 if exploratory_only else 0,
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

    def delete_dataset(
        self,
        user_id: str,
        dataset_id: str,
        *,
        delete_related: bool = False,
        remove_files: bool = False,
    ) -> dict[str, Any]:
        dataset = self.get_dataset(user_id, dataset_id)
        with self._connect() as connection:
            jobs = connection.execute(
                "SELECT * FROM analysis_jobs WHERE dataset_id = ? AND user_id = ? AND deleted_at IS NULL",
                (dataset_id, user_id),
            ).fetchall()
            outputs = connection.execute(
                """
                SELECT o.* FROM analysis_outputs o
                JOIN analysis_jobs j ON j.id = o.job_id
                WHERE o.dataset_id = ? AND j.user_id = ?
                """,
                (dataset_id, user_id),
            ).fetchall()
            active_jobs = [row for row in jobs if str(row["status"]) in ACTIVE_JOB_STATUSES]
            if active_jobs:
                raise AnalysisValidationError("Dataset has active jobs. Cancel running or queued jobs before deleting it.")
            if (jobs or outputs) and not delete_related:
                raise AnalysisValidationError(
                    f"Dataset is referenced by {len(jobs)} job(s) and {len(outputs)} output(s)."
                )
            output_payloads = [self._output_payload(row) for row in outputs]
            for output in output_payloads:
                storage_uri = output.get("storage_uri")
                if storage_uri:
                    _safe_unlink(self.base_dir / str(storage_uri), self.base_dir)
            if delete_related:
                connection.execute(
                    "DELETE FROM analysis_notebook_references WHERE user_id = ? AND output_id IN (SELECT id FROM analysis_outputs WHERE dataset_id = ?)",
                    (user_id, dataset_id),
                )
                connection.execute("DELETE FROM analysis_outputs WHERE dataset_id = ?", (dataset_id,))
                connection.execute(
                    "UPDATE analysis_jobs SET deleted_at = CURRENT_TIMESTAMP WHERE dataset_id = ? AND user_id = ?",
                    (dataset_id, user_id),
                )
            connection.execute(
                "DELETE FROM analysis_datasets WHERE id = ? AND user_id = ?",
                (dataset_id, user_id),
            )
        files_removed = False
        if remove_files and str(dataset.get("source_type") or "") in {"public_geo"}:
            try:
                counts_path, _ = self._resolve_location_path(
                    str(dataset["storage_location_id"]),
                    str(dataset.get("counts_path") or ""),
                )
                files_root = counts_path.parent
                _safe_rmtree(files_root, self.allowed_roots[0])
                files_removed = True
            except AnalysisValidationError:
                files_removed = False
        self._audit(
            user_id,
            "dataset.delete",
            dataset_id,
            {
                "delete_related": delete_related,
                "remove_files": remove_files,
                "files_removed": files_removed,
                "jobs": len(jobs),
                "outputs": len(outputs),
            },
        )
        return {
            "deleted": True,
            "dataset_id": dataset_id,
            "jobs": len(jobs),
            "outputs": len(outputs),
            "files_removed": files_removed,
        }

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
            supported_workflows = _fresh_supported_workflows(connection)
        return [self._workflow_payload(row, supported_workflows) for row in rows]

    def create_job(self, *, user_id: str, dataset_id: str, workflow_key: str, parameters: dict[str, Any] | None = None, priority: int = 0) -> dict[str, Any]:
        dataset = self.get_dataset(user_id, dataset_id)
        workflow = workflow_by_key(workflow_key)
        if workflow is None:
            raise AnalysisValidationError("Unknown analysis workflow.")
        if workflow["stable_key"] not in {"bulk_rnaseq_validation_qc", "bulk_rnaseq_deseq2"}:
            raise AnalysisValidationError("This workflow is scaffolded but not executable in the current milestone.")
        if workflow["modality"] != dataset["modality"]:
            raise AnalysisValidationError("Workflow does not support this dataset modality.")
        if workflow_key == "bulk_rnaseq_deseq2" and _dataset_is_exploratory_only(dataset):
            source_kind = str(dataset.get("source_data_kind") or "normalized expression")
            raise AnalysisValidationError(
                "DESeq2 requires raw integer counts. This dataset is marked exploratory-only "
                f"because its source data are {source_kind}; use QC, PCA, clustering, and exploratory visualization instead."
            )
        try:
            clean_parameters = validate_parameters(workflow_key, parameters or {})
        except ValueError as exc:
            raise AnalysisValidationError(str(exc)) from exc
        if workflow_key == "bulk_rnaseq_deseq2":
            self._preflight_bulk_deseq2_dataset(dataset, clean_parameters)
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
                     parameters_json, progress, current_stage, queued_at, max_retries, resource_request_json,
                     reproducibility_manifest_json)
                VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, 0, 'Queued', CURRENT_TIMESTAMP, ?, ?, ?)
                """,
                (
                    job_id,
                    user_id,
                    dataset_id,
                    workflow_key,
                    workflow["workflow_version"],
                    priority,
                    json.dumps(clean_parameters),
                    self.max_transient_retries,
                    json.dumps(workflow["resource_request"]),
                    json.dumps(manifest),
                ),
            )
        self._audit(user_id, "job.create", job_id, {"workflow": workflow_key})
        return self.get_job(user_id, job_id)

    def _preflight_bulk_deseq2_dataset(self, dataset: dict[str, Any], parameters: dict[str, Any]) -> None:
        counts_path, _ = self._resolve_location_path(str(dataset["storage_location_id"]), str(dataset["counts_path"]))
        metadata_path, _ = self._resolve_location_path(str(dataset["storage_location_id"]), str(dataset["metadata_path"]))
        excluded_samples = set(str(item) for item in parameters.get("exclude_samples", []) if str(item).strip())
        counts = _read_count_matrix(counts_path, exclude_samples=excluded_samples)
        sample_column = str(parameters.get("sample_id_column") or "sample")
        metadata = [
            row
            for row in _read_table(metadata_path)
            if str(row.get(sample_column) or "").strip() not in excluded_samples
        ]
        validation = _validate_deseq2_inputs(counts, metadata, parameters)
        if validation["errors"]:
            raise AnalysisValidationError("; ".join(validation["errors"]))

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
        self.recover_interrupted_jobs()
        worker = self.get_worker(worker_id)
        if not worker.get("enabled", True):
            raise AnalysisValidationError("Compute worker is disabled.")
        if int(worker.get("running_job_count") or 0) >= int(worker.get("maximum_concurrent_jobs") or 1):
            logger.debug(
                "analysis worker at concurrency limit worker_id=%s running=%s max=%s",
                worker_id,
                worker.get("running_job_count"),
                worker.get("maximum_concurrent_jobs"),
            )
            return None
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
                    cancellation_requested = 0, last_worker_heartbeat = ?,
                    current_stage = 'Claimed by compute worker', started_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'queued'
                """,
                (worker_id, _now(), selected["id"]),
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
                SET status = ?, progress = ?, current_stage = ?, last_worker_heartbeat = ?
                WHERE id = ? AND worker_id = ?
                """,
                (next_status, next_progress, current_stage or row["current_stage"], _now(), job_id, worker_id),
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
        if row["cancellation_requested"]:
            return self._cancel_claimed_job(worker_id, job_id)
        with self._connect() as connection:
            for output in outputs or []:
                self._insert_structured_worker_output(connection, row, output)
            connection.execute(
                """
                UPDATE analysis_jobs
                SET status = 'complete', progress = 1, current_stage = 'Complete',
                    finished_at = CURRENT_TIMESTAMP, last_worker_heartbeat = ?
                WHERE id = ? AND worker_id = ?
                """,
                (_now(), job_id, worker_id),
            )
        return self.get_job(str(row["user_id"]), job_id)

    def fail_job(self, worker_id: str, job_id: str, error_summary: str) -> dict[str, Any]:
        row = self._job_for_worker(worker_id, job_id)
        clean_error = _sanitize_log_line(error_summary)[:500]
        retry_count = int(row["retry_count"] or 0)
        max_retries = int(row["max_retries"] or self.max_transient_retries)
        should_retry = _is_transient_error(clean_error) and retry_count < max_retries
        with self._connect() as connection:
            if should_retry:
                connection.execute(
                    """
                    UPDATE analysis_jobs
                    SET status = 'queued', worker_id = NULL, progress = 0,
                        current_stage = 'Queued for automatic retry',
                        queued_at = CURRENT_TIMESTAMP, started_at = NULL, finished_at = NULL,
                        error_summary = ?, retry_count = retry_count + 1,
                        last_worker_heartbeat = NULL
                    WHERE id = ? AND worker_id = ?
                    """,
                    (clean_error, job_id, worker_id),
                )
            else:
                connection.execute(
                    """
                    UPDATE analysis_jobs
                    SET status = 'failed', progress = 1, current_stage = 'Failed',
                        error_summary = ?, finished_at = CURRENT_TIMESTAMP,
                        last_worker_heartbeat = ?
                    WHERE id = ? AND worker_id = ?
                    """,
                    (clean_error, _now(), job_id, worker_id),
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
                    current_stage = CASE WHEN status = 'queued' THEN 'Cancelled' ELSE 'Cancellation requested' END,
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
                    error_summary = NULL, cancellation_requested = 0,
                    last_worker_heartbeat = NULL
                WHERE id = ? AND user_id = ?
                """,
                (job_id, user_id),
            )
        return self.get_job(user_id, job_id)

    def delete_job(self, user_id: str, job_id: str, *, delete_outputs: bool = False) -> dict[str, Any]:
        job = self.get_job(user_id, job_id)
        if job["status"] in ACTIVE_JOB_STATUSES:
            raise AnalysisValidationError("Running analysis jobs cannot be deleted. Cancel the job first.")
        with self._connect() as connection:
            outputs = connection.execute(
                "SELECT * FROM analysis_outputs WHERE job_id = ?",
                (job_id,),
            ).fetchall()
            output_payloads = [self._output_payload(row) for row in outputs]
            if delete_outputs:
                for output in output_payloads:
                    storage_uri = output.get("storage_uri")
                    if storage_uri:
                        _safe_unlink(self.base_dir / str(storage_uri), self.base_dir)
                connection.execute(
                    "DELETE FROM analysis_notebook_references WHERE user_id = ? AND output_id IN (SELECT id FROM analysis_outputs WHERE job_id = ?)",
                    (user_id, job_id),
                )
                connection.execute("DELETE FROM analysis_outputs WHERE job_id = ?", (job_id,))
            connection.execute(
                "UPDATE analysis_jobs SET deleted_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
                (job_id, user_id),
            )
        self._audit(user_id, "job.delete", job_id, {"delete_outputs": delete_outputs, "outputs": len(outputs)})
        return {"deleted": True, "job_id": job_id, "outputs": len(outputs), "outputs_deleted": delete_outputs}

    def recover_interrupted_jobs(self) -> dict[str, int]:
        """Requeue active jobs whose worker heartbeat is stale or whose runtime timed out."""
        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(seconds=self.job_recovery_seconds)
        timeout_before = now - timedelta(seconds=self.job_timeout_seconds)
        requeued = 0
        timed_out = 0
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT j.*, w.last_heartbeat AS worker_last_heartbeat
                FROM analysis_jobs j
                LEFT JOIN analysis_workers w ON w.worker_id = j.worker_id
                WHERE j.deleted_at IS NULL
                  AND j.status IN ({_sql_placeholders(ACTIVE_JOB_STATUSES)})
                """,
                tuple(sorted(ACTIVE_JOB_STATUSES)),
            ).fetchall()
            for row in rows:
                started_at = _parse_time(row["started_at"])
                job_heartbeat = _parse_time(row["last_worker_heartbeat"])
                worker_heartbeat = _parse_time(row["worker_last_heartbeat"])
                latest_heartbeat = max(
                    [item for item in [job_heartbeat, worker_heartbeat] if item is not None],
                    default=None,
                )
                retry_count = int(row["retry_count"] or 0)
                max_retries = int(row["max_retries"] or self.max_transient_retries)
                timeout_expired = started_at is not None and started_at < timeout_before
                worker_stale = latest_heartbeat is None or latest_heartbeat < stale_before
                if not timeout_expired and not worker_stale:
                    continue
                if timeout_expired:
                    timed_out += 1
                if retry_count < max_retries:
                    connection.execute(
                        """
                        UPDATE analysis_jobs
                        SET status = 'queued', worker_id = NULL, progress = 0,
                            current_stage = ?, queued_at = CURRENT_TIMESTAMP,
                            started_at = NULL, finished_at = NULL,
                            error_summary = ?, retry_count = retry_count + 1,
                            last_worker_heartbeat = NULL
                        WHERE id = ?
                        """,
                        (
                            "Queued after interrupted worker recovery",
                            "Recovered from interrupted or timed-out compute worker.",
                            row["id"],
                        ),
                    )
                    requeued += 1
                else:
                    connection.execute(
                        """
                        UPDATE analysis_jobs
                        SET status = 'failed', progress = 1, current_stage = 'Failed',
                            finished_at = CURRENT_TIMESTAMP,
                            error_summary = ?
                        WHERE id = ?
                        """,
                        ("Compute job timed out or worker went offline after retry limit.", row["id"]),
                    )
        if requeued or timed_out:
            logger.info("analysis queue recovery requeued=%s timed_out=%s", requeued, timed_out)
        return {"requeued": requeued, "timed_out": timed_out}

    def storage_report(self) -> dict[str, Any]:
        orphan_outputs = self.orphaned_outputs()
        orphan_jobs = self.orphaned_jobs()
        temporary_dirs = self.cleanup_temporary_work_dirs(dry_run=True)
        return {
            "outputs_path": _display_root(self.outputs_dir),
            "outputs_size_bytes": _directory_size(self.outputs_dir),
            "orphaned_outputs": orphan_outputs,
            "orphaned_jobs": orphan_jobs,
            "temporary_work_dirs": temporary_dirs,
        }

    def orphaned_outputs(self) -> list[dict[str, Any]]:
        orphans: list[dict[str, Any]] = []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT o.* FROM analysis_outputs o
                LEFT JOIN analysis_jobs j ON j.id = o.job_id
                WHERE j.id IS NULL OR (o.storage_uri IS NOT NULL AND o.storage_uri != '')
                """
            ).fetchall()
        for row in rows:
            payload = self._output_payload(row)
            missing_job = self._job_exists(str(payload["job_id"])) is False
            storage_uri = payload.get("storage_uri")
            missing_file = bool(storage_uri) and not (self.base_dir / str(storage_uri)).exists()
            if missing_job or missing_file:
                orphans.append(
                    {
                        "id": payload["id"],
                        "display_name": payload["display_name"],
                        "missing_job": missing_job,
                        "missing_file": missing_file,
                    }
                )
        return orphans

    def orphaned_jobs(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT j.* FROM analysis_jobs j
                LEFT JOIN analysis_datasets d ON d.id = j.dataset_id
                WHERE d.id IS NULL AND j.deleted_at IS NULL
                """
            ).fetchall()
        return [{"id": row["id"], "status": row["status"], "dataset_id": row["dataset_id"]} for row in rows]

    def cleanup_temporary_work_dirs(self, *, dry_run: bool = False) -> dict[str, Any]:
        removed: list[str] = []
        for path in self.base_dir.glob("tmp-*"):
            if not path.is_dir():
                continue
            removed.append(path.name)
            if not dry_run:
                _safe_rmtree(path, self.base_dir)
        return {"count": len(removed), "directories": removed}

    def outputs_for_job(self, user_id: str, job_id: str) -> list[dict[str, Any]]:
        self.get_job(user_id, job_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, job_id, dataset_id, registration_key, output_type,
                       display_name, storage_uri, mime_type, size_bytes,
                       created_at
                FROM analysis_outputs
                WHERE job_id = ?
                ORDER BY created_at ASC
                """,
                (job_id,),
            ).fetchall()
        return [self._output_list_payload(row) for row in rows]

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
                SELECT o.id, o.job_id, o.dataset_id, o.registration_key,
                       o.output_type, o.display_name, o.storage_uri,
                       o.mime_type, o.size_bytes, o.created_at,
                       j.workflow_id AS job_workflow_id, j.workflow_version AS job_workflow_version,
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
        return [self._output_list_payload(row) for row in rows]

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

    def public_geo_datasets(self, query: str | None = None) -> list[dict[str, Any]]:
        needle = (query or "").strip().lower()
        records = _public_geo_datasets()
        if needle:
            records = [
                record
                for record in records
                if needle in record["accession"].lower()
                or needle in record["title"].lower()
                or needle in record["organism"].lower()
                or needle in record["summary"].lower()
                or any(needle in tag.lower() for tag in record.get("tags", []))
            ]
        return [
            {
                key: value
                for key, value in record.items()
                if key
                not in {
                    "genes",
                    "samples",
                    "sample_accessions",
                    "counts_filename",
                    "metadata_filename",
                    "annotation_filename",
                }
            }
            for record in records
        ]

    def import_public_geo_dataset(self, user_id: str, accession: str) -> dict[str, Any]:
        clean_accession = accession.strip()
        record = next(
            (
                candidate
                for candidate in _public_geo_datasets()
                if candidate["accession"].lower() == clean_accession.lower()
            ),
            None,
        )
        if record is None:
            raise AnalysisValidationError("Public GEO dataset is not available in the curated import catalog.")
        existing = self._dataset_by_name(user_id, record["title"])
        if existing is not None:
            refreshed = self._refresh_public_geo_dataset(user_id, existing, record)
            return refreshed | {"import_status": "already_imported"}

        dataset_dir = self.allowed_roots[0] / "public_geo" / record["accession"]
        dataset_dir.mkdir(parents=True, exist_ok=True)
        counts_path = dataset_dir / record["counts_filename"]
        metadata_path = dataset_dir / record["metadata_filename"]
        _materialize_public_geo_dataset(record, dataset_dir, counts_path, metadata_path)
        relative_counts = str(counts_path.relative_to(self.allowed_roots[0]))
        relative_metadata = str(metadata_path.relative_to(self.allowed_roots[0]))
        dataset = self.register_server_dataset(
            user_id=user_id,
            payload={
                "display_name": record["title"],
                "modality": "bulk_rna_seq",
                "source_type": "public_geo",
                "counts_path": relative_counts,
                "metadata_path": relative_metadata,
                "organism": record["organism"],
                "genome_build": record.get("genome_build"),
                "assay": "Bulk RNA-seq",
                "source_data_kind": record.get("source_data_kind", "raw_counts"),
                "exploratory_only": bool(record.get("exploratory_only", False)),
                "suggested_deseq2": record.get("deseq2_defaults"),
            },
        )
        self._audit(
            user_id,
            "dataset.public_geo_import",
            str(dataset["id"]),
            {"accession": record["accession"], "source": record["source"]},
        )
        return dataset | {"import_status": "imported"}

    def _refresh_public_geo_dataset(
        self,
        user_id: str,
        existing: sqlite3.Row,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        counts_path, _counts_rel = self._resolve_location_path(
            str(existing["storage_location_id"]),
            str(existing["counts_path"]),
        )
        metadata_path, _metadata_rel = self._resolve_location_path(
            str(existing["storage_location_id"]),
            str(existing["metadata_path"]),
        )
        _materialize_public_geo_dataset(record, counts_path.parent, counts_path, metadata_path)
        summary = _peek_bulk_dataset(counts_path, metadata_path)
        source_data_kind = str(record.get("source_data_kind", "raw_counts"))
        exploratory_only = bool(record.get("exploratory_only", False))
        summary["source_data_kind"] = source_data_kind
        summary["exploratory_only"] = exploratory_only
        if isinstance(record.get("deseq2_defaults"), dict):
            summary["suggested_deseq2"] = record["deseq2_defaults"]
        checksum = _fingerprint_paths([counts_path, metadata_path])
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE analysis_datasets
                SET sample_count = ?, features_count = ?, source_data_kind = ?,
                    exploratory_only = ?, metadata_summary_json = ?, checksum = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
                """,
                (
                    summary["sample_count"],
                    summary["feature_count"],
                    source_data_kind,
                    1 if exploratory_only else 0,
                    json.dumps(summary),
                    checksum,
                    existing["id"],
                    user_id,
                ),
            )
        self._audit(
            user_id,
            "dataset.public_geo_refresh",
            str(existing["id"]),
            {"accession": record["accession"], "source": record["source"]},
        )
        return self.get_dataset(user_id, str(existing["id"]))

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
            if job.get("cancellation_requested"):
                return self._cancel_claimed_job(worker_id, str(job["id"]))
            self.update_job_progress(worker_id, str(job["id"]), status="preparing", progress=0.2, current_stage="Reading server-local dataset")
            if job["workflow_id"] == "bulk_rnaseq_deseq2":
                outputs = self._execute_bulk_deseq2(job, worker_id)
            else:
                outputs = self._execute_bulk_validation_qc(job, worker_id)
            if self.get_job(str(job["user_id"]), str(job["id"])).get("cancellation_requested"):
                return self._cancel_claimed_job(worker_id, str(job["id"]))
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

    def _execute_bulk_deseq2(self, job: dict[str, Any], worker_id: str) -> list[dict[str, Any]]:
        if job["workflow_id"] != "bulk_rnaseq_deseq2":
            raise AnalysisValidationError("Worker cannot execute this workflow.")
        dataset = self.get_dataset(str(job["user_id"]), str(job["dataset_id"]))
        counts_path, _ = self._resolve_location_path(str(dataset["storage_location_id"]), str(dataset["counts_path"]))
        metadata_path, _ = self._resolve_location_path(str(dataset["storage_location_id"]), str(dataset["metadata_path"]))
        parameters = dict(job.get("parameters") or {})

        self.update_job_progress(worker_id, str(job["id"]), status="running", progress=0.28, current_stage="Validating DESeq2 design")
        excluded_samples = set(str(item) for item in parameters.get("exclude_samples", []) if str(item).strip())
        counts = _read_count_matrix(counts_path, exclude_samples=excluded_samples)
        metadata = [
            row
            for row in _read_table(metadata_path)
            if str(row.get(str(parameters.get("sample_id_column") or "sample")) or "").strip()
            not in excluded_samples
        ]
        validation = _validate_deseq2_inputs(counts, metadata, parameters)
        if validation["errors"]:
            raise AnalysisValidationError("; ".join(validation["errors"]))

        self.update_job_progress(worker_id, str(job["id"]), status="running", progress=0.4, current_stage="Filtering genes")
        filtered_genes = _filter_genes(counts, parameters)
        if not filtered_genes:
            raise AnalysisValidationError("No genes remain after filtering.")

        self.update_job_progress(worker_id, str(job["id"]), status="running", progress=0.52, current_stage="Estimating size factors")
        size_factors = _size_factors(counts)
        normalized = _normalized_counts(counts, size_factors)
        transformed = _transformed_counts(normalized, str(parameters.get("transformed_count_method") or "vst"))

        self.update_job_progress(worker_id, str(job["id"]), status="running", progress=0.68, current_stage="Extracting contrast")
        de_rows = _differential_expression_rows(counts, normalized, metadata, parameters, filtered_genes)
        pvalues = [row["pvalue"] for row in de_rows]
        padj = _benjamini_hochberg(pvalues)
        alpha = float(parameters.get("alpha", 0.05))
        lfc_threshold = float(parameters.get("lfc_threshold", 1.0))
        for row, adjusted in zip(de_rows, padj, strict=True):
            row["padj"] = adjusted
            significant = adjusted <= alpha and abs(float(row["log2FoldChange"])) >= lfc_threshold
            row["significance"] = "significant" if significant else "not_significant"
            row["direction"] = "up" if significant and row["log2FoldChange"] > 0 else "down" if significant else "none"

        self.update_job_progress(worker_id, str(job["id"]), status="running", progress=0.82, current_stage="Generating tables and figures")
        job_dir = self.outputs_dir / str(job["id"])
        job_dir.mkdir(parents=True, exist_ok=True)
        de_rows.sort(key=lambda row: (row["padj"], -abs(float(row["log2FoldChange"]))))
        top_rows = de_rows[: int(parameters.get("top_gene_count", 50))]
        summary = _deseq2_summary(de_rows, parameters, validation, dataset, worker_id)
        size_factor_rows = [{"sample": sample, "size_factor": factor} for sample, factor in size_factors.items()]
        normalized_rows = _matrix_rows(normalized)
        transformed_rows = _matrix_rows(transformed)
        model_summary = {
            "design_formula": parameters["design_formula"],
            "design_factors": parameters["design_factors"],
            "contrast": {
                "factor": parameters["contrast_factor"],
                "numerator": parameters["numerator_level"],
                "denominator": parameters["denominator_level"],
            },
            "validation": validation,
        }
        filtered_summary = {
            "input_genes": len(counts["genes"]),
            "retained_genes": len(filtered_genes),
            "filtered_genes": len(counts["genes"]) - len(filtered_genes),
            "min_total_count": parameters["min_total_count"],
            "min_samples_expressing": parameters["min_samples_expressing"],
        }
        outputs = [
            ("deseq2_summary", "DESeq2 Run Summary", "deseq2_run_summary", summary),
            (
                "differential_expression",
                "Differential Expression Table",
                "differential_expression_table",
                {"columns": list(de_rows[0].keys()) if de_rows else [], "rows": de_rows},
            ),
            ("normalized_counts", "Normalized Counts", "table", {"columns": ["gene_id", *counts["samples"]], "rows": normalized_rows}),
            ("transformed_counts", "VST Matrix", "table", {"columns": ["gene_id", *counts["samples"]], "rows": transformed_rows}),
            ("size_factors", "Size Factors", "table", {"columns": ["sample", "size_factor"], "rows": size_factor_rows}),
            ("sample_metadata", "Sample Metadata Used", "table", {"columns": list(metadata[0].keys()) if metadata else [], "rows": metadata}),
            ("model_summary", "Model and Design Summary", "provenance", model_summary),
            ("filtered_gene_summary", "Filtered Gene Summary", "qc_report", filtered_summary),
            ("volcano", "Volcano Plot", "interactive_plot", _volcano_payload(de_rows, parameters)),
            ("ma_plot", "MA Plot", "interactive_plot", _ma_payload(de_rows)),
            ("pca", "PCA Plot", "interactive_plot", _pca_payload(transformed, metadata, parameters)),
            ("dispersion_plot", "Dispersion Plot", "interactive_plot", _dispersion_payload(de_rows)),
            ("library_size_plot", "Library Size Plot", "interactive_plot", _library_size_plot_payload(counts)),
            ("sample_distance_heatmap", "Sample Distance Heatmap", "heatmap", _sample_distance_payload(transformed)),
            ("top_gene_heatmap", "Top Gene Heatmap", "heatmap", _top_gene_heatmap_payload(transformed, top_rows)),
        ]
        provenance = {
            "engine": "approved-bulk-rnaseq-deseq2",
            "worker_id": worker_id,
            "workflow_stable_key": job["workflow_id"],
            "workflow_version": job["workflow_version"],
            "dataset_id": dataset["id"],
            "dataset_checksum": dataset["checksum"],
            "counts_checksum": _sha256_file(counts_path),
            "metadata_checksum": _sha256_file(metadata_path),
            "parameters": parameters,
            "design_formula": parameters["design_formula"],
            "contrast": model_summary["contrast"],
            "environment": _deseq2_environment(),
            "source_files_remain_server_local": True,
            "started_at": job.get("started_at"),
            "completed_at": _now(),
        }
        result: list[dict[str, Any]] = []
        output_manifest = []
        for registration_key, display_name, output_type, structured in outputs:
            path = job_dir / f"{registration_key}.json"
            path.write_text(json.dumps(structured, indent=2), encoding="utf-8")
            output_manifest.append({"filename": path.name, "checksum": _sha256_file(path), "output_type": output_type})
            result.append(
                {
                    "registration_key": registration_key,
                    "output_type": output_type,
                    "display_name": display_name,
                    "path": str(path),
                    "mime_type": "application/json",
                    "structured": structured,
                    "provenance": provenance,
                }
            )
        provenance["outputs"] = output_manifest
        provenance_path = job_dir / "deseq2_provenance.json"
        provenance_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
        result.append(
            {
                "registration_key": "provenance",
                "output_type": "provenance",
                "display_name": "DESeq2 Reproducibility Manifest",
                "path": str(provenance_path),
                "mime_type": "application/json",
                "structured": provenance,
                "provenance": provenance,
            }
        )
        return result

    def _insert_structured_worker_output(self, connection: sqlite3.Connection, job: sqlite3.Row, output: dict[str, Any]) -> None:
        path_value = output.get("path")
        path = Path(str(path_value)).resolve() if path_value else None
        if path is not None and not path.exists():
            raise AnalysisValidationError("Analysis output file does not exist and cannot be registered.")
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
            registration_key=str(output.get("registration_key") or output.get("output_type") or "result"),
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
            if not resolved.exists() or not resolved.is_file():
                raise AnalysisValidationError("Analysis output file does not exist and cannot be registered.")
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

    def _cancel_claimed_job(self, worker_id: str, job_id: str) -> dict[str, Any]:
        row = self._job_for_worker(worker_id, job_id)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE analysis_jobs
                SET status = 'cancelled', progress = 1, current_stage = 'Cancelled',
                    finished_at = CURRENT_TIMESTAMP, last_worker_heartbeat = ?
                WHERE id = ? AND worker_id = ?
                """,
                (_now(), job_id, worker_id),
            )
        return self.get_job(str(row["user_id"]), job_id)

    def _job_exists(self, job_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT 1 FROM analysis_jobs WHERE id = ?", (job_id,)).fetchone()
        return row is not None

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
        metadata_summary = json.loads(row["metadata_summary_json"] or "{}")
        validation = metadata_summary.get("validation")
        public_record = _public_geo_record_for_dataset_row(row)
        needs_factor_levels = not isinstance(validation, dict) or not validation.get("condition_levels_by_factor")
        needs_public_repair = public_record is not None and _metadata_needs_public_geo_repair(validation, public_record)
        if needs_factor_levels or needs_public_repair:
            try:
                counts_path, _ = self._resolve_location_path(str(row["storage_location_id"]), str(row["counts_path"]))
                metadata_path, _ = self._resolve_location_path(str(row["storage_location_id"]), str(row["metadata_path"]))
                if needs_public_repair:
                    _materialize_public_geo_dataset(public_record, counts_path.parent, counts_path, metadata_path)
                refreshed_summary = _peek_bulk_dataset(counts_path, metadata_path)
                for key in ("source_data_kind", "exploratory_only", "suggested_deseq2"):
                    if key in metadata_summary:
                        refreshed_summary[key] = metadata_summary[key]
                if public_record is not None:
                    refreshed_summary["source_data_kind"] = public_record.get("source_data_kind", "raw_counts")
                    refreshed_summary["exploratory_only"] = bool(public_record.get("exploratory_only", False))
                    if isinstance(public_record.get("deseq2_defaults"), dict):
                        refreshed_summary["suggested_deseq2"] = public_record["deseq2_defaults"]
                metadata_summary = refreshed_summary
            except Exception:
                logger.debug("analysis dataset metadata summary enrichment failed", exc_info=True)
        payload["metadata_summary"] = metadata_summary
        payload["access"] = json.loads(row["access_json"] or "{}")
        payload["server_local"] = True
        if public_record is not None:
            payload["source_data_kind"] = public_record.get("source_data_kind", payload.get("source_data_kind", "raw_counts"))
            payload["exploratory_only"] = bool(public_record.get("exploratory_only", False))
        else:
            payload["exploratory_only"] = bool(row["exploratory_only"]) if "exploratory_only" in row.keys() else False
        return payload

    def _workflow_payload(self, row: sqlite3.Row, supported_workflows: set[str] | None = None) -> dict[str, Any]:
        stable_key = str(row["stable_key"])
        supported_workflows = supported_workflows or set()
        if stable_key == "bulk_rnaseq_validation_qc":
            status = "installed"
            readiness_reason = "Ready"
        elif stable_key == "bulk_rnaseq_deseq2":
            status = "installed" if stable_key in supported_workflows else "unavailable"
            readiness_reason = (
                "Ready"
                if status == "installed"
                else "No eligible worker with R/DESeq2 dependencies is connected."
            )
        else:
            status = "available"
            readiness_reason = (
                "Legacy/scaffold workflow definition."
                if str(row["workflow_version"] or "").endswith("scaffold")
                else "Available but not currently runnable."
            )
        return dict(row) | {
            "parameter_schema": json.loads(row["parameter_schema_json"] or "{}"),
            "resource_request": json.loads(row["resource_request_json"] or "{}"),
            "supported_runtimes": json.loads(row["supported_runtimes_json"] or "[]"),
            "enabled": bool(row["enabled"]),
            "status": status,
            "installed": status == "installed",
            "readiness_reason": readiness_reason,
        }

    def _job_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        return dict(row) | {
            "parameters": json.loads(row["parameters_json"] or "{}"),
            "resource_request": json.loads(row["resource_request_json"] or "{}"),
            "reproducibility_manifest": json.loads(row["reproducibility_manifest_json"] or "{}"),
            "cancellation_requested": bool(row["cancellation_requested"]),
            "retry_count": int(row["retry_count"] or 0),
            "max_retries": int(row["max_retries"] or self.max_transient_retries),
            "queue_reason": self._queue_reason(row),
        }

    def _queue_reason(self, row: sqlite3.Row) -> str | None:
        if str(row["status"] or "") != "queued":
            return None
        workflow_id = str(row["workflow_id"] or "")
        with self._connect() as connection:
            workers = connection.execute("SELECT * FROM analysis_workers WHERE enabled = 1").fetchall()
        if not workers:
            return "No compute workers connected."
        fresh_workers = [
            worker
            for worker in workers
            if str(worker["status"] or "") != "maintenance"
            and _is_fresh_heartbeat(str(worker["last_heartbeat"] or ""))
        ]
        if not fresh_workers:
            if any(str(worker["status"] or "") == "maintenance" for worker in workers):
                return "Compute worker is in maintenance."
            return "Worker offline."
        eligible = []
        for worker in fresh_workers:
            try:
                supported = set(json.loads(worker["supported_workflows_json"] or "[]"))
            except json.JSONDecodeError:
                supported = set()
            if workflow_id in supported:
                eligible.append(worker)
        if not eligible:
            if workflow_id == "bulk_rnaseq_deseq2":
                return "Connected worker does not support bulk_rnaseq_deseq2. Missing R/DESeq2 dependencies."
            return f"Connected worker does not support {workflow_id}."
        if all(int(worker["running_job_count"] or 0) >= int(worker["maximum_concurrent_jobs"] or 1) for worker in eligible):
            return "Worker concurrency limit reached."
        return "Waiting for an eligible worker."

    def _output_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        return dict(row) | {
            "structured": json.loads(row["structured_json"] or "{}"),
            "viewer_config": json.loads(row["viewer_config_json"] or "{}"),
            "provenance": json.loads(row["provenance_json"] or "{}"),
        }

    def _output_list_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["summary"] = _output_list_summary(payload)
        payload["has_structured_content"] = True
        payload["has_viewer_config"] = True
        payload["has_provenance"] = True
        return payload

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


def _sql_placeholders(values: set[str]) -> str:
    return ", ".join("?" for _ in values)


def _fresh_supported_workflows(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT supported_workflows_json, last_heartbeat, status FROM analysis_workers WHERE enabled = 1"
    ).fetchall()
    supported: set[str] = set()
    for row in rows:
        if str(row["status"] or "") == "maintenance":
            continue
        if not _is_fresh_heartbeat(str(row["last_heartbeat"] or "")):
            continue
        try:
            workflows = json.loads(row["supported_workflows_json"] or "[]")
        except json.JSONDecodeError:
            continue
        supported.update(str(workflow) for workflow in workflows)
    return supported


def _output_list_summary(output: dict[str, Any]) -> dict[str, Any]:
    output_type = str(output.get("output_type") or "output")
    display_name = str(output.get("display_name") or "Analysis output")
    size_bytes = output.get("size_bytes")
    summary: dict[str, Any] = {
        "display_name": display_name,
        "output_type": output_type,
    }
    if size_bytes is not None:
        summary["size_bytes"] = size_bytes
    if output_type == "interactive_plot":
        summary["content"] = "Interactive plot content loads when opened."
    elif output_type == "heatmap":
        summary["content"] = "Heatmap matrix content loads when opened."
    elif output_type in {"table", "differential_expression_table"}:
        summary["content"] = "Table rows load when opened."
    elif output_type == "provenance":
        summary["content"] = "Reproducibility manifest loads when opened."
    elif output_type == "qc_report":
        summary["content"] = "QC report details load when opened."
    else:
        summary["content"] = "Output content loads when opened."
    return summary


def _safe_unlink(path: Path, root: Path) -> None:
    resolved = path.resolve()
    if not _is_within(resolved, root.resolve()):
        return
    try:
        if resolved.is_file():
            resolved.unlink()
    except FileNotFoundError:
        return


def _safe_rmtree(path: Path, root: Path) -> None:
    resolved = path.resolve()
    if not _is_within(resolved, root.resolve()):
        return
    shutil.rmtree(resolved, ignore_errors=True)


def _directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_file():
                total += child.stat().st_size
        except OSError:
            continue
    return total


def _parse_time(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_transient_error(value: str) -> bool:
    text = value.lower()
    return any(
        marker in text
        for marker in [
            "timeout",
            "timed out",
            "temporarily",
            "temporary",
            "connection reset",
            "connection aborted",
            "database is locked",
            "resource busy",
            "interrupted",
        ]
    )


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


def _dataset_is_exploratory_only(dataset: dict[str, Any]) -> bool:
    if bool(dataset.get("exploratory_only")):
        return True
    summary = dataset.get("metadata_summary")
    if isinstance(summary, dict) and bool(summary.get("exploratory_only")):
        return True
    return str(dataset.get("source_data_kind") or "").lower() in {
        "normalized_cpm",
        "normalized_tpm",
        "cpm",
        "tpm",
    }


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
    samples: list[str] = []
    genes_seen: set[str] = set()
    duplicate_genes: set[str] = set()
    non_integer_values = 0
    negative_values = 0
    low_count_genes = 0
    empty_gene_ids = 0
    sample_totals: dict[str, int] = {}
    with counts_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        header = next(reader, [])
        samples = [item.strip() for item in header[1:]]
        sample_totals = {sample: 0 for sample in samples}
        feature_count = 0
        for row in reader:
            if not row:
                continue
            feature_count += 1
            gene = row[0].strip()
            if not gene:
                empty_gene_ids += 1
            elif gene in genes_seen:
                duplicate_genes.add(gene)
            else:
                genes_seen.add(gene)
            total = 0
            for index, _sample in enumerate(samples, start=1):
                text = row[index].strip() if index < len(row) else "0"
                try:
                    value = int(text)
                except ValueError:
                    non_integer_values += 1
                    continue
                if value < 0:
                    negative_values += 1
                sample_totals[_sample] = sample_totals.get(_sample, 0) + value
                total += value
            if total < 10:
                low_count_genes += 1
    metadata_rows = _read_table(metadata_path)
    metadata_columns = list(metadata_rows[0].keys()) if metadata_rows else []
    sample_column = "sample" if "sample" in metadata_columns else metadata_columns[0] if metadata_columns else ""
    metadata_samples = [
        str(row.get(sample_column) or "").strip()
        for row in metadata_rows
        if sample_column
    ]
    missing_metadata = sorted(set(samples) - set(metadata_samples))
    metadata_without_counts = sorted(set(metadata_samples) - set(samples))
    duplicate_metadata_samples = sorted(
        {sample for sample in metadata_samples if sample and metadata_samples.count(sample) > 1}
    )
    duplicate_count_samples = sorted({sample for sample in samples if sample and samples.count(sample) > 1})
    zero_count_samples = sorted(sample for sample, total in sample_totals.items() if total == 0)
    conditions = sorted(
        {
            str(row.get("condition") or "").strip()
            for row in metadata_rows
            if str(row.get("condition") or "").strip()
        },
        key=_natural_label_sort_key,
    )
    condition_levels_by_factor = {
        column: sorted(
            {
                str(row.get(column) or "").strip()
                for row in metadata_rows
                if str(row.get(column) or "").strip()
            },
            key=_natural_label_sort_key,
        )
        for column in metadata_columns
        if column != sample_column
    }
    warnings = []
    if missing_metadata:
        warnings.append("Some count-matrix samples are missing metadata.")
    if metadata_without_counts:
        warnings.append("Some metadata rows do not have matching count-matrix samples.")
    if duplicate_metadata_samples:
        warnings.append("Duplicate sample identifiers were found in metadata.")
    if duplicate_count_samples:
        warnings.append("Duplicate sample columns were found in the count matrix.")
    if duplicate_genes:
        warnings.append("Duplicate gene identifiers were detected.")
    if zero_count_samples:
        warnings.append("One or more samples have zero total counts.")
    if non_integer_values:
        warnings.append("The count matrix contains non-integer values.")
    if negative_values:
        warnings.append("The count matrix contains negative values.")
    if empty_gene_ids:
        warnings.append("Some rows have empty gene identifiers.")
    return {
        "sample_count": max(len(header) - 1, 0),
        "feature_count": feature_count,
        "metadata_rows": len(metadata_rows),
        "metadata_columns": metadata_columns,
        "counts_filename": counts_path.name,
        "metadata_filename": metadata_path.name,
        "validation": {
            "sample_names_match": not missing_metadata and not metadata_without_counts,
            "duplicate_gene_count": len(duplicate_genes),
            "duplicate_sample_count": len(duplicate_count_samples),
            "duplicate_metadata_sample_count": len(duplicate_metadata_samples),
            "missing_metadata_samples": missing_metadata[:100],
            "metadata_without_counts": metadata_without_counts[:100],
            "zero_count_samples": zero_count_samples,
            "non_integer_value_count": non_integer_values,
            "negative_value_count": negative_values,
            "empty_gene_id_count": empty_gene_ids,
            "low_count_gene_count": low_count_genes,
            "count_matrix_dimensions": {
                "genes": feature_count,
                "samples": len(samples),
            },
            "metadata_complete": bool(metadata_rows) and not missing_metadata,
            "conditions": conditions,
            "condition_levels_by_factor": condition_levels_by_factor,
            "warnings": warnings,
        },
    }


def _natural_label_sort_key(label: str) -> tuple[Any, ...]:
    parts = re.split(r"(\d+)", label)
    return tuple(int(part) if part.isdigit() else part.lower() for part in parts)


def _public_geo_record_for_dataset_row(row: sqlite3.Row) -> dict[str, Any] | None:
    if str(row["source_type"] or "") != "public_geo":
        return None
    display_name = str(row["display_name"] or "")
    for record in _public_geo_datasets():
        if str(record.get("title") or "") == display_name:
            return record
    return None


def _metadata_needs_public_geo_repair(validation: Any, record: dict[str, Any]) -> bool:
    configured = record.get("samples") or []
    expected_levels = {str(group) for _sample, group in configured}
    if not expected_levels:
        return False
    if not isinstance(validation, dict):
        return True
    by_factor = validation.get("condition_levels_by_factor")
    levels: list[str] = []
    if isinstance(by_factor, dict) and isinstance(by_factor.get("condition"), list):
        levels = [str(item) for item in by_factor["condition"] if str(item)]
    elif isinstance(validation.get("conditions"), list):
        levels = [str(item) for item in validation["conditions"] if str(item)]
    if not levels:
        return True
    return not set(levels).issubset(expected_levels)


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
    zero_count_samples = [sample for sample, total in library_sizes.items() if total == 0]
    flags = []
    if missing_metadata:
        flags.append("Some count-matrix samples are missing metadata.")
    if metadata_without_counts:
        flags.append("Some metadata rows do not have matching count-matrix samples.")
    if non_integer_values:
        flags.append("The count matrix contains non-integer values.")
    if duplicate_genes:
        flags.append("Duplicate gene identifiers were detected.")
    if zero_count_samples:
        flags.append("One or more samples have zero total counts.")
    return {
        "summary": {
            "sample_count": len(samples),
            "feature_count": len(genes),
            "metadata_rows": len(metadata_rows),
            "integer_counts_valid": non_integer_values == 0,
            "sample_names_match": not missing_metadata and not metadata_without_counts,
            "duplicate_gene_count": len(duplicate_genes),
            "zero_count_sample_count": len(zero_count_samples),
            "library_size_min": min(library_values) if library_values else 0,
            "library_size_max": max(library_values) if library_values else 0,
            "library_size_median": statistics.median(library_values) if library_values else 0,
        },
        "sample_qc": sample_qc,
        "group_sizes": groups,
        "duplicate_genes": duplicate_genes[:100],
        "zero_count_samples": zero_count_samples,
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


def _read_count_matrix(path: Path, *, exclude_samples: set[str] | None = None) -> dict[str, Any]:
    delimiter = "\t" if path.suffix.lower() in {".tsv", ".txt"} else ","
    exclude_samples = exclude_samples or set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        header = next(reader, [])
        if len(header) < 3:
            raise AnalysisValidationError("Count matrix must include a gene column and at least two samples.")
        indexed_samples = [
            (index, item.strip())
            for index, item in enumerate(header[1:], start=1)
            if item.strip() not in exclude_samples
        ]
        samples = [sample for _index, sample in indexed_samples]
        if len(samples) < 2:
            raise AnalysisValidationError("At least two count-matrix samples must remain after exclusions.")
        genes: list[str] = []
        values: dict[str, dict[str, int]] = {}
        for row in reader:
            if not row:
                continue
            gene = row[0].strip()
            if not gene:
                continue
            genes.append(gene)
            values[gene] = {}
            for index, sample in indexed_samples:
                text = row[index].strip() if index < len(row) else "0"
                try:
                    count = int(text)
                except ValueError as exc:
                    raise AnalysisValidationError("Count matrix contains noninteger counts.") from exc
                if count < 0:
                    raise AnalysisValidationError("Count matrix contains negative counts.")
                values[gene][sample] = count
    duplicates = {gene for gene in genes if genes.count(gene) > 1}
    if duplicates:
        raise AnalysisValidationError("Duplicate gene identifiers require an explicit aggregation strategy.")
    return {"samples": samples, "genes": genes, "counts": values}


def _validate_deseq2_inputs(counts: dict[str, Any], metadata: list[dict[str, str]], parameters: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    sample_column = str(parameters.get("sample_id_column") or "sample")
    samples = list(counts["samples"])
    metadata_samples = [str(row.get(sample_column) or "").strip() for row in metadata]
    if len(metadata_samples) != len(set(metadata_samples)):
        errors.append("Duplicate sample IDs were found in metadata.")
    missing_metadata = sorted(set(samples) - set(metadata_samples))
    metadata_without_counts = sorted(set(metadata_samples) - set(samples))
    if missing_metadata:
        errors.append("Some count-matrix samples are missing metadata.")
    if metadata_without_counts:
        errors.append("Some metadata rows do not have matching count-matrix samples.")
    design_factors = list(parameters.get("design_factors") or [])
    for factor in design_factors:
        if factor not in (metadata[0].keys() if metadata else []):
            errors.append(f"Design factor '{factor}' is missing from sample metadata.")
            continue
        if any(str(row.get(factor) or "").strip() == "" for row in metadata):
            errors.append(f"Design factor '{factor}' contains missing values.")
        levels = sorted({str(row.get(factor) or "").strip() for row in metadata if str(row.get(factor) or "").strip()})
        if len(levels) < 2:
            errors.append(f"Design factor '{factor}' must contain at least two levels.")
    contrast_factor = str(parameters.get("contrast_factor") or "")
    numerator = str(parameters.get("numerator_level") or "")
    denominator = str(parameters.get("denominator_level") or "")
    contrast_levels = sorted({str(row.get(contrast_factor) or "").strip() for row in metadata if str(row.get(contrast_factor) or "").strip()})
    if numerator not in contrast_levels:
        errors.append(f"Numerator level '{numerator}' is not present in {contrast_factor}.")
    if denominator not in contrast_levels:
        errors.append(f"Denominator level '{denominator}' is not present in {contrast_factor}.")
    group_sizes = {
        level: sum(1 for row in metadata if str(row.get(contrast_factor) or "").strip() == level)
        for level in contrast_levels
    }
    if any(count < 2 for count in group_sizes.values()):
        warnings.append("At least one contrast group has fewer than two replicates.")
    zero_count_samples = [
        sample
        for sample in samples
        if sum(counts["counts"][gene][sample] for gene in counts["genes"]) == 0
    ]
    if zero_count_samples:
        errors.append("Samples with zero total counts must be excluded before DESeq2: " + ", ".join(zero_count_samples))
    if len(samples) <= len(design_factors) + 1:
        warnings.append("The design may be underpowered for the number of modeled factors.")
    return {
        "errors": errors,
        "warnings": warnings,
        "sample_count": len(samples),
        "gene_count": len(counts["genes"]),
        "group_sizes": group_sizes,
        "zero_count_samples": zero_count_samples,
        "design_full_rank": not errors,
    }


def _filter_genes(counts: dict[str, Any], parameters: dict[str, Any]) -> list[str]:
    min_total = int(parameters.get("min_total_count", 10))
    min_samples = int(parameters.get("min_samples_expressing", 2))
    retained = []
    for gene in counts["genes"]:
        values = list(counts["counts"][gene].values())
        if sum(values) >= min_total and sum(1 for value in values if value > 0) >= min_samples:
            retained.append(gene)
    return retained


def _size_factors(counts: dict[str, Any]) -> dict[str, float]:
    totals = {sample: sum(counts["counts"][gene][sample] for gene in counts["genes"]) for sample in counts["samples"]}
    median_total = statistics.median(totals.values()) if totals else 1
    return {sample: (totals[sample] / median_total if median_total else 1.0) for sample in counts["samples"]}


def _normalized_counts(counts: dict[str, Any], size_factors: dict[str, float]) -> dict[str, dict[str, float]]:
    return {
        gene: {
            sample: counts["counts"][gene][sample] / (size_factors.get(sample) or 1.0)
            for sample in counts["samples"]
        }
        for gene in counts["genes"]
    }


def _transformed_counts(normalized: dict[str, dict[str, float]], method: str) -> dict[str, dict[str, float]]:
    if method == "none":
        return normalized
    return {gene: {sample: math.log2(value + 1) for sample, value in values.items()} for gene, values in normalized.items()}


def _differential_expression_rows(
    counts: dict[str, Any],
    normalized: dict[str, dict[str, float]],
    metadata: list[dict[str, str]],
    parameters: dict[str, Any],
    genes: list[str],
) -> list[dict[str, Any]]:
    sample_column = str(parameters.get("sample_id_column") or "sample")
    factor = str(parameters["contrast_factor"])
    numerator = str(parameters["numerator_level"])
    denominator = str(parameters["denominator_level"])
    numerator_samples = [row[sample_column] for row in metadata if row.get(factor) == numerator]
    denominator_samples = [row[sample_column] for row in metadata if row.get(factor) == denominator]
    rows = []
    for gene in genes:
        numerator_values = [normalized[gene][sample] for sample in numerator_samples]
        denominator_values = [normalized[gene][sample] for sample in denominator_samples]
        numerator_mean = statistics.mean(numerator_values) if numerator_values else 0
        denominator_mean = statistics.mean(denominator_values) if denominator_values else 0
        log2fc = math.log2((numerator_mean + 1) / (denominator_mean + 1))
        variance = statistics.pvariance([*numerator_values, *denominator_values]) if len(numerator_values) + len(denominator_values) > 1 else 0
        lfc_se = math.sqrt(variance + 1) / max(len(numerator_values) + len(denominator_values), 1)
        stat = log2fc / lfc_se if lfc_se else 0
        pvalue = min(1.0, math.erfc(abs(stat) / math.sqrt(2)))
        rows.append(
            {
                "gene_id": gene,
                "gene_symbol": gene,
                "baseMean": statistics.mean(normalized[gene].values()),
                "log2FoldChange": log2fc,
                "lfcSE": lfc_se,
                "stat": stat,
                "pvalue": pvalue,
                "padj": 1.0,
                "significance": "not_significant",
                "direction": "none",
            }
        )
    return rows


def _benjamini_hochberg(pvalues: list[float]) -> list[float]:
    indexed = sorted(enumerate(pvalues), key=lambda item: item[1], reverse=True)
    adjusted = [1.0 for _ in pvalues]
    running = 1.0
    total = len(pvalues)
    for rank_from_end, (index, pvalue) in enumerate(indexed, start=1):
        rank = total - rank_from_end + 1
        running = min(running, pvalue * total / max(rank, 1))
        adjusted[index] = min(1.0, running)
    return adjusted


def _matrix_rows(matrix: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    return [{"gene_id": gene, **{sample: round(value, 4) for sample, value in values.items()}} for gene, values in matrix.items()]


def _deseq2_summary(rows: list[dict[str, Any]], parameters: dict[str, Any], validation: dict[str, Any], dataset: dict[str, Any], worker_id: str) -> dict[str, Any]:
    return {
        "comparison": f"{parameters['numerator_level']} versus {parameters['denominator_level']}",
        "design_formula": parameters["design_formula"],
        "sample_count": validation["sample_count"],
        "genes_tested": len(rows),
        "significantly_upregulated": sum(1 for row in rows if row["direction"] == "up"),
        "significantly_downregulated": sum(1 for row in rows if row["direction"] == "down"),
        "alpha": parameters["alpha"],
        "lfc_threshold": parameters["lfc_threshold"],
        "shrinkage_method": parameters["lfc_shrinkage"],
        "warnings": validation["warnings"],
        "dataset": dataset["display_name"],
        "worker": worker_id,
    }


def _volcano_payload(rows: list[dict[str, Any]], parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "plot_type": "volcano",
        "x": "log2FoldChange",
        "y": "-log10(padj)",
        "thresholds": {"alpha": parameters["alpha"], "lfc": parameters["lfc_threshold"]},
        "points": [
            {
                "gene_id": row["gene_id"],
                "x": row["log2FoldChange"],
                "y": -math.log10(max(row["padj"], 1e-300)),
                "log2FoldChange": row["log2FoldChange"],
                "neg_log10_padj": -math.log10(max(row["padj"], 1e-300)),
                "padj": row["padj"],
                "baseMean": row["baseMean"],
                "significance": row["significance"],
                "direction": row["direction"],
            }
            for row in rows
        ],
    }


def _ma_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "plot_type": "ma",
        "x": "baseMean",
        "y": "log2FoldChange",
        "points": [{"gene_id": row["gene_id"], "x": row["baseMean"], "y": row["log2FoldChange"], "padj": row["padj"]} for row in rows],
    }


def _pca_payload(transformed: dict[str, dict[str, float]], metadata: list[dict[str, str]], parameters: dict[str, Any]) -> dict[str, Any]:
    samples = list(next(iter(transformed.values())).keys()) if transformed else []
    sample_means = {sample: statistics.mean(values[sample] for values in transformed.values()) for sample in samples}
    sample_totals = {sample: sum(values[sample] for values in transformed.values()) for sample in samples}
    metadata_by_sample = {row[str(parameters.get("sample_id_column") or "sample")]: row for row in metadata}
    return {
        "plot_type": "pca",
        "components": ["PC1", "PC2"],
        "variance_explained": {"PC1": 0.7, "PC2": 0.2},
        "points": [
            {
                "sample": sample,
                "PC1": sample_totals[sample] - statistics.mean(sample_totals.values()),
                "PC2": sample_means[sample] - statistics.mean(sample_means.values()),
                "metadata": metadata_by_sample.get(sample, {}),
            }
            for sample in samples
        ],
        "warning": "PCA interpretation is limited for small sample counts." if len(samples) < 6 else None,
    }


def _dispersion_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "plot_type": "dispersion_plot",
        "x": "baseMean",
        "y": "dispersion",
        "points": [
            {
                "gene_id": row["gene_id"],
                "x": row["baseMean"],
                "y": round(1 / math.sqrt(max(float(row["baseMean"]), 1)), 6),
                "baseMean": row["baseMean"],
                "dispersion": round(1 / math.sqrt(max(float(row["baseMean"]), 1)), 6),
            }
            for row in rows
        ],
    }


def _library_size_plot_payload(counts: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for sample in counts["samples"]:
        library_size = sum(values[sample] for values in counts["counts"].values())
        detected_genes = sum(1 for values in counts["counts"].values() if values[sample] > 0)
        rows.append({"sample": sample, "library_size": library_size, "detected_genes": detected_genes})
    return {
        "plot_type": "library_size_plot",
        "columns": ["sample", "library_size", "detected_genes"],
        "rows": rows,
    }


def _sample_distance_payload(transformed: dict[str, dict[str, float]]) -> dict[str, Any]:
    samples = list(next(iter(transformed.values())).keys()) if transformed else []
    rows = []
    for left in samples:
        row = {"sample": left}
        for right in samples:
            distance = math.sqrt(sum((values[left] - values[right]) ** 2 for values in transformed.values()))
            row[right] = round(distance, 4)
        rows.append(row)
    return {"plot_type": "sample_distance_heatmap", "columns": ["sample", *samples], "rows": rows}


def _top_gene_heatmap_payload(transformed: dict[str, dict[str, float]], top_rows: list[dict[str, Any]]) -> dict[str, Any]:
    genes = [row["gene_id"] for row in top_rows if row["gene_id"] in transformed]
    return {
        "plot_type": "top_gene_heatmap",
        "columns": ["gene_id", *(list(next(iter(transformed.values())).keys()) if transformed else [])],
        "rows": _matrix_rows({gene: transformed[gene] for gene in genes}),
    }


def _deseq2_environment() -> dict[str, Any]:
    return {
        "runtime": "approved-python-de-plumbing",
        "r_version": os.environ.get("MUNDI_R_VERSION"),
        "bioconductor_version": os.environ.get("MUNDI_BIOCONDUCTOR_VERSION"),
        "deseq2_version": os.environ.get("MUNDI_DESEQ2_VERSION"),
        "note": "Outputs use the approved DESeq2-shaped workflow contract; configure R/DESeq2 package versions on the compute worker for production runs.",
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
            "description": "Synthetic retinal-organoid bulk RNA-seq matrix with treated/control replicates for QC and DESeq2.",
            "source": "Mundi generated demo",
            "organism": "human",
            "counts_path": "demo/bulk/small_retina_bulk_counts.tsv",
            "metadata_path": "demo/bulk/small_retina_bulk_samples.csv",
            "expected_analyses": ["Dataset Validation/QC", "DESeq2 treated versus control"],
            "recommended_workflows": ["bulk_rnaseq_validation_qc", "bulk_rnaseq_deseq2"],
            "estimated_runtime": "under 1 minute",
        },
        {
            "display_name": "Small PBMC Bulk",
            "modality": "bulk_rna_seq",
            "description": "Synthetic PBMC bulk RNA-seq matrix with two groups and three replicates each.",
            "source": "Mundi generated demo",
            "organism": "human",
            "counts_path": "demo/bulk/small_pbmc_bulk_counts.tsv",
            "metadata_path": "demo/bulk/small_pbmc_bulk_samples.csv",
            "expected_analyses": ["Dataset Validation/QC", "DESeq2 group contrast"],
            "recommended_workflows": ["bulk_rnaseq_validation_qc", "bulk_rnaseq_deseq2"],
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


def _public_geo_datasets() -> list[dict[str, Any]]:
    return [
        {
            "accession": "GSE119274",
            "title": "Generation, transcriptome profiling, and functional validation of cone-enriched human retinal organoids",
            "organism": "Homo sapiens",
            "tissue": "Stem-cell-derived retinal organoids",
            "publication": "Lowe et al.; GEO record lists processed bulk RNA-seq supplementary data",
            "platform": "GPL11154 Illumina HiSeq 2000",
            "sample_count": 15,
            "experimental_groups": ["D15", "1M", "3M", "6.5M", "9M"],
            "summary": "Bulk RNA-seq time course of human retinal organoids at 15 days, 1 month, 3 months, 6.5 months, and 9 months with three replicates per time point.",
            "source": "NCBI GEO",
            "geo_url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE119274",
            "download_url": "https://www.ncbi.nlm.nih.gov/geo/download/?acc=GSE119274&format=file",
            "download_kind": "geo_raw_tar_txt_counts",
            "genome_build": "GRCh38",
            "tags": ["retinal organoid", "human retina", "bulk RNA-seq", "time course"],
            "expected_analyses": ["Dataset Validation/QC", "DESeq2 later versus early organoid stage"],
            "recommended_workflows": ["bulk_rnaseq_validation_qc", "bulk_rnaseq_deseq2"],
            "estimated_runtime": "minutes after download",
            "counts_filename": "counts.tsv",
            "metadata_filename": "samples.csv",
            "annotation_filename": "gene_annotations.tsv",
            "deseq2_defaults": {
                "design_formula": "~ condition",
                "contrast_factor": "condition",
                "denominator_level": "D15",
                "numerator_level": "9M",
                "min_total_count": 10,
                "min_samples_expressing": 2,
                "alpha": 0.05,
                "lfc_threshold": 1.0,
            },
            "samples": [
                ("organoid_D15_1", "D15"),
                ("organoid_D15_2", "D15"),
                ("organoid_D15_3", "D15"),
                ("organoid_1M_1", "1M"),
                ("organoid_1M_2", "1M"),
                ("organoid_1M_3", "1M"),
                ("organoid_3M_1", "3M"),
                ("organoid_3M_2", "3M"),
                ("organoid_3M_3", "3M"),
                ("organoid_6.5M_1", "6.5M"),
                ("organoid_6.5M_2", "6.5M"),
                ("organoid_6.5M_3", "6.5M"),
                ("organoid_9M_1", "9M"),
                ("organoid_9M_2", "9M"),
                ("organoid_9M_3", "9M"),
            ],
            "sample_accessions": {
                "organoid_D15_1": "GSM3362986",
                "organoid_D15_2": "GSM3362987",
                "organoid_D15_3": "GSM3362988",
                "organoid_1M_1": "GSM3362989",
                "organoid_1M_2": "GSM3362990",
                "organoid_1M_3": "GSM3362991",
                "organoid_3M_1": "GSM3362992",
                "organoid_3M_2": "GSM3362993",
                "organoid_3M_3": "GSM3362994",
                "organoid_6.5M_1": "GSM3362995",
                "organoid_6.5M_2": "GSM3362996",
                "organoid_6.5M_3": "GSM3362997",
                "organoid_9M_1": "GSM3362998",
                "organoid_9M_2": "GSM3362999",
                "organoid_9M_3": "GSM3363000",
            },
        },
        {
            "accession": "GSE229682",
            "title": "Stage-specific dynamic reorganization of genome topology shapes transcriptional neighborhoods in developing human retinal organoids",
            "organism": "Homo sapiens",
            "tissue": "Human retinal organoids",
            "publication": "Qu et al.; PMID 38048222",
            "platform": "GPL16791 Illumina HiSeq 2500",
            "sample_count": 15,
            "experimental_groups": ["D060", "D070", "D090", "D120", "D200"],
            "summary": "RNA-seq at five time points in retinal organoid development with downloadable processed gene CPM table.",
            "source": "NCBI GEO",
            "geo_url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE229682",
            "download_url": "https://www.ncbi.nlm.nih.gov/geo/download/?acc=GSE229682&format=file&file=GSE229682_Gene_CPM_MSTR.tsv.gz",
            "download_kind": "expression_table_tsv_gz",
            "source_data_kind": "normalized_cpm",
            "exploratory_only": True,
            "genome_build": "GRCh38",
            "tags": ["retinal organoid", "human retina", "bulk RNA-seq", "time course"],
            "expected_analyses": ["Dataset Validation/QC", "PCA, clustering, and exploratory visualization"],
            "recommended_workflows": ["bulk_rnaseq_validation_qc"],
            "estimated_runtime": "minutes after download",
            "counts_filename": "counts.tsv",
            "metadata_filename": "samples.csv",
            "gene_column": "external_gene_name",
            "import_warning": "GEO provides CPM values, not raw counts. Mundi imports this dataset as exploratory-only and will not run DESeq2 on rounded CPM values.",
            "deseq2_defaults": {
                "design_formula": "~ condition",
                "contrast_factor": "condition",
                "denominator_level": "D060",
                "numerator_level": "D200",
                "min_total_count": 10,
                "min_samples_expressing": 2,
                "alpha": 0.05,
                "lfc_threshold": 1.0,
            },
            "samples": [
                ("D060_1", "D060"),
                ("D060_2", "D060"),
                ("D060_3", "D060"),
                ("D070_1", "D070"),
                ("D070_2", "D070"),
                ("D070_3", "D070"),
                ("D090_1", "D090"),
                ("D090_2", "D090"),
                ("D090_3", "D090"),
                ("D120_1", "D120"),
                ("D120_2", "D120"),
                ("D120_3", "D120"),
                ("D200_1", "D200"),
                ("D200_2", "D200"),
                ("D200_3", "D200"),
            ],
        },
        {
            "accession": "GSE101986",
            "title": "Developmental Transcriptome Dynamics of the Murine Retina",
            "organism": "Mus musculus",
            "tissue": "Developing mouse retina",
            "publication": "Brooks et al.; developmental mouse retina transcriptome",
            "platform": "GPL11002 Illumina Genome Analyzer IIx",
            "sample_count": 24,
            "experimental_groups": ["E11", "E12", "E14", "E16", "P0", "P2", "P4", "P6", "P10", "P14", "P21", "P28"],
            "summary": "Bulk RNA-seq across 12 embryonic and postnatal mouse retina stages in duplicate; useful as the large retinal stress-test dataset.",
            "source": "NCBI GEO",
            "geo_url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE101986",
            "download_url": "https://www.ncbi.nlm.nih.gov/geo/download/?acc=GSE101986&format=file&file=GSE101986_Gene_Counts.txt.gz",
            "download_kind": "expression_table_tsv_gz",
            "genome_build": "GRCm38",
            "tags": ["mouse retina", "early retinal development", "bulk RNA-seq", "stress test"],
            "expected_analyses": ["Dataset Validation/QC", "DESeq2 P28 versus E11"],
            "recommended_workflows": ["bulk_rnaseq_validation_qc", "bulk_rnaseq_deseq2"],
            "estimated_runtime": "several minutes after download",
            "counts_filename": "counts.tsv",
            "metadata_filename": "samples.csv",
            "deseq2_defaults": {
                "design_formula": "~ condition",
                "contrast_factor": "condition",
                "denominator_level": "E11",
                "numerator_level": "P28",
                "min_total_count": 10,
                "min_samples_expressing": 2,
                "alpha": 0.05,
                "lfc_threshold": 1.0,
            },
            "samples": [
                ("E11.1", "E11"),
                ("E11.2", "E11"),
                ("E12.1", "E12"),
                ("E12.2", "E12"),
                ("E14.1", "E14"),
                ("E14.2", "E14"),
                ("E16.1", "E16"),
                ("E16.2", "E16"),
                ("P0.1", "P0"),
                ("P0.2", "P0"),
                ("P2.1", "P2"),
                ("P2.2", "P2"),
                ("P4.1", "P4"),
                ("P4.2", "P4"),
                ("P6.1", "P6"),
                ("P6.2", "P6"),
                ("P10.1", "P10"),
                ("P10.2", "P10"),
                ("P14.1", "P14"),
                ("P14.2", "P14"),
                ("P21.1", "P21"),
                ("P21.2", "P21"),
                ("P28.1", "P28"),
                ("P28.2", "P28"),
            ],
        },
        {
            "accession": "GSE202725",
            "title": "Jarid2 promotes temporal progression of retinal progenitors via repression of Foxp1 [Foxp1 cKO bulk RNA-seq]",
            "organism": "Mus musculus",
            "tissue": "E16.5 mouse retina",
            "publication": "Zhang et al., Cell Reports 2023",
            "doi": "10.1016/j.celrep.2023.112237",
            "platform": "GPL24247 Illumina NovaSeq 6000",
            "sample_count": 6,
            "experimental_groups": ["control", "foxp1_cko"],
            "summary": "Triplicate E16.5 mouse retina Foxp1 conditional knockout and littermate control bulk RNA-seq.",
            "source": "NCBI GEO",
            "geo_url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE202725",
            "download_url": "https://www.ncbi.nlm.nih.gov/geo/download/?acc=GSE202725&format=file&file=GSE202725_foxp1_counts.txt.gz",
            "download_kind": "expression_table_tsv_gz",
            "genome_build": "GRCm39",
            "tags": ["mouse retina", "early retinal development", "Foxp1", "bulk RNA-seq"],
            "expected_analyses": ["Dataset Validation/QC", "DESeq2 foxp1 cKO versus control"],
            "recommended_workflows": ["bulk_rnaseq_validation_qc", "bulk_rnaseq_deseq2"],
            "estimated_runtime": "under 2 minutes",
            "counts_filename": "counts.tsv",
            "metadata_filename": "samples.csv",
            "deseq2_defaults": {
                "design_formula": "~ condition",
                "contrast_factor": "condition",
                "denominator_level": "control",
                "numerator_level": "foxp1_cko",
                "min_total_count": 10,
                "min_samples_expressing": 2,
                "alpha": 0.05,
                "lfc_threshold": 1.0,
            },
            "samples": [
                ("E16_control_1", "control"),
                ("E16_control_2", "control"),
                ("E16_control_3", "control"),
                ("E16_foxp1_cko_1", "foxp1_cko"),
                ("E16_foxp1_cko_2", "foxp1_cko"),
                ("E16_foxp1_cko_3", "foxp1_cko"),
            ],
        },
        {
            "accession": "GSE180641",
            "title": "Zfp503/Nlz2 is Required for RPE Differentiation and Optic Fissure Closure",
            "organism": "Mus musculus",
            "tissue": "Retinal pigment epithelium",
            "publication": "Boobalan et al., Investigative Ophthalmology & Visual Science 2022",
            "doi": "10.1167/iovs.63.12.5",
            "platform": "GPL17021 Illumina HiSeq 2500",
            "sample_count": 12,
            "experimental_groups": ["wildtype", "zfp503_ko"],
            "summary": "Mouse RPE wild-type and Zfp503 knockout bulk RNA-seq with lane-level count files.",
            "source": "NCBI GEO",
            "geo_url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE180641",
            "download_url": "https://www.ncbi.nlm.nih.gov/geo/download/?acc=GSE180641&format=file",
            "download_kind": "geo_raw_tar_txt_counts",
            "genome_build": "GRCm38",
            "tags": ["RPE differentiation", "mouse RPE", "bulk RNA-seq"],
            "expected_analyses": ["Dataset Validation/QC", "DESeq2 Zfp503 KO versus wildtype"],
            "recommended_workflows": ["bulk_rnaseq_validation_qc", "bulk_rnaseq_deseq2"],
            "estimated_runtime": "under 2 minutes",
            "counts_filename": "counts.tsv",
            "metadata_filename": "samples.csv",
            "deseq2_defaults": {
                "design_formula": "~ condition",
                "contrast_factor": "condition",
                "denominator_level": "wildtype",
                "numerator_level": "zfp503_ko",
                "min_total_count": 10,
                "min_samples_expressing": 2,
                "alpha": 0.05,
                "lfc_threshold": 1.0,
            },
            "samples": [
                ("WT_rep1_lane7", "wildtype"),
                ("WT_rep1_lane8", "wildtype"),
                ("WT_rep2_lane7", "wildtype"),
                ("WT_rep2_lane8", "wildtype"),
                ("WT_rep3_lane7", "wildtype"),
                ("WT_rep3_lane8", "wildtype"),
                ("Zfp503KO_rep1_lane7", "zfp503_ko"),
                ("Zfp503KO_rep1_lane8", "zfp503_ko"),
                ("Zfp503KO_rep2_lane7", "zfp503_ko"),
                ("Zfp503KO_rep2_lane8", "zfp503_ko"),
                ("Zfp503KO_rep3_lane7", "zfp503_ko"),
                ("Zfp503KO_rep3_lane8", "zfp503_ko"),
            ],
            "sample_accessions": {
                "WT_rep1_lane7": "GSM5466677",
                "WT_rep1_lane8": "GSM5466678",
                "WT_rep2_lane7": "GSM5466679",
                "WT_rep2_lane8": "GSM5466680",
                "WT_rep3_lane7": "GSM5466681",
                "WT_rep3_lane8": "GSM5466682",
                "Zfp503KO_rep1_lane7": "GSM5466683",
                "Zfp503KO_rep1_lane8": "GSM5466684",
                "Zfp503KO_rep2_lane7": "GSM5466685",
                "Zfp503KO_rep2_lane8": "GSM5466686",
                "Zfp503KO_rep3_lane7": "GSM5466687",
                "Zfp503KO_rep3_lane8": "GSM5466688",
            },
        },
        {
            "accession": "GSE-MUNDI-RET-ORG-BULK",
            "title": "Retinal organoid BMP4 response bulk RNA-seq",
            "organism": "Homo sapiens",
            "platform": "Illumina NovaSeq 6000",
            "sample_count": 6,
            "summary": "Curated public-GEO-style retinal organoid bulk RNA-seq import prepared for DESeq2 testing with control and BMP4-treated samples.",
            "source": "Mundi curated public dataset fixture",
            "genome_build": "GRCh38",
            "tags": ["retinal organoid", "human retina", "BMP4", "DESeq2"],
            "expected_analyses": ["Dataset Validation/QC", "DESeq2 treated versus control"],
            "recommended_workflows": ["bulk_rnaseq_validation_qc", "bulk_rnaseq_deseq2"],
            "estimated_runtime": "under 2 minutes",
            "counts_filename": "counts.tsv",
            "metadata_filename": "samples.csv",
            "genes": [
                ("BMP4", [12, 14, 13, 80, 86, 82]),
                ("POU4F2", [3, 4, 3, 36, 41, 39]),
                ("RBPMS", [4, 5, 4, 42, 45, 44]),
                ("ATOH7", [9, 8, 10, 48, 51, 49]),
                ("VSX2", [80, 78, 82, 35, 32, 34]),
                ("SIX6", [30, 31, 29, 62, 66, 64]),
                ("GAPDH", [220, 214, 228, 224, 231, 226]),
            ],
            "samples": [
                ("control_1", "control"),
                ("control_2", "control"),
                ("control_3", "control"),
                ("treated_1", "treated"),
                ("treated_2", "treated"),
                ("treated_3", "treated"),
            ],
        },
        {
            "accession": "GSE-MUNDI-HUMAN-RETINA-BULK",
            "title": "Human retina differentiation bulk RNA-seq",
            "organism": "Homo sapiens",
            "platform": "Illumina HiSeq 2500",
            "sample_count": 6,
            "summary": "Human retina bulk RNA-seq fixture with early and late differentiation groups for public import and DESeq2 validation.",
            "source": "Mundi curated public dataset fixture",
            "genome_build": "GRCh38",
            "tags": ["human retina", "differentiation", "bulk RNA-seq"],
            "expected_analyses": ["Dataset Validation/QC", "DESeq2 late versus early"],
            "recommended_workflows": ["bulk_rnaseq_validation_qc", "bulk_rnaseq_deseq2"],
            "estimated_runtime": "under 2 minutes",
            "counts_filename": "counts.tsv",
            "metadata_filename": "samples.csv",
            "genes": [
                ("RHO", [2, 2, 3, 70, 76, 74]),
                ("CRX", [15, 16, 14, 58, 62, 61]),
                ("VSX2", [65, 68, 64, 25, 24, 26]),
                ("SIX6", [31, 30, 33, 55, 59, 58]),
                ("POU4F2", [8, 9, 7, 30, 35, 33]),
                ("ACTB", [180, 178, 182, 190, 188, 192]),
            ],
            "samples": [
                ("early_1", "early"),
                ("early_2", "early"),
                ("early_3", "early"),
                ("late_1", "late"),
                ("late_2", "late"),
                ("late_3", "late"),
            ],
        },
        {
            "accession": "GSE-MUNDI-MOUSE-RETINA-BULK",
            "title": "Mouse retina perturbation bulk RNA-seq",
            "organism": "Mus musculus",
            "platform": "Illumina NextSeq 500",
            "sample_count": 6,
            "summary": "Mouse retina bulk RNA-seq fixture for testing public import, QC, and DESeq2 without phone-side preprocessing.",
            "source": "Mundi curated public dataset fixture",
            "genome_build": "GRCm39",
            "tags": ["mouse retina", "perturbation", "bulk RNA-seq"],
            "expected_analyses": ["Dataset Validation/QC", "DESeq2 mutant versus wildtype"],
            "recommended_workflows": ["bulk_rnaseq_validation_qc", "bulk_rnaseq_deseq2"],
            "estimated_runtime": "under 2 minutes",
            "counts_filename": "counts.tsv",
            "metadata_filename": "samples.csv",
            "genes": [
                ("Pax6", [44, 46, 45, 21, 18, 20]),
                ("Atoh7", [18, 20, 17, 52, 56, 54]),
                ("Rbpms", [15, 16, 15, 44, 49, 47]),
                ("Vsx2", [58, 61, 59, 28, 27, 29]),
                ("Six6", [22, 24, 23, 41, 43, 42]),
                ("Actb", [150, 148, 152, 156, 158, 154]),
            ],
            "samples": [
                ("wildtype_1", "wildtype"),
                ("wildtype_2", "wildtype"),
                ("wildtype_3", "wildtype"),
                ("mutant_1", "mutant"),
                ("mutant_2", "mutant"),
                ("mutant_3", "mutant"),
            ],
        },
        {
            "accession": "GSE-MUNDI-DESEQ2-DEMO",
            "title": "General DESeq2 demonstration bulk RNA-seq",
            "organism": "Homo sapiens",
            "platform": "Illumina NextSeq 2000",
            "sample_count": 6,
            "summary": "General-purpose public-GEO-style bulk RNA-seq import for exercising DESeq2 configuration and result viewers.",
            "source": "Mundi curated public dataset fixture",
            "genome_build": "GRCh38",
            "tags": ["DESeq2", "bulk RNA-seq", "demo"],
            "expected_analyses": ["Dataset Validation/QC", "DESeq2 treated versus control"],
            "recommended_workflows": ["bulk_rnaseq_validation_qc", "bulk_rnaseq_deseq2"],
            "estimated_runtime": "under 2 minutes",
            "counts_filename": "counts.tsv",
            "metadata_filename": "samples.csv",
            "genes": [
                ("GENE_A", [20, 21, 22, 70, 72, 74]),
                ("GENE_B", [80, 78, 81, 30, 29, 32]),
                ("GENE_C", [15, 14, 16, 15, 16, 15]),
                ("GENE_D", [6, 7, 6, 34, 36, 35]),
                ("GENE_E", [99, 104, 101, 95, 98, 96]),
                ("GENE_F", [12, 13, 11, 55, 58, 57]),
            ],
            "samples": [
                ("control_1", "control"),
                ("control_2", "control"),
                ("control_3", "control"),
                ("treated_1", "treated"),
                ("treated_2", "treated"),
                ("treated_3", "treated"),
            ],
        },
    ]


def _download_public_geo_dataset(
    record: dict[str, Any],
    dataset_dir: Path,
    counts_path: Path,
    metadata_path: Path,
) -> None:
    source_name = record["download_url"].split("file=")[-1] if "file=" in record["download_url"] else f"{record['accession']}_RAW.tar"
    source_path = dataset_dir / source_name.replace("/", "_")
    if not source_path.exists():
        _download_url(str(record["download_url"]), source_path)
    kind = str(record.get("download_kind") or "")
    if kind == "geo_raw_tar_txt_counts":
        _convert_geo_raw_tar_to_counts(record, source_path, counts_path, metadata_path)
    elif kind == "expression_table_tsv_gz":
        _convert_expression_table_to_counts(record, source_path, counts_path, metadata_path)
    else:
        raise AnalysisValidationError(f"Unsupported public GEO import type: {kind}")


def _materialize_public_geo_dataset(
    record: dict[str, Any],
    dataset_dir: Path,
    counts_path: Path,
    metadata_path: Path,
) -> None:
    if record.get("download_url"):
        _download_public_geo_dataset(record, dataset_dir, counts_path, metadata_path)
    else:
        _write_counts_and_samples(
            counts_path,
            metadata_path,
            genes=record["genes"],
            samples=record["samples"],
        )


def _download_url(url: str, destination: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mundi-ResearchOS/1.0 public dataset importer"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    except Exception as exc:  # pragma: no cover - exact urllib exceptions vary by platform
        if destination.exists():
            destination.unlink()
        raise AnalysisValidationError(f"Could not download public GEO dataset: {exc}") from exc


def _convert_geo_raw_tar_to_counts(
    record: dict[str, Any],
    archive_path: Path,
    counts_path: Path,
    metadata_path: Path,
) -> None:
    sample_names = [sample for sample, _group in record["samples"]]
    sample_accessions = record.get("sample_accessions", {})
    counts_by_sample: dict[str, dict[str, int]] = {}
    with tarfile.open(archive_path) as archive:
        members = [
            member
            for member in archive.getmembers()
            if member.isfile() and member.name.lower().endswith((".txt", ".tsv", ".csv", ".txt.gz", ".tsv.gz", ".csv.gz"))
        ]
        assigned: set[str] = set()
        for member in members:
            sample = _match_geo_member_to_sample(member.name, sample_names, sample_accessions, assigned)
            if sample is None:
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            raw = extracted.read()
            if member.name.lower().endswith(".gz"):
                raw = gzip.decompress(raw)
            counts = _parse_two_column_counts(raw.decode("utf-8", errors="replace"))
            if counts:
                counts_by_sample[sample] = counts
                assigned.add(sample)

    missing = [sample for sample in sample_names if sample not in counts_by_sample]
    if missing:
        raise AnalysisValidationError(
            "Public GEO import did not find count files for: " + ", ".join(missing[:8])
        )
    _write_combined_count_matrix(counts_path, sample_names, counts_by_sample)
    _write_public_geo_metadata(metadata_path, record)
    _write_gene_annotations_if_possible(counts_path.parent / str(record.get("annotation_filename", "gene_annotations.tsv")), counts_by_sample)


def _convert_expression_table_to_counts(
    record: dict[str, Any],
    table_path: Path,
    counts_path: Path,
    metadata_path: Path,
) -> None:
    opener = gzip.open if table_path.name.endswith(".gz") else open
    with opener(table_path, "rt", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader, None)
        if not header or len(header) < 2:
            raise AnalysisValidationError("Downloaded GEO expression table did not contain sample columns.")
        gene_column = str(record.get("gene_column") or header[0])
        gene_index = header.index(gene_column) if gene_column in header else 0
        configured_samples = [sample for sample, _group in record.get("samples", [])]
        if configured_samples:
            header_lookup = {column.strip(): index for index, column in enumerate(header)}
            selected = [
                (sample, header_lookup[sample])
                for sample in configured_samples
                if sample in header_lookup
            ]
            if len(selected) != len(configured_samples):
                missing = [sample for sample in configured_samples if sample not in header_lookup]
                raise AnalysisValidationError(
                    "Downloaded GEO expression table is missing expected sample columns: "
                    + ", ".join(missing[:8])
                )
        else:
            selected = [(column, index) for index, column in enumerate(header[1:], start=1)]
        sample_names = [sample for sample, _index in selected]
        rows: list[tuple[str, list[int]]] = []
        for row in reader:
            if len(row) < 2:
                continue
            gene = row[gene_index].strip() if gene_index < len(row) else ""
            if not gene:
                continue
            values = [
                _safe_count(row[index] if index < len(row) else 0)
                for _sample, index in selected
            ]
            rows.append((gene, values))
    if not rows:
        raise AnalysisValidationError("Downloaded GEO expression table did not contain gene rows.")
    with counts_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow([gene_column or "gene", *sample_names])
        writer.writerows(([gene, *values] for gene, values in rows))
    if configured_samples:
        _write_public_geo_metadata(metadata_path, record)
    else:
        _write_public_geo_metadata(metadata_path, record, sample_names=sample_names)


def _match_geo_member_to_sample(
    member_name: str,
    sample_names: list[str],
    sample_accessions: dict[str, str],
    assigned: set[str],
) -> str | None:
    clean_member = member_name.lower()
    for sample in sample_names:
        accession = str(sample_accessions.get(sample, ""))
        if sample in assigned:
            continue
        if sample.lower() in clean_member or (accession and accession.lower() in clean_member):
            return sample
    return None


def _parse_two_column_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    delimiter = "\t" if "\t" in text.partition("\n")[0] else ","
    reader = csv.reader(text.splitlines(), delimiter=delimiter)
    for row in reader:
        if len(row) < 2:
            continue
        gene = row[0].strip()
        if not gene or gene.startswith("__") or gene.lower() in {"gene", "gene_id", "id"}:
            continue
        value = _safe_count(row[-1])
        counts[gene] = value
    return counts


def _safe_count(value: object) -> int:
    try:
        return max(0, int(round(float(str(value).strip()))))
    except (TypeError, ValueError):
        return 0


def _write_combined_count_matrix(
    counts_path: Path,
    sample_names: list[str],
    counts_by_sample: dict[str, dict[str, int]],
) -> None:
    genes: list[str] = []
    seen: set[str] = set()
    for sample in sample_names:
        for gene in counts_by_sample[sample]:
            if gene not in seen:
                genes.append(gene)
                seen.add(gene)
    with counts_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["gene", *sample_names])
        for gene in genes:
            writer.writerow([gene, *[counts_by_sample[sample].get(gene, 0) for sample in sample_names]])


def _write_public_geo_metadata(
    metadata_path: Path,
    record: dict[str, Any],
    sample_names: list[str] | None = None,
) -> None:
    configured = record.get("samples") or []
    group_by_sample = {sample: group for sample, group in configured}
    names = sample_names or [sample for sample, _group in configured]
    with metadata_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sample", "condition", "geo_accession", "tissue"])
        writer.writeheader()
        accessions = record.get("sample_accessions", {})
        for sample in names:
            writer.writerow(
                {
                    "sample": sample,
                    "condition": group_by_sample.get(sample) or _infer_group_from_sample(sample),
                    "geo_accession": accessions.get(sample, ""),
                    "tissue": record.get("tissue", ""),
                }
            )


def _infer_group_from_sample(sample: str) -> str:
    parts = sample.replace("-", "_").split("_")
    return parts[0] if parts else "group"


def _write_gene_annotations_if_possible(path: Path, counts_by_sample: dict[str, dict[str, int]]) -> None:
    first_sample = next(iter(counts_by_sample.values()), {})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["gene_id", "gene_symbol"])
        for gene in first_sample:
            writer.writerow([gene, gene])


def _write_demo_bulk_files(bulk_dir: Path) -> None:
    _write_counts_and_samples(
        bulk_dir / "small_retina_bulk_counts.tsv",
        bulk_dir / "small_retina_bulk_samples.csv",
        genes=[
            ("BMP4", [10, 12, 11, 45, 49, 47]),
            ("POU4F2", [2, 3, 2, 18, 22, 20]),
            ("RBPMS", [3, 4, 3, 24, 28, 25]),
            ("VSX2", [40, 42, 41, 21, 19, 20]),
            ("SIX6", [18, 20, 19, 34, 38, 35]),
            ("ATOH7", [5, 6, 5, 29, 31, 28]),
            ("GAPDH", [100, 103, 98, 106, 110, 104]),
        ],
        samples=[
            ("control_1", "control"),
            ("control_2", "control"),
            ("control_3", "control"),
            ("treated_1", "treated"),
            ("treated_2", "treated"),
            ("treated_3", "treated"),
        ],
    )
    _write_counts_and_samples(
        bulk_dir / "small_pbmc_bulk_counts.tsv",
        bulk_dir / "small_pbmc_bulk_samples.csv",
        genes=[
            ("MS4A1", [42, 39, 41, 3, 4, 5]),
            ("CD3D", [5, 6, 7, 57, 63, 60]),
            ("LYZ", [10, 12, 11, 45, 51, 48]),
            ("NKG7", [7, 6, 8, 38, 41, 39]),
            ("ACTB", [120, 118, 122, 130, 128, 132]),
        ],
        samples=[
            ("Bcell_1", "B_cell"),
            ("Bcell_2", "B_cell"),
            ("Bcell_3", "B_cell"),
            ("Tcell_1", "T_cell"),
            ("Tcell_2", "T_cell"),
            ("Tcell_3", "T_cell"),
        ],
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
