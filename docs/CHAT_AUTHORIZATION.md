# Chat Authorization

ResearchOS chat authorization is enforced in the backend by `LabChatService`.

## Core Rule

Private means private to current conversation members.

No lab owner, PI, administrator, supervisor, creator, or system operator receives implicit access to private group chats or direct messages.

## Access Rules

Lab channels:

- Active lab members may read lab channels unless a future restriction is configured.

Project channels:

- Require active lab membership and explicit project-channel membership.

Group chats:

- Require current active conversation membership.
- Removed members immediately lose access to metadata, messages, attachments, unread counts, and search results.

Direct messages:

- Exactly two participants.
- No third participant can be added.
- Only the two current participants can read the conversation.

## Membership Policies

Supported policies:

- `members_manage`: any current member can add or remove participants.
- `moderators_manage`: only owners/moderators can manage participants.
- `creator_manages`: creator can manage only while still a current member.

The creator does not retain read access after leaving or being removed.

## Search and Attachments

Search only traverses conversations the current user can access. Private message text is never returned to non-members.

Attachments are checked twice:

1. The user must be a current conversation member.
2. The user must be authorized to view the referenced ResearchOS resource.

## Audit Logs

For private conversations, audit logs may record non-content metadata:

- conversation created
- member added
- member removed
- member left
- conversation archived
- administrative soft deletion

Audit logs must not contain private message bodies.

## No Backdoors

ResearchOS intentionally does not implement:

- admin private-chat viewer
- owner private-chat viewer
- supervisor private-chat viewer
- system-operator private-chat export
- assistant/copilot ingestion of private chats for non-members

