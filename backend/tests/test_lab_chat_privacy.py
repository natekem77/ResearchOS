"""Security tests for ResearchOS lab chat privacy."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.lab_chat import ChatAuthorizationError, ChatValidationError, LabChatService


class LabChatPrivacyTests(unittest.TestCase):
    def _service(self, tmpdir: str) -> LabChatService:
        return LabChatService(
            Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")
        )

    def test_lab_member_can_read_lab_channel(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            messages = service.list_messages("user:researcher-a", "chat:general")

        self.assertGreaterEqual(len(messages["messages"]), 1)

    def test_non_member_cannot_read_lab_channel(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)

            with self.assertRaises(ChatAuthorizationError):
                service.list_messages("user:outside", "chat:general")

    def test_project_member_can_access_project_channel(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            conversation = service.get_conversation("user:researcher-a", "chat:sag-project")

        self.assertIsNotNone(conversation)

    def test_non_project_member_cannot_access_project_channel(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            conversation = service.get_conversation("user:guest", "chat:sag-project")

        self.assertIsNone(conversation)

    def test_group_member_can_access_private_group_chat(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            conversation = service.get_conversation("user:researcher-a", "chat:private-ab")

        self.assertIsNotNone(conversation)

    def test_non_member_cannot_enumerate_or_retrieve_private_group_chat(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            listed = service.list_conversations("user:pi-owner")
            conversation = service.get_conversation("user:pi-owner", "chat:private-ab")

        self.assertIsNone(conversation)
        self.assertNotIn("chat:private-ab", {item["conversation_id"] for item in listed})

    def test_elevated_roles_cannot_read_private_group_chat_without_membership(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)

            for user_id in ("user:pi-owner", "user:lab-admin", "user:supervisor"):
                with self.subTest(user_id=user_id):
                    self.assertIsNone(service.get_conversation(user_id, "chat:private-ab"))
                    with self.assertRaises(ChatAuthorizationError):
                        service.list_messages(user_id, "chat:private-ab")

    def test_direct_message_only_visible_to_two_participants(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)

            self.assertIsNotNone(service.get_conversation("user:researcher-a", "chat:dm-a-b"))
            self.assertIsNotNone(service.get_conversation("user:researcher-b", "chat:dm-a-b"))
            self.assertIsNone(service.get_conversation("user:pi-owner", "chat:dm-a-b"))

    def test_direct_message_cannot_add_third_participant(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)

            with self.assertRaises(ChatValidationError):
                service.add_member("user:researcher-a", "chat:dm-a-b", "user:researcher-c")

    def test_group_member_can_add_and_remove_same_lab_member(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            conversation = service.create_conversation(
                "user:researcher-a",
                "lab:demo",
                "group_chat",
                "Temporary group",
                member_user_ids=["user:researcher-b"],
            )
            service.add_member("user:researcher-b", conversation["conversation_id"], "user:researcher-c")
            self.assertIsNotNone(service.get_conversation("user:researcher-c", conversation["conversation_id"]))
            service.remove_member("user:researcher-b", conversation["conversation_id"], "user:researcher-c")

            hidden = service.get_conversation("user:researcher-c", conversation["conversation_id"])

        self.assertIsNone(hidden)

    def test_removed_member_cannot_retrieve_historical_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)

            with self.assertRaises(ChatAuthorizationError):
                service.list_messages("user:researcher-c", "chat:private-ab")

    def test_creator_cannot_read_after_leaving(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            conversation = service.create_conversation(
                "user:researcher-a",
                "lab:demo",
                "group_chat",
                "Leave test",
                member_user_ids=["user:researcher-b"],
            )
            service.remove_member("user:researcher-a", conversation["conversation_id"], "user:researcher-a")

            hidden = service.get_conversation("user:researcher-a", conversation["conversation_id"])

        self.assertIsNone(hidden)

    def test_cross_lab_member_cannot_be_added(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)

            with self.assertRaises(ChatValidationError):
                service.add_member("user:researcher-a", "chat:private-ab", "user:outside")

    def test_unauthorized_user_cannot_edit_or_delete_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            message = service.send_message("user:researcher-a", "chat:private-ab", "Edit protection")

            with self.assertRaises(ChatAuthorizationError):
                service.edit_message("user:researcher-b", message["message_id"], "Changed")
            with self.assertRaises(ChatAuthorizationError):
                service.delete_message("user:pi-owner", message["message_id"])

    def test_attachment_requires_conversation_and_underlying_resource_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)

            with self.assertRaises(ChatAuthorizationError):
                service.send_message(
                    "user:researcher-b",
                    "chat:private-ab",
                    "Attaching A private notebook",
                    attachments=[
                        {
                            "attachment_type": "notebook",
                            "resource_id": "notebook:researcher-a",
                            "display_name": "Researcher A notebook",
                        }
                    ],
                )

    def test_unread_counts_update_after_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            message = service.send_message("user:researcher-a", "chat:private-ab", "Unread test")
            unread = service.unread_counts("user:researcher-b")
            service.mark_read("user:researcher-b", message["message_id"])
            after = service.unread_counts("user:researcher-b")

        self.assertGreater(unread["total_unread"], after["total_unread"])

    def test_search_does_not_leak_private_message_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            service.send_message("user:researcher-a", "chat:private-ab", "private-secret-sag")

            owner_results = service.search("user:pi-owner", "private-secret-sag")
            member_results = service.search("user:researcher-b", "private-secret-sag")

        self.assertEqual(owner_results["results"], [])
        self.assertEqual(len(member_results["results"]), 1)

    def test_audit_logs_do_not_contain_private_message_bodies(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = self._service(tmpdir)
            service.send_message("user:researcher-a", "chat:private-ab", "super private message body")
            service.add_member("user:researcher-a", "chat:private-ab", "user:guest")
            events = service.authz.audit_events("user:pi-owner", "lab:demo")

        serialized = " ".join(str(event) for event in events)
        self.assertNotIn("super private message body", serialized)
        self.assertIn("conversation.member_added", serialized)


if __name__ == "__main__":
    unittest.main()
