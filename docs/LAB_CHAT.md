# Lab Chat

ResearchOS Lab Chat adds persistent, backend-authorized communication for laboratory work.

Supported conversation types:

- `lab_channel`: lab-wide channels such as General, Announcements, and Inventory.
- `project_channel`: project-specific channels.
- `group_chat`: private group chats visible only to current members.
- `direct_message`: private two-person conversations.

## Default Demo Channels

The demo lab seeds:

- General Lab Chat
- Announcements
- Inventory
- SAG Project
- SAG private planning
- Researcher A + Researcher B direct message

Demo private chats intentionally do not include the PI unless explicitly added.

## Scientific Attachments

Messages can link to ResearchOS resources by reference instead of duplicating data:

- experiment
- notebook
- entry
- protocol
- image
- inventory
- purchase request
- design
- statistic
- paper
- custom

Attachment access requires both current conversation membership and permission to view the underlying resource. A chat attachment must never grant access to a scientific object the user could not otherwise view.

## API Examples

```bash
curl -H "X-ResearchOS-User: user:researcher-a" http://127.0.0.1:8001/chat/conversations
curl -H "X-ResearchOS-User: user:researcher-a" http://127.0.0.1:8001/chat/conversations/chat:private-ab/messages
```

Create a group chat:

```bash
curl -X POST http://127.0.0.1:8001/chat/conversations \
  -H "Content-Type: application/json" \
  -H "X-ResearchOS-User: user:researcher-a" \
  -d '{"conversation_type":"group_chat","name":"D32 Imaging","member_user_ids":["user:researcher-b"]}'
```

Send a message:

```bash
curl -X POST http://127.0.0.1:8001/chat/conversations/chat:private-ab/messages \
  -H "Content-Type: application/json" \
  -H "X-ResearchOS-User: user:researcher-a" \
  -d '{"body":"Please review NK_Expt_31 before imaging.","attachments":[{"attachment_type":"experiment","resource_id":"NK_Expt_31","display_name":"NK_Expt_31"}]}'
```

## Save to Research Record

The initial API stores chat messages and references. The future `Save to Research Record` action should create:

- notebook entry draft
- experiment timeline note
- session note

The promoted record must preserve message author, timestamp, conversation title, source message IDs, and the user who promoted the discussion. ResearchOS must never silently copy private chat into notebooks.

## Current Limitations

This milestone uses persisted REST APIs and mobile polling. External push notifications and full WebSocket delivery are future work.

