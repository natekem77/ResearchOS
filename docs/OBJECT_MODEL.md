# Universal Research Object Model

ResearchOS represents major scientific records as `ResearchObject` references. Objects are built dynamically from existing provider metadata; the system should not duplicate source records.

## Shape

```json
{
  "object_id": "experiment:...",
  "object_type": "Experiment",
  "title": "NK_Expt_26",
  "subtitle": "retinal organoid",
  "lab_id": "lab:demo",
  "owner_user_id": "user:researcher-a",
  "created_at": "...",
  "updated_at": "...",
  "icon": "science",
  "search_keywords": [],
  "metadata": {},
  "supported_actions": ["open", "preview", "copy_reference"]
}
```

## Current Sources

The object index currently derives objects from:

- experiments and general experiment workspaces
- cohorts, conditions, timeline events
- protocol hub protocols, versions, materials, and media
- notebooks and notebook entries
- chat conversations and authorized chat messages
- resources and inventory
- assets, images, spreadsheets, and GraphPad analyses
- papers/literature
- experiment designs, reminders, and plate layouts
- users and lab workspaces
- knowledge graph entities

## Permissions

The object service filters objects using existing authorization services. Private notebooks and private chats are not returned to unauthorized users. Object links do not grant access to the target object.

