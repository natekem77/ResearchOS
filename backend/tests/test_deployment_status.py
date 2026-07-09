"""Tests for lab-server deployment status helpers."""

from __future__ import annotations

import unittest

from starlette.requests import Request

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

    def test_mobile_connection_info_warns_for_localhost(self) -> None:
        from app import main

        original = main.settings
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/mobile/connection-info",
            "headers": [],
            "scheme": "http",
            "server": ("127.0.0.1", 8001),
            "client": ("testclient", 123),
            "query_string": b"",
        }
        try:
            main.settings = Settings(api_host="127.0.0.1", api_port=8001, public_base_url="")
            payload = main.mobile_connection_info(Request(scope))
        finally:
            main.settings = original

        self.assertEqual(payload["server_name"], "ResearchOS")
        self.assertEqual(payload["current_host"], "127.0.0.1")
        self.assertEqual(payload["current_port"], 8001)
        self.assertIn("recommended_mobile_url", payload)
        self.assertTrue(any("iPhone" in warning for warning in payload["warnings"]))


if __name__ == "__main__":
    unittest.main()
