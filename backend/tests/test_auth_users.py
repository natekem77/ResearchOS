"""Tests for ResearchOS user/auth scaffolding."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.permissions import can_admin, can_edit_resource, can_view_resource, permission_summary
from app.storage import SQLiteStore
from app.users import current_user, normalize_role, permissions_for_role, user_with_permissions


class AuthUsersTests(unittest.TestCase):
    """User scaffolding should keep local demo mode unblocked."""

    def _settings(self, tmpdir: str, auth_enabled: bool = False) -> Settings:
        return Settings(
            database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}",
            auth_enabled=auth_enabled,
            dev_user_email="dev@example.test",
            dev_user_display_name="Dev Researcher",
        )

    def test_dev_mode_current_user_is_admin(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            user = current_user(settings, store)
            users = store.list_users()

        self.assertEqual(user["user_id"], "user:dev-local")
        self.assertEqual(user["role"], "admin")
        self.assertEqual(user["auth_provider"], "local_dev")
        self.assertTrue(user["permissions"]["can_admin"])
        self.assertEqual(len(users), 1)

    def test_role_permissions(self) -> None:
        self.assertEqual(normalize_role("Admin"), "admin")
        self.assertTrue(permissions_for_role("researcher")["can_edit"])
        self.assertFalse(permissions_for_role("viewer")["can_edit"])
        self.assertTrue(can_view_resource({"role": "viewer"}, "experiments"))
        self.assertFalse(can_edit_resource({"role": "viewer"}, "experiments"))
        self.assertTrue(can_edit_resource({"role": "researcher"}, "assets"))
        self.assertFalse(can_edit_resource({"role": "researcher"}, "users"))
        self.assertTrue(can_admin({"role": "admin"}))
        self.assertIn("workflows", permission_summary({"role": "researcher"})["resource_permissions"])
        with self.assertRaises(ValueError):
            normalize_role("owner")

    def test_bootstrap_admin_storage_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            user = store.upsert_user(
                user_id="user:admin",
                email="admin@example.test",
                display_name="Admin User",
                role="admin",
                auth_provider="local",
            )
            fetched = store.get_user_by_email("ADMIN@example.test")

        self.assertEqual(user["user_id"], "user:admin")
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["display_name"], "Admin User")
        self.assertTrue(user_with_permissions(fetched)["permissions"]["can_admin"])

    def test_owner_fields_are_stored_for_user_created_resources(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            entry = store.save_pending_entry(
                title="Owned draft",
                experiment_id="NK_Expt_31",
                template="general",
                structured={},
                markdown="# Owned draft",
                owner_user_id="user:dev-local",
                created_by="user:dev-local",
            )
            asset = store.register_asset(
                asset_type="image",
                experiment_id="NK_Expt_31",
                title="Owned asset",
                filename="owned.tif",
                provider="local",
                path="data/owned.tif",
                owner_user_id="user:dev-local",
                created_by="user:dev-local",
            )
            session = store.start_session(
                experiment_id="NK_Expt_31",
                notes="Owned session",
                owner_user_id="user:dev-local",
                created_by="user:dev-local",
            )

        self.assertEqual(entry["owner_user_id"], "user:dev-local")
        self.assertEqual(asset["created_by"], "user:dev-local")
        self.assertEqual(session["owner_user_id"], "user:dev-local")


if __name__ == "__main__":
    unittest.main()
