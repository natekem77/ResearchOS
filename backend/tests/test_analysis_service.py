import csv
import os
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
        self.assertTrue(dataset["server_local"])
        self.assertEqual(dataset["sample_count"], 3)
        self.assertEqual(dataset["features_count"], 4)

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
                    workflow_key="deseq2_differential_expression",
                )

    def test_analysis_routes_are_registered(self) -> None:
        from app.main import app

        routes = {(route.path, ",".join(sorted(getattr(route, "methods", [])))) for route in app.routes}

        self.assertTrue(any(path == "/mobile/analysis/workers" and "GET" in methods for path, methods in routes))
        self.assertTrue(any(path == "/worker/register" and "POST" in methods for path, methods in routes))
        self.assertTrue(any(path == "/mobile/analysis/demo-library" and "GET" in methods for path, methods in routes))


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
