# Private Chat Policy

ResearchOS private chats are private to current members only.

## Non-Negotiable Rule

Private group chats and direct messages are visible only to current conversation members.

The following users do not receive implicit access:

- PI
- lab owner
- lab administrator
- supervisor
- conversation creator
- system operator

## Member Removal

When a member is removed:

- access is revoked immediately
- the conversation disappears from their list
- historical messages are no longer retrievable
- unread counts stop including the conversation
- search no longer returns the conversation or its messages
- future realtime events must not be delivered

Historical messages remain available to remaining members.

## Direct Messages

Direct messages always contain exactly two participants. A third person cannot be added. To include more people, users must create a new private group chat.

## Group Chats

Default group-chat policy is `members_manage`, meaning any current member can add or remove another active same-lab member. A user cannot remove the final remaining member.

## Audit

Private message bodies are never written to audit logs. Audit logs can record non-content moderation and membership metadata only.

## AI and Analytics

Private chats must not be included in assistant, copilot, search, analytics, summaries, or exports for non-members.

