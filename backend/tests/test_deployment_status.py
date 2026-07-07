"""Tests for lab-server deployment status helpers."""

from __future__ import annotations

import unittest

from app.config import Settings


class DeploymentStatusTests(unittest.TestCase):
    """Deployment status should report safe warnings without secrets."""

    def test_localhost_mode_warns(self) -> None:
        from app import main

        original = main.settings
        try:
            main.settings = Settings(api_host="127.0.0.1", api_port=8001, public_base_url="")
            status = main._deployment_status()
        finally:
            main.settings = original

        self.assertEqual(status["mode"], "local_dev")
        self.assertFalse(status["https_enabled"])
        self.assertTrue(status["warnings"])

    def test_public_https_mode(self) -> None:
        from app import main

        original = main.settings
        try:
            main.settings = Settings(
                api_host="0.0.0.0",
                api_port=8001,
                public_base_url="https://researchos.example.edu",
                microsoft_redirect_uri="https://researchos.example.edu/auth/callback",
            )
            status = main._deployment_status()
        finally:
            main.settings = original

        self.assertEqual(status["mode"], "lab_server")
        self.assertTrue(status["public_base_url_configured"])
        self.assertTrue(status["https_enabled"])
        self.assertEqual(status["warnings"], [])


if __name__ == "__main__":
    unittest.main()
