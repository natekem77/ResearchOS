import os
import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.imaging import ImagingService, ImagingValidationError
from imaging_worker.fiji_runner import FijiRunner, tiny_tiff


class ImagingServiceTests(unittest.TestCase):
    def _settings(self, tmpdir: str) -> Settings:
        return Settings(
            data_dir=tmpdir,
            database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}",
        )

    def test_upload_png_extracts_basic_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ImagingService(self._settings(tmpdir))
            asset = service.create_asset(
                user_id="user:pi-owner",
                filename="preview.png",
                data=_tiny_png(),
                mime_type="image/png",
            )

        self.assertEqual(asset["format"], "PNG")
        self.assertEqual(asset["width"], 1)
        self.assertEqual(asset["height"], 1)
        self.assertEqual(asset["metadata"]["metadata_status"], "basic_png")

    def test_reject_unsupported_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ImagingService(self._settings(tmpdir))
            with self.assertRaisesRegex(ImagingValidationError, "Unsupported"):
                service.create_asset(
                    user_id="user:pi-owner",
                    filename="notes.txt",
                    data=b"not image",
                    mime_type="text/plain",
                )

    def test_reject_oversized_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ImagingService(self._settings(tmpdir))
            service.max_file_bytes = 2
            with self.assertRaisesRegex(ImagingValidationError, "too large"):
                service.create_asset(
                    user_id="user:pi-owner",
                    filename="large.png",
                    data=b"123",
                    mime_type="image/png",
                )

    def test_upload_tiff_keeps_metadata_unavailable_nonfatal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ImagingService(self._settings(tmpdir))
            asset = service.create_asset(
                user_id="user:pi-owner",
                filename="cells.ome.tif",
                data=b"tiff",
                mime_type="image/tiff",
            )

        self.assertEqual(asset["format"], "OME.TIF")
        self.assertEqual(asset["metadata"]["metadata_status"], "unavailable")

    def test_generate_preview_job_fails_explicitly_without_fiji(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ImagingService(self._settings(tmpdir))
            asset = service.create_asset(
                user_id="user:pi-owner",
                filename="cells.tif",
                data=tiny_tiff(),
                mime_type="image/tiff",
            )
            raw_path = Path(tmpdir) / "imaging" / asset["storage_uri"]
            original_bytes = raw_path.read_bytes()
            job = service.create_job(
                user_id="user:pi-owner",
                asset_id=asset["id"],
                workflow_key="generate_preview",
            )
            original_path = os.environ.pop("MUNDI_FIJI_PATH", None)
            try:
                processed = service.run_job_once("test-worker")
            finally:
                if original_path is not None:
                    os.environ["MUNDI_FIJI_PATH"] = original_path
            raw_after = raw_path.read_bytes()

        self.assertEqual(processed["status"], "failed")
        self.assertEqual(processed["error_code"], "worker_error")
        self.assertIn("MUNDI_FIJI_PATH", processed["safe_error_message"])
        self.assertEqual(raw_after, original_bytes)

    def test_only_generate_preview_workflow_is_registered(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ImagingService(self._settings(tmpdir))
            workflows = service.list_workflows()
            asset = service.create_asset(
                user_id="user:pi-owner",
                filename="cells.tif",
                data=tiny_tiff(),
                mime_type="image/tiff",
            )

            with self.assertRaisesRegex(ImagingValidationError, "Unknown"):
                service.create_job(
                    user_id="user:pi-owner",
                    asset_id=asset["id"],
                    workflow_key="threshold_area_measurement",
                )

        self.assertEqual([workflow["stable_key"] for workflow in workflows], ["generate_preview"])

    def test_output_provenance_and_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ImagingService(self._settings(tmpdir))
            asset = service.create_asset(
                user_id="user:pi-owner",
                filename="cells.tif",
                data=b"raw-tiff-bytes",
                mime_type="image/tiff",
            )
            job = service.create_job(
                user_id="user:pi-owner",
                asset_id=asset["id"],
                workflow_key="generate_preview",
            )

            with self.assertRaisesRegex(ImagingValidationError, "not found"):
                service.get_asset("user:other", asset["id"])

            original_path = os.environ.pop("MUNDI_FIJI_PATH", None)
            try:
                service.run_job_once("test-worker")
            finally:
                if original_path is not None:
                    os.environ["MUNDI_FIJI_PATH"] = original_path
            outputs = service.outputs_for_job("user:pi-owner", job["id"])

        self.assertEqual(outputs, [])

    def test_parameter_validation_and_worker_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ImagingService(self._settings(tmpdir))
            asset = service.create_asset(
                user_id="user:pi-owner",
                filename="cells.nd2",
                data=b"nd2",
                mime_type="application/octet-stream",
            )
            with self.assertRaisesRegex(ImagingValidationError, "Unsupported parameter"):
                service.create_job(
                    user_id="user:pi-owner",
                    asset_id=asset["id"],
                    workflow_key="generate_preview",
                    parameters={"macro": "run arbitrary code"},
                )
            status = service.record_worker_heartbeat("test-worker")

        self.assertTrue(status["connected"])
        self.assertEqual(status["worker_id"], "test-worker")


@unittest.skipUnless(os.environ.get("MUNDI_FIJI_PATH"), "MUNDI_FIJI_PATH is required for real Fiji integration test.")
class FijiRunnerIntegrationTests(unittest.TestCase):
    def test_generate_preview_executes_real_fiji(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.tif"
            output_path = Path(tmpdir) / "preview.png"
            input_path.write_bytes(tiny_tiff())

            result = FijiRunner(os.environ["MUNDI_FIJI_PATH"], timeout_seconds=120).generate_preview(
                input_path=input_path,
                output_path=output_path,
            )

            self.assertEqual(result.returncode, 0)
            self.assertTrue(output_path.exists())
            self.assertGreater(output_path.stat().st_size, 0)
            self.assertEqual(output_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_health_check_executes_preview_macro(self) -> None:
        status = FijiRunner(os.environ["MUNDI_FIJI_PATH"], timeout_seconds=120).health_check()

        self.assertTrue(status["executable_found"])
        self.assertTrue(status["fiji_launched"])
        self.assertTrue(status["macro_executed"])
        self.assertTrue(status["preview_generated"])
        self.assertTrue(status["fiji_exited"])


def _tiny_png() -> bytes:
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6360000002000100ffff03000006000557bfab0000000049454e44ae426082"
    )


if __name__ == "__main__":
    unittest.main()
