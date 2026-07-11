"""Security tests for multi-user notebook sharing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.authorization import AuthorizationService
from app.config import Settings


class NotebookAuthorizationTests(unittest.TestCase):
    def _service(self, tmpdir: str) -> AuthorizationService:
        return AuthorizationService(
            Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")
        )

    def test_researcher_can_view_own_notebook(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            notebook = service.get_notebook("user:researcher-a", "notebook:researcher-a")

        self.assertIsNotNone(notebook)
        assert notebook is not None
        self.assertEqual(notebook["owner_user_id"], "user:researcher-a")

    def test_researcher_cannot_view_another_private_notebook(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            notebook = service.get_notebook("user:researcher-a", "notebook:researcher-b")

        self.assertIsNone(notebook)

    def test_owner_can_view_all_lab_notebooks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            notebooks = service.list_visible_notebooks("user:pi-owner")

        self.assertGreaterEqual(len(notebooks), 3)

    def test_admin_without_view_all_cannot_view_all_notebooks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            notebooks = service.list_visible_notebooks("user:lab-admin")

        self.assertEqual(notebooks, [])

    def test_explicit_share_grants_and_revocation_removes_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            permission = service.share_notebook(
                actor_user_id="user:researcher-a",
                notebook_id="notebook:researcher-a",
                principal_type="user",
                principal_id="user:researcher-b",
                access_level="view",
            )
            self.assertIsNotNone(service.get_notebook("user:researcher-b", "notebook:researcher-a"))
            service.revoke_permission(
                "user:researcher-a",
                "notebook:researcher-a",
                permission["permission_id"],
            )
            hidden = service.get_notebook("user:researcher-b", "notebook:researcher-a")

        self.assertIsNone(hidden)

    def test_group_share_grants_access_to_members(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            group = service.create_group("user:pi-owner", "lab:demo", "Project Team")
            service.add_group_member("user:pi-owner", group["group_id"], "user:guest")
            service.share_notebook(
                actor_user_id="user:researcher-a",
                notebook_id="notebook:researcher-a",
                principal_type="group",
                principal_id=group["group_id"],
                access_level="view",
            )
            visible = service.get_notebook("user:guest", "notebook:researcher-a")

        self.assertIsNotNone(visible)

    def test_guest_sees_only_shared_notebooks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            notebooks = service.list_visible_notebooks("user:guest")

        self.assertEqual(notebooks, [])

    def test_direct_entry_request_cannot_bypass_notebook_protection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            with self.assertRaises(PermissionError):
                service.entry_detail("user:researcher-a", "entry:notebook:researcher-b")

    def test_cross_lab_access_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            notebooks = service.list_visible_notebooks("user:researcher-a", "lab:other")

        self.assertEqual(notebooks, [])

    def test_audit_events_are_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            service.share_notebook(
                actor_user_id="user:researcher-a",
                notebook_id="notebook:researcher-a",
                principal_type="user",
                principal_id="user:researcher-b",
                access_level="view",
            )
            events = service.audit_events("user:pi-owner", "lab:demo")

        self.assertTrue(any(event["action"] == "notebook.shared" for event in events))


if __name__ == "__main__":
    unittest.main()
