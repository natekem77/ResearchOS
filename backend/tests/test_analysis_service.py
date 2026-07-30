import csv
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.analysis import AnalysisAuthorizationError, AnalysisService, AnalysisValidationError
from app.config import Settings


class AnalysisServiceTests(unittest.TestCase):
    def _settings(self, tmpdir: str) -> Settings:
        return Settings(
            data_dir=tmpdir,
            database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}",
        )

    def _fixture(self, tmpdir: str) -> tuple[AnalysisService, Path]:
        root = Path(tmpdir) / "lab-data"
        root.mkdir(parents=True)
        _write_bulk_fixture(root)
        previous = os.environ.get("MUNDI_ANALYSIS_DATA_ROOTS")
        os.environ["MUNDI_ANALYSIS_DATA_ROOTS"] = str(root)
        self.addCleanup(_restore_env, "MUNDI_ANALYSIS_DATA_ROOTS", previous)
        return AnalysisService(self._settings(tmpdir)), root

    def test_worker_registration_and_heartbeat(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            service.require_worker_token("dev-compute-worker-token")
            worker = service.register_worker(
                {
                    "worker_id": "worker-1",
                    "display_name": "Lab Analysis Server",
                    "cpu_count": 32,
                    "ram_gb": 128,
                    "gpu_inventory": [{"name": "NVIDIA RTX 4090", "memory_gb": 24}],
                    "supported_runtimes": ["python", "r", "pytorch"],
                    "supported_workflows": ["bulk_rnaseq_validation_qc"],
                    "software_versions": {"python": "3.x", "R": "4.x"},
                    "status": "ready",
                }
            )
            heartbeat = service.record_worker_heartbeat(
                "worker-1",
                {"status": "ready", "running_job_count": 0},
            )

        self.assertEqual(worker["worker_id"], "worker-1")
        self.assertTrue(heartbeat["connected"])
        self.assertEqual(heartbeat["status"], "ready")

    def test_legacy_analysis_outputs_schema_adds_registration_key_before_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "researchos.db"
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    CREATE TABLE analysis_outputs (
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
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO analysis_outputs
                        (id, job_id, dataset_id, output_type, display_name, structured_json, viewer_config_json, provenance_json)
                    VALUES ('analysis-output:legacy', 'analysis-job:legacy', 'analysis-dataset:legacy', 'table',
                            'Legacy Library Sizes', '{}', '{}', '{}')
                    """
                )

            AnalysisService(self._settings(tmpdir))
            service = AnalysisService(self._settings(tmpdir))
            with service._connect() as connection:
                columns = {
                    row["name"]
                    for row in connection.execute("PRAGMA table_info(analysis_outputs)").fetchall()
                }
                indexes = {
                    row["name"]
                    for row in connection.execute("PRAGMA index_list(analysis_outputs)").fetchall()
                }
                legacy_row = connection.execute(
                    "SELECT display_name, registration_key FROM analysis_outputs WHERE id = 'analysis-output:legacy'"
                ).fetchone()

        self.assertIn("registration_key", columns)
        self.assertIn("idx_analysis_outputs_registration", indexes)
        self.assertEqual(legacy_row["display_name"], "Legacy Library Sizes")
        self.assertIsNone(legacy_row["registration_key"])

    def test_worker_status_becomes_offline_when_heartbeat_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            service.register_worker({"worker_id": "worker-1", "display_name": "Worker"})
            with service._connect() as connection:
                connection.execute(
                    "UPDATE analysis_workers SET last_heartbeat = '2020-01-01T00:00:00+00:00' WHERE worker_id = 'worker-1'"
                )
            worker = service.get_worker("worker-1")

        self.assertFalse(worker["connected"])
        self.assertEqual(worker["status"], "offline")

    def test_deseq2_workflow_has_single_active_registry_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            with service._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO analysis_workflows
                        (id, stable_key, name, description, workflow_version, category, modality,
                         parameter_schema_json, resource_request_json, supported_runtimes_json, enabled)
                    VALUES ('legacy-deseq2', 'deseq2_differential_expression', 'DESeq2 Differential Expression',
                            'Legacy scaffold', '0.1.0-scaffold', 'Bulk RNA-seq', 'bulk_rna_seq',
                            '{}', '{}', '[]', 1)
                    """
                )
            AnalysisService(self._settings(tmpdir))
            workflows = service.list_workflows()

        deseq2_cards = [workflow for workflow in workflows if workflow["name"] == "DESeq2 Differential Expression"]
        self.assertEqual([workflow["stable_key"] for workflow in deseq2_cards], ["bulk_rnaseq_deseq2"])
        self.assertEqual(deseq2_cards[0]["status"], "unavailable")

    def test_deseq2_workflow_ready_only_with_exact_fresh_worker_capability(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            unavailable = next(workflow for workflow in service.list_workflows() if workflow["stable_key"] == "bulk_rnaseq_deseq2")
            service.register_worker(
                {
                    "worker_id": "worker-1",
                    "display_name": "Worker",
                    "supported_workflows": ["bulk_rnaseq_validation_qc"],
                }
            )
            still_unavailable = next(workflow for workflow in service.list_workflows() if workflow["stable_key"] == "bulk_rnaseq_deseq2")
            service.register_worker(
                {
                    "worker_id": "worker-1",
                    "display_name": "Worker",
                    "supported_workflows": ["bulk_rnaseq_validation_qc", "bulk_rnaseq_deseq2"],
                    "supported_runtimes": ["python", "r", "deseq2"],
                    "software_versions": {"R": "4.x", "DESeq2": "1.x"},
                }
            )
            ready = next(workflow for workflow in service.list_workflows() if workflow["stable_key"] == "bulk_rnaseq_deseq2")

        self.assertEqual(unavailable["status"], "unavailable")
        self.assertEqual(still_unavailable["status"], "unavailable")
        self.assertEqual(ready["status"], "installed")

    def test_queued_deseq2_job_reports_missing_worker_dependency_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            service.register_worker(
                {
                    "worker_id": "worker-1",
                    "display_name": "Worker",
                    "supported_workflows": ["bulk_rnaseq_validation_qc"],
                }
            )
            dataset = service.register_server_dataset(
                user_id="user:pi-owner",
                payload={
                    "display_name": "Bulk SAG GRKi",
                    "counts_path": "bulk/counts.tsv",
                    "metadata_path": "bulk/samples.csv",
                },
            )
            job = service.create_job(
                user_id="user:pi-owner",
                dataset_id=dataset["id"],
                workflow_key="bulk_rnaseq_deseq2",
                parameters={
                    "contrast_factor": "condition",
                    "numerator_level": "SAG",
                    "denominator_level": "DMSO",
                },
            )
            claimed = service.claim_next_job("worker-1")
            queued = service.get_job("user:pi-owner", job["id"])

        self.assertIsNone(claimed)
        self.assertIn("Missing R/DESeq2 dependencies", queued["queue_reason"])

    def test_worker_authentication_rejects_bad_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            with self.assertRaises(AnalysisAuthorizationError):
                service.require_worker_token("wrong")

    def test_register_server_local_bulk_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, root = self._fixture(tmpdir)
            dataset = service.register_server_dataset(
                user_id="user:pi-owner",
                payload={
                    "display_name": "Bulk SAG GRKi",
                    "counts_path": "bulk/counts.tsv",
                    "metadata_path": "bulk/samples.csv",
                    "organism": "human",
                },
            )
            self.assertTrue((root / "bulk/counts.tsv").exists())

        self.assertEqual(dataset["display_name"], "Bulk SAG GRKi")

    def test_public_geo_search_and_import_registers_bulk_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, root = self._fixture(tmpdir)
            records = service.public_geo_datasets("retinal organoid")
            fixture = next(
                record
                for record in service.public_geo_datasets("BMP4 response")
                if record["accession"] == "GSE-MUNDI-RET-ORG-BULK"
            )
            dataset = service.import_public_geo_dataset(
                "user:pi-owner",
                fixture["accession"],
            )
            again = service.import_public_geo_dataset(
                "user:pi-owner",
                fixture["accession"],
            )
            counts_exists = (root / dataset["counts_path"]).exists()
            metadata_exists = (root / dataset["metadata_path"]).exists()

        self.assertGreaterEqual(len(records), 1)
        self.assertIn("GSE119274", {record["accession"] for record in records})
        stress_records = service.public_geo_datasets("stress test")
        stress_record = next(record for record in stress_records if record["accession"] == "GSE101986")
        self.assertEqual(stress_record["sample_count"], 24)
        self.assertIn("bulk_rnaseq_deseq2", stress_record["recommended_workflows"])
        self.assertEqual(dataset["modality"], "bulk_rna_seq")
        self.assertEqual(dataset["source_type"], "public_geo")
        self.assertEqual(dataset["sample_count"], 6)
        self.assertTrue(counts_exists)
        self.assertTrue(metadata_exists)
        self.assertEqual(again["id"], dataset["id"])
        self.assertEqual(again["import_status"], "already_imported")
        self.assertTrue(dataset["server_local"])
        self.assertEqual(dataset["features_count"], 7)
        self.assertTrue(dataset["metadata_summary"]["validation"]["sample_names_match"])
        self.assertEqual(dataset["metadata_summary"]["validation"]["duplicate_gene_count"], 0)

    def test_raw_count_dataset_allows_deseq2_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            dataset = service.register_server_dataset(
                user_id="user:pi-owner",
                payload={
                    "display_name": "Raw Counts",
                    "counts_path": "bulk/counts.tsv",
                    "metadata_path": "bulk/samples.csv",
                    "source_data_kind": "raw_counts",
                },
            )
            job = service.create_job(
                user_id="user:pi-owner",
                dataset_id=dataset["id"],
                workflow_key="bulk_rnaseq_deseq2",
                parameters={
                    "sample_id_column": "sample",
                    "design_factors": ["condition"],
                    "contrast_factor": "condition",
                    "numerator_level": "SAG",
                    "denominator_level": "DMSO",
                },
            )

        self.assertEqual(job["workflow_id"], "bulk_rnaseq_deseq2")
        self.assertEqual(job["status"], "queued")

    def test_normalized_cpm_dataset_blocks_deseq2_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            public_records = service.public_geo_datasets("GSE229682")
            gse229682 = next(record for record in public_records if record["accession"] == "GSE229682")
            dataset = service.register_server_dataset(
                user_id="user:pi-owner",
                payload={
                    "display_name": "CPM-only Dataset",
                    "counts_path": "bulk/counts.tsv",
                    "metadata_path": "bulk/samples.csv",
                    "source_data_kind": "normalized_cpm",
                    "exploratory_only": True,
                },
            )

            with self.assertRaisesRegex(AnalysisValidationError, "DESeq2 requires raw integer counts"):
                service.create_job(
                    user_id="user:pi-owner",
                    dataset_id=dataset["id"],
                    workflow_key="bulk_rnaseq_deseq2",
                    parameters={
                        "sample_id_column": "sample",
                        "design_factors": ["condition"],
                        "contrast_factor": "condition",
                        "numerator_level": "SAG",
                        "denominator_level": "DMSO",
                    },
                )

        self.assertTrue(gse229682["exploratory_only"])
        self.assertEqual(gse229682["source_data_kind"], "normalized_cpm")
        self.assertNotIn("bulk_rnaseq_deseq2", gse229682["recommended_workflows"])
        self.assertTrue(dataset["exploratory_only"])

    def test_zero_count_sample_requires_explicit_exclusion_for_deseq2(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, root = self._fixture(tmpdir)
            zero_counts = root / "bulk" / "counts_with_zero.tsv"
            with zero_counts.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter="\t")
                writer.writerow(["gene", "DMSO_1", "SAG_1", "zero_sample"])
                writer.writerow(["BMP4", "10", "28", "0"])
                writer.writerow(["POU4F2", "2", "9", "0"])
                writer.writerow(["RBPMS", "3", "12", "0"])
                writer.writerow(["GAPDH", "100", "110", "0"])
            metadata = root / "bulk" / "samples_with_zero.csv"
            with metadata.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["sample", "condition"])
                writer.writeheader()
                writer.writerow({"sample": "DMSO_1", "condition": "DMSO"})
                writer.writerow({"sample": "SAG_1", "condition": "SAG"})
                writer.writerow({"sample": "zero_sample", "condition": "SAG"})
            dataset = service.register_server_dataset(
                user_id="user:pi-owner",
                payload={
                    "display_name": "Counts With Zero Sample",
                    "counts_path": "bulk/counts_with_zero.tsv",
                    "metadata_path": "bulk/samples_with_zero.csv",
                },
            )
            validation = dataset["metadata_summary"]["validation"]

            with self.assertRaisesRegex(AnalysisValidationError, "zero_sample"):
                service.create_job(
                    user_id="user:pi-owner",
                    dataset_id=dataset["id"],
                    workflow_key="bulk_rnaseq_deseq2",
                    parameters={
                        "sample_id_column": "sample",
                        "design_factors": ["condition"],
                        "contrast_factor": "condition",
                        "numerator_level": "SAG",
                        "denominator_level": "DMSO",
                    },
                )
            job = service.create_job(
                user_id="user:pi-owner",
                dataset_id=dataset["id"],
                workflow_key="bulk_rnaseq_deseq2",
                parameters={
                    "sample_id_column": "sample",
                    "design_factors": ["condition"],
                    "contrast_factor": "condition",
                    "numerator_level": "SAG",
                    "denominator_level": "DMSO",
                    "exclude_samples": ["zero_sample"],
                },
            )

        self.assertEqual(validation["zero_count_samples"], ["zero_sample"])
        self.assertEqual(job["parameters"]["exclude_samples"], ["zero_sample"])

    def test_path_allowlist_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            with self.assertRaisesRegex(AnalysisValidationError, "safe relative"):
                service.register_server_dataset(
                    user_id="user:pi-owner",
                    payload={
                        "display_name": "Bad",
                        "counts_path": "../secret.tsv",
                        "metadata_path": "bulk/samples.csv",
                    },
                )

    def test_browse_approved_root_returns_dataset_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            browse = service.browse_storage_location("analysis-storage:default")

        self.assertEqual(browse["storage_location_id"], "analysis-storage:default")
        bulk = next(item for item in browse["entries"] if item["name"] == "bulk")
        self.assertTrue(bulk["is_directory"])
        self.assertEqual(bulk["candidate"]["modality"], "bulk_rna_seq")

    def test_job_claim_progress_completion_and_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            service.register_worker(
                {
                    "worker_id": "worker-1",
                    "display_name": "Lab Analysis Server",
                    "supported_workflows": ["bulk_rnaseq_validation_qc"],
                    "supported_runtimes": ["python"],
                }
            )
            dataset = service.register_server_dataset(
                user_id="user:pi-owner",
                payload={
                    "display_name": "Bulk SAG GRKi",
                    "counts_path": "bulk/counts.tsv",
                    "metadata_path": "bulk/samples.csv",
                },
            )
            job = service.create_job(
                user_id="user:pi-owner",
                dataset_id=dataset["id"],
                workflow_key="bulk_rnaseq_validation_qc",
                parameters={"sample_id_column": "sample", "group_column": "condition"},
            )
            claimed = service.claim_next_job("worker-1")
            running = service.update_job_progress(
                "worker-1",
                job["id"],
                status="running",
                progress=0.5,
                current_stage="Validating counts",
            )
            complete = service.run_claimed_job_once("worker-1")
            outputs = service.outputs_for_job("user:pi-owner", job["id"])
            stored_job = service.get_job("user:pi-owner", job["id"])

        self.assertEqual(claimed["id"], job["id"])
        self.assertEqual(running["status"], "running")
        self.assertIsNone(complete)
        self.assertEqual(stored_job["status"], "running")
        self.assertEqual(outputs, [])

    def test_queued_job_survives_service_reconstruction(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            dataset = service.register_server_dataset(
                user_id="user:pi-owner",
                payload={
                    "display_name": "Bulk SAG GRKi",
                    "counts_path": "bulk/counts.tsv",
                    "metadata_path": "bulk/samples.csv",
                },
            )
            job = service.create_job(
                user_id="user:pi-owner",
                dataset_id=dataset["id"],
                workflow_key="bulk_rnaseq_validation_qc",
                parameters={"sample_id_column": "sample", "group_column": "condition"},
            )

            restarted = AnalysisService(self._settings(tmpdir))
            stored = restarted.get_job("user:pi-owner", job["id"])

        self.assertEqual(stored["status"], "queued")
        self.assertEqual(stored["retry_count"], 0)

    def test_stale_active_job_is_recovered_after_worker_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            service.register_worker(
                {
                    "worker_id": "worker-1",
                    "display_name": "Lab Analysis Server",
                    "supported_workflows": ["bulk_rnaseq_validation_qc"],
                    "supported_runtimes": ["python"],
                }
            )
            dataset = service.register_server_dataset(
                user_id="user:pi-owner",
                payload={
                    "display_name": "Bulk SAG GRKi",
                    "counts_path": "bulk/counts.tsv",
                    "metadata_path": "bulk/samples.csv",
                },
            )
            job = service.create_job(
                user_id="user:pi-owner",
                dataset_id=dataset["id"],
                workflow_key="bulk_rnaseq_validation_qc",
                parameters={"sample_id_column": "sample", "group_column": "condition"},
            )
            service.claim_next_job("worker-1")
            with service._connect() as connection:
                connection.execute(
                    """
                    UPDATE analysis_workers SET last_heartbeat = '2020-01-01T00:00:00+00:00'
                    WHERE worker_id = 'worker-1'
                    """
                )
                connection.execute(
                    """
                    UPDATE analysis_jobs
                    SET status = 'running', started_at = '2020-01-01T00:00:00+00:00',
                        last_worker_heartbeat = '2020-01-01T00:00:00+00:00'
                    WHERE id = ?
                    """,
                    (job["id"],),
                )

            restarted = AnalysisService(self._settings(tmpdir))
            recovered = restarted.get_job("user:pi-owner", job["id"])

        self.assertEqual(recovered["status"], "queued")
        self.assertIsNone(recovered["worker_id"])
        self.assertEqual(recovered["retry_count"], 1)

    def test_cancel_running_job_is_honored_before_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            service.register_worker(
                {
                    "worker_id": "worker-1",
                    "display_name": "Lab Analysis Server",
                    "supported_workflows": ["bulk_rnaseq_validation_qc"],
                    "supported_runtimes": ["python"],
                }
            )
            dataset = service.register_server_dataset(
                user_id="user:pi-owner",
                payload={
                    "display_name": "Bulk SAG GRKi",
                    "counts_path": "bulk/counts.tsv",
                    "metadata_path": "bulk/samples.csv",
                },
            )
            job = service.create_job(
                user_id="user:pi-owner",
                dataset_id=dataset["id"],
                workflow_key="bulk_rnaseq_validation_qc",
                parameters={"sample_id_column": "sample", "group_column": "condition"},
            )
            service.claim_next_job("worker-1")
            service.update_job_progress("worker-1", job["id"], status="running", progress=0.5)
            service.cancel_job("user:pi-owner", job["id"])
            cancelled = service.complete_job("worker-1", job["id"], [])

        self.assertEqual(cancelled["status"], "cancelled")
        self.assertTrue(cancelled["cancellation_requested"])

    def test_transient_failure_requeues_until_retry_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            service.register_worker(
                {
                    "worker_id": "worker-1",
                    "display_name": "Lab Analysis Server",
                    "supported_workflows": ["bulk_rnaseq_validation_qc"],
                    "supported_runtimes": ["python"],
                }
            )
            dataset = service.register_server_dataset(
                user_id="user:pi-owner",
                payload={
                    "display_name": "Bulk SAG GRKi",
                    "counts_path": "bulk/counts.tsv",
                    "metadata_path": "bulk/samples.csv",
                },
            )
            job = service.create_job(
                user_id="user:pi-owner",
                dataset_id=dataset["id"],
                workflow_key="bulk_rnaseq_validation_qc",
                parameters={"sample_id_column": "sample", "group_column": "condition"},
            )
            service.claim_next_job("worker-1")
            retried = service.fail_job("worker-1", job["id"], "Temporary timeout while reading dataset")
            service.claim_next_job("worker-1")
            failed = service.fail_job("worker-1", job["id"], "permanent malformed matrix")

        self.assertEqual(retried["status"], "queued")
        self.assertEqual(retried["retry_count"], 1)
        self.assertEqual(failed["status"], "failed")

    def test_output_registration_requires_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            with service._connect() as connection:
                with self.assertRaisesRegex(AnalysisValidationError, "does not exist"):
                    service._insert_output(
                        connection,
                        job_id="analysis-job:missing",
                        dataset_id="analysis-dataset:missing",
                        output_type="file",
                        display_name="Missing file",
                        path=service.outputs_dir / "missing.txt",
                    )

    def test_storage_report_detects_orphans_and_temp_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            temp_dir = service.base_dir / "tmp-stale"
            temp_dir.mkdir(parents=True)
            with service._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO analysis_outputs
                        (id, job_id, dataset_id, registration_key, output_type, display_name,
                         storage_uri, structured_json, viewer_config_json, provenance_json)
                    VALUES ('analysis-output:orphan', 'analysis-job:missing', 'analysis-dataset:missing',
                            'orphan', 'file', 'Missing output', 'outputs/missing.txt', '{}', '{}', '{}')
                    """
                )
            report = service.storage_report()
            cleanup = service.cleanup_temporary_work_dirs()

        self.assertEqual(len(report["orphaned_outputs"]), 1)
        self.assertEqual(report["temporary_work_dirs"]["count"], 1)
        self.assertEqual(cleanup["count"], 1)

    def test_worker_vertical_slice_runs_bulk_qc(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            service.register_worker(
                {
                    "worker_id": "worker-1",
                    "display_name": "Lab Analysis Server",
                    "supported_workflows": ["bulk_rnaseq_validation_qc"],
                    "supported_runtimes": ["python"],
                }
            )
            dataset = service.register_server_dataset(
                user_id="user:pi-owner",
                payload={
                    "display_name": "Bulk SAG GRKi",
                    "counts_path": "bulk/counts.tsv",
                    "metadata_path": "bulk/samples.csv",
                },
            )
            job = service.create_job(
                user_id="user:pi-owner",
                dataset_id=dataset["id"],
                workflow_key="bulk_rnaseq_validation_qc",
                parameters={"sample_id_column": "sample", "group_column": "condition"},
            )
            completed = service.run_claimed_job_once("worker-1")
            outputs = service.outputs_for_job("user:pi-owner", job["id"])

        self.assertEqual(completed["status"], "complete")
        self.assertEqual(completed["progress"], 1)
        self.assertEqual({output["output_type"] for output in outputs}, {"qc_report", "table", "provenance"})
        qc = next(output for output in outputs if output["output_type"] == "qc_report")
        self.assertTrue(qc["structured"]["summary"]["integer_counts_valid"])
        self.assertTrue(qc["provenance"]["source_files_remain_server_local"])

    def test_deseq2_workflow_registration_and_demo_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            service.register_worker(
                {
                    "worker_id": "worker-1",
                    "display_name": "Lab Analysis Server",
                    "supported_workflows": ["bulk_rnaseq_validation_qc", "bulk_rnaseq_deseq2"],
                    "supported_runtimes": ["python", "r", "deseq2"],
                    "software_versions": {"R": "4.x", "DESeq2": "1.x"},
                }
            )
            dataset = service.register_server_dataset(
                user_id="user:pi-owner",
                payload={
                    "display_name": "Bulk SAG GRKi",
                    "counts_path": "bulk/counts.tsv",
                    "metadata_path": "bulk/samples.csv",
                },
            )
            job = service.create_job(
                user_id="user:pi-owner",
                dataset_id=dataset["id"],
                workflow_key="bulk_rnaseq_deseq2",
                parameters={
                    "sample_id_column": "sample",
                    "design_factors": ["condition"],
                    "contrast_factor": "condition",
                    "numerator_level": "SAG",
                    "denominator_level": "DMSO",
                    "min_total_count": 1,
                    "min_samples_expressing": 1,
                    "alpha": 0.1,
                    "lfc_threshold": 0.5,
                },
            )
            completed = service.run_claimed_job_once("worker-1")
            outputs = service.outputs_for_job("user:pi-owner", job["id"])
            self.assertEqual(completed["status"], "complete")
            self.assertIn("bulk_rnaseq_deseq2", [workflow["stable_key"] for workflow in service.list_workflows()])
            output_types = {output["output_type"] for output in outputs}
            self.assertIn("differential_expression_table", output_types)
            self.assertIn("interactive_plot", output_types)
            self.assertIn("heatmap", output_types)
            self.assertIn("provenance", output_types)
            de_table = next(output for output in outputs if output["output_type"] == "differential_expression_table")
            self.assertIn("log2FoldChange", de_table["structured"]["columns"])
            volcano = next(output for output in outputs if output["display_name"] == "Volcano Plot")
            self.assertIn("log2FoldChange", volcano["structured"]["points"][0])
            self.assertIn("neg_log10_padj", volcano["structured"]["points"][0])
            plot_types = {
                output["structured"].get("plot_type")
                for output in outputs
                if output["structured"].get("plot_type")
            }
            self.assertIn("dispersion_plot", plot_types)
            self.assertIn("library_size_plot", plot_types)
            self.assertTrue(de_table["provenance"]["source_files_remain_server_local"])

    def test_deseq2_invalid_contrast_fails_with_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            service.register_worker(
                {
                    "worker_id": "worker-1",
                    "display_name": "Lab Analysis Server",
                    "supported_workflows": ["bulk_rnaseq_deseq2"],
                    "supported_runtimes": ["python", "r", "deseq2"],
                }
            )
            dataset = service.register_server_dataset(
                user_id="user:pi-owner",
                payload={
                    "display_name": "Bulk SAG GRKi",
                    "counts_path": "bulk/counts.tsv",
                    "metadata_path": "bulk/samples.csv",
                },
            )
            with self.assertRaisesRegex(AnalysisValidationError, "Numerator level"):
                service.create_job(
                    user_id="user:pi-owner",
                    dataset_id=dataset["id"],
                    workflow_key="bulk_rnaseq_deseq2",
                    parameters={
                        "sample_id_column": "sample",
                        "design_factors": ["condition"],
                        "contrast_factor": "condition",
                        "numerator_level": "missing",
                        "denominator_level": "DMSO",
                    },
                )

    def test_output_detail_rename_references_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            service.register_worker(
                {
                    "worker_id": "worker-1",
                    "display_name": "Lab Analysis Server",
                    "supported_workflows": ["bulk_rnaseq_validation_qc"],
                    "supported_runtimes": ["python"],
                }
            )
            dataset = service.register_server_dataset(
                user_id="user:pi-owner",
                payload={
                    "display_name": "Bulk SAG GRKi",
                    "counts_path": "bulk/counts.tsv",
                    "metadata_path": "bulk/samples.csv",
                },
            )
            job = service.create_job(
                user_id="user:pi-owner",
                dataset_id=dataset["id"],
                workflow_key="bulk_rnaseq_validation_qc",
                parameters={"sample_id_column": "sample", "group_column": "condition"},
            )
            service.run_claimed_job_once("worker-1")
            output = next(
                item
                for item in service.outputs_for_job("user:pi-owner", job["id"])
                if item["output_type"] == "qc_report"
            )

            detail = service.get_output("user:pi-owner", output["id"])
            renamed = service.rename_output("user:pi-owner", output["id"], "Reviewed QC")
            linked = service.record_notebook_reference(
                "user:pi-owner",
                output_id=output["id"],
                notebook_id="notebook:test",
                reference_type="linked",
                caption="QC summary",
            )
            snapshot = service.record_notebook_reference(
                "user:pi-owner",
                output_id=output["id"],
                experiment_id="experiment:test",
                reference_type="snapshot",
            )
            references = service.references_for_output("user:pi-owner", output["id"])
            with self.assertRaisesRegex(AnalysisValidationError, "referenced"):
                service.delete_output("user:pi-owner", output["id"])
            deleted = service.delete_output(
                "user:pi-owner",
                output["id"],
                reference_mode="remove_references",
            )

        self.assertEqual(detail["dataset"]["display_name"], "Bulk SAG GRKi")
        self.assertEqual(renamed["display_name"], "Reviewed QC")
        self.assertEqual(linked["reference_type"], "linked")
        self.assertEqual(snapshot["reference_type"], "snapshot")
        self.assertEqual(len(references), 2)
        self.assertTrue(deleted["deleted"])

    def test_output_registration_is_idempotent_within_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            service.register_worker(
                {
                    "worker_id": "worker-1",
                    "display_name": "Lab Analysis Server",
                    "supported_workflows": ["bulk_rnaseq_validation_qc"],
                    "supported_runtimes": ["python"],
                }
            )
            dataset = service.register_server_dataset(
                user_id="user:pi-owner",
                payload={
                    "display_name": "Bulk SAG GRKi",
                    "counts_path": "bulk/counts.tsv",
                    "metadata_path": "bulk/samples.csv",
                },
            )
            job = service.create_job(
                user_id="user:pi-owner",
                dataset_id=dataset["id"],
                workflow_key="bulk_rnaseq_validation_qc",
                parameters={"sample_id_column": "sample", "group_column": "condition"},
            )
            with service._connect() as connection:
                service._insert_output(
                    connection,
                    job_id=job["id"],
                    dataset_id=dataset["id"],
                    output_type="table",
                    display_name="Library Sizes",
                    structured={"columns": ["sample"], "rows": [{"sample": "A"}]},
                    registration_key="library_sizes",
                )
                service._insert_output(
                    connection,
                    job_id=job["id"],
                    dataset_id=dataset["id"],
                    output_type="table",
                    display_name="Library Sizes",
                    structured={"columns": ["sample"], "rows": [{"sample": "B"}]},
                    registration_key="library_sizes",
                )
            outputs = service.outputs_for_job("user:pi-owner", job["id"])

        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0]["structured"]["rows"][0]["sample"], "B")

    def test_output_groups_are_dataset_job_output_ordered(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            service.register_worker(
                {
                    "worker_id": "worker-1",
                    "display_name": "Lab Analysis Server",
                    "supported_workflows": ["bulk_rnaseq_validation_qc"],
                    "supported_runtimes": ["python"],
                }
            )
            dataset = service.register_server_dataset(
                user_id="user:pi-owner",
                payload={
                    "display_name": "Bulk SAG GRKi",
                    "counts_path": "bulk/counts.tsv",
                    "metadata_path": "bulk/samples.csv",
                },
            )
            for _ in range(2):
                service.create_job(
                    user_id="user:pi-owner",
                    dataset_id=dataset["id"],
                    workflow_key="bulk_rnaseq_validation_qc",
                    parameters={"sample_id_column": "sample", "group_column": "condition"},
                )
                service.run_claimed_job_once("worker-1")
            groups = service.output_groups("user:pi-owner")

        self.assertEqual(len(groups), 2)
        self.assertTrue(all(group["dataset"]["display_name"] == "Bulk SAG GRKi" for group in groups))
        self.assertTrue(all(len(group["outputs"]) == 3 for group in groups))

    def test_output_browser_and_demo_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            library = service.demo_library()
            install = service.install_demo_workspace("user:pi-owner")
            outputs = service.list_outputs("user:pi-owner", query="QC")
            datasets = service.list_datasets("user:pi-owner")

        self.assertIn("PBMC 3k", [item["display_name"] for item in library["datasets"]])
        self.assertIn("Demo Workspace", install["workspace"]["display_name"])
        self.assertGreaterEqual(len(outputs), 1)
        self.assertIn("Small PBMC Bulk", [item["display_name"] for item in datasets])

    def test_scaffolded_workflow_cannot_execute_yet(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service, _root = self._fixture(tmpdir)
            dataset = service.register_server_dataset(
                user_id="user:pi-owner",
                payload={
                    "display_name": "Bulk SAG GRKi",
                    "counts_path": "bulk/counts.tsv",
                    "metadata_path": "bulk/samples.csv",
                },
            )
            with self.assertRaisesRegex(AnalysisValidationError, "scaffolded"):
                service.create_job(
                    user_id="user:pi-owner",
                    dataset_id=dataset["id"],
                    workflow_key="scanpy_standard_pipeline",
                )

    def test_analysis_routes_are_registered(self) -> None:
        from app.main import app

        routes = {(route.path, ",".join(sorted(getattr(route, "methods", [])))) for route in app.routes}

        self.assertTrue(any(path == "/mobile/analysis/workers" and "GET" in methods for path, methods in routes))
        self.assertTrue(any(path == "/worker/register" and "POST" in methods for path, methods in routes))
        self.assertTrue(any(path == "/mobile/analysis/demo-library" and "GET" in methods for path, methods in routes))
        self.assertTrue(any(path == "/mobile/analysis/output-groups" and "GET" in methods for path, methods in routes))
        self.assertTrue(any(path == "/mobile/analysis/outputs/{output_id}" and "PATCH" in methods for path, methods in routes))
        self.assertTrue(any(path == "/mobile/analysis/notebook-references" and "POST" in methods for path, methods in routes))
        self.assertTrue(any(path == "/mobile/analysis/storage-report" and "GET" in methods for path, methods in routes))


def _write_bulk_fixture(root: Path) -> None:
    bulk = root / "bulk"
    bulk.mkdir(parents=True)
    with (bulk / "counts.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["gene", "DMSO_1", "SAG_1", "SAG_2"])
        writer.writerow(["BMP4", "10", "28", "31"])
        writer.writerow(["POU4F2", "2", "9", "8"])
        writer.writerow(["RBPMS", "3", "12", "11"])
        writer.writerow(["GAPDH", "100", "110", "115"])
    with (bulk / "samples.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sample", "condition"])
        writer.writeheader()
        writer.writerow({"sample": "DMSO_1", "condition": "DMSO"})
        writer.writerow({"sample": "SAG_1", "condition": "SAG"})
        writer.writerow({"sample": "SAG_2", "condition": "SAG"})


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
