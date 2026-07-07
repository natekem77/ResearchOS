"""Tests for OneNote readiness and redirect validation."""

from __future__ import annotations

import unittest

from app.config import Settings


class OneNoteReadinessTests(unittest.TestCase):
    """OneNote readiness should be explicit without exposing secrets."""

    def test_local_redirect_is_compatible_and_writeback_disabled(self) -> None:
        from app import main

        original = main.settings
        try:
            main.settings = Settings(
                api_host="127.0.0.1",
                api_port=8001,
                microsoft_client_id="test-client-id",
                microsoft_tenant_id="common",
                microsoft_redirect_uri="http://localhost:8001/auth/callback",
                graph_scopes="User.Read Notes.Read openid profile offline_access",
            )
            readiness = main._onenote_readiness()
        finally:
            main.settings = original

        self.assertTrue(readiness["microsoft_client_id_configured"])
        self.assertTrue(readiness["redirect_uri_compatible"])
        self.assertEqual(readiness["missing_required_scopes"], [])
        self.assertFalse(readiness["read_only_sync_ready"])
        self.assertTrue(readiness["write_back_disabled"])
        self.assertIn("Notes.Create", str(readiness["write_back_message"]))

    def test_public_url_requires_matching_redirect(self) -> None:
        from app import main

        original = main.settings
        try:
            main.settings = Settings(
                api_host="0.0.0.0",
                api_port=8001,
                public_base_url="https://researchos.example.edu",
                microsoft_client_id="test-client-id",
                microsoft_tenant_id="ucsd-tenant",
                microsoft_redirect_uri="http://localhost:8001/auth/callback",
                graph_scopes="User.Read Notes.Read",
            )
            readiness = main._onenote_readiness()
        finally:
            main.settings = original

        self.assertEqual(
            readiness["required_azure_redirect_uri"],
            "https://researchos.example.edu/auth/callback",
        )
        self.assertFalse(readiness["redirect_uri_compatible"])
        self.assertIn("openid", readiness["missing_required_scopes"])
        self.assertIn("offline_access", readiness["missing_required_scopes"])


if __name__ == "__main__":
    unittest.main()
