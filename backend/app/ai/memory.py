"""Conversation memory extension points."""

from __future__ import annotations


class AIMemoryService:
    def summarize_conversation(self, conversation: dict[str, object]) -> str:
        messages = conversation.get("messages") if isinstance(conversation, dict) else None
        if not isinstance(messages, list):
            return ""
        return "\n".join(str(item.get("content") or "") for item in messages if isinstance(item, dict))[-4000:]

