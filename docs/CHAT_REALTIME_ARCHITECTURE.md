# Chat Realtime Architecture

The current Lab Chat foundation persists messages through REST APIs and supports polling. This is intentionally conservative while ResearchOS is still a local-first preview.

## Current Implementation

- Messages are written to SQLite before clients see them.
- Clients fetch conversations and messages with REST endpoints.
- Unread state is stored in conversation membership rows.
- Removed private-chat members lose access immediately because every request re-checks current membership.

## Future Realtime Provider

The next phase should introduce:

```python
class ChatRealtimeProvider:
    def subscribe(user_id: str, conversation_id: str) -> None: ...
    def publish_message(conversation_id: str, message: dict) -> None: ...
    def publish_membership_change(conversation_id: str, event: dict) -> None: ...
    def revoke_user(conversation_id: str, user_id: str) -> None: ...
```

The first concrete transport can be:

- `/ws/chat` WebSocket endpoint
- Server-sent events
- polling fallback for mobile

## Required WebSocket Guarantees

A WebSocket implementation must:

- authenticate the connection
- subscribe only to authorized conversations
- re-check membership before every private delivery
- revoke subscriptions immediately when a member is removed
- persist messages before broadcasting
- deliver edits, deletions, membership changes, and read-state changes
- never deliver private messages to non-members

## Push Notifications

External push notifications are not implemented yet. When added, notification payloads for private chats should avoid message bodies unless a future privacy review explicitly permits them.

## Deployment Note

Chat from anywhere requires an always-reachable backend. The current Mac-hosted development backend works only while the Mac is awake, ResearchOS is running, and the phone can reach it through LAN or Tailscale.

