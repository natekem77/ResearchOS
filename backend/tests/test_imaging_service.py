import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.imaging import ImagingService, ImagingValidationError


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

    def test_job_worker_outputs_measurements_and_preserves_raw(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ImagingService(self._settings(tmpdir))
            asset = service.create_asset(
                user_id="user:pi-owner",
                filename="cells.tif",
                data=b"raw-tiff-bytes",
                mime_type="image/tiff",
            )
            raw_path = Path(tmpdir) / "imaging" / asset["storage_uri"]
            original_bytes = raw_path.read_bytes()
            job = service.create_job(
                user_id="user:pi-owner",
                asset_id=asset["id"],
                workflow_key="threshold_area_measurement",
                parameters={"threshold_method": "Otsu"},
            )
            processed = service.run_job_once("test-worker")
            outputs = service.outputs_for_job("user:pi-owner", job["id"])
            measurements = service.measurements_for_job("user:pi-owner", job["id"])
            raw_after = raw_path.read_bytes()

        self.assertEqual(processed["status"], "complete")
        self.assertEqual(raw_after, original_bytes)
        self.assertIn("mask_tiff", {item["output_type"] for item in outputs})
        self.assertIn("overlay_preview_png", {item["output_type"] for item in outputs})
        self.assertIn("measurements_csv", {item["output_type"] for item in outputs})
        self.assertIn("total_positive_area", {item["name"] for item in measurements})
        self.assertIn("percent_positive_area", {item["name"] for item in measurements})

    def test_allowlisted_workflows_create_expected_outputs(self) -> None:
        expectations = {
            "generate_preview": {"preview_png"},
            "max_intensity_projection": {"projected_tiff", "preview_png"},
            "split_channels": {"channel_tiff", "channel_preview_png"},
            "background_subtraction": {"processed_tiff", "preview_png"},
        }
        for workflow_key, expected_outputs in expectations.items():
            with self.subTest(workflow_key=workflow_key):
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
                        workflow_key=workflow_key,
                    )
                    processed = service.run_job_once("test-worker")
                    outputs = service.outputs_for_job("user:pi-owner", job["id"])

                self.assertEqual(processed["status"], "complete")
                self.assertTrue(expected_outputs.issubset({item["output_type"] for item in outputs}))
                self.assertIn("provenance", {item["output_type"] for item in outputs})

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
                workflow_key="max_intensity_projection",
            )
            service.run_job_once("test-worker")
            outputs = service.outputs_for_job("user:pi-owner", job["id"])
            provenance = next(item for item in outputs if item["output_type"] == "provenance")
            provenance_path = service.output_path("user:pi-owner", provenance["id"])

            with self.assertRaisesRegex(ImagingValidationError, "not found"):
                service.get_asset("user:other", asset["id"])
            with self.assertRaisesRegex(ImagingValidationError, "not found"):
                service.output_path("user:other", provenance["id"])

            self.assertEqual(provenance["filename"], "provenance.json")
            provenance_text = provenance_path.read_text(encoding="utf-8")
            self.assertIn("source_checksum", provenance_text)
            self.assertIn("checksum", provenance_text)

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


def _tiny_png() -> bytes:
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6360000002000100ffff03000006000557bfab0000000049454e44ae426082"
    )


if __name__ == "__main__":
    unittest.main()
