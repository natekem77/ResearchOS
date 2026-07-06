# OneNote Write-Back Design

This document describes the future ResearchOS workflow for saving reviewed
experiment drafts to Microsoft OneNote. It is design-only. ResearchOS does not
write to OneNote in the current MVP.

## Workflow

The PI-requested workflow is:

1. Researcher dictates experiment details on a phone, laptop, or browser input.
2. ResearchOS converts raw dictation into structured fields.
3. ResearchOS renders a formatted Markdown notebook entry.
4. Researcher reviews the structured fields, missing fields, and generated entry.
5. Researcher explicitly approves saving.
6. A future write-back integration creates a OneNote page.

The current implementation stops at step 4. The UI includes local copy,
download, and preview controls, while **Save to OneNote** remains disabled.

## Why Review Before Save Is Required

Notebook write-back affects the official lab record. Automatic save without
review would risk:

- Incorrectly parsed concentrations, dates, or treatment windows.
- Missing controls or readouts.
- AI-generated wording that overstates observations.
- Duplicate or misplaced notebook pages.
- Accidental inclusion of unapproved content.

ResearchOS should require explicit human review and confirmation before any
future OneNote page creation.

## Microsoft Graph Page Creation Flow

A future write-back flow would use Microsoft Graph delegated permissions:

1. User signs in through the existing public-client delegated auth flow.
2. ResearchOS lists notebooks and sections the user can access.
3. User chooses the target notebook and section.
4. ResearchOS converts reviewed Markdown to OneNote-compatible HTML.
5. ResearchOS calls Microsoft Graph to create a page in the selected section.
6. ResearchOS stores local metadata linking the draft, created page ID, section,
   notebook, timestamp, and user confirmation.

Likely Graph operation:

```text
POST /me/onenote/sections/{section-id}/pages
```

The request body would be OneNote page HTML, not raw Markdown.

## Future Permissions

The read-only MVP should keep the current minimal delegated permissions:

- `User.Read`
- `Notes.Read`
- `openid`
- `profile`
- `offline_access`

Future write-back would require separate approval for create/write permissions,
such as:

- `Notes.Create`
- `Notes.ReadWrite`

ResearchOS should not request these scopes until UCSD IT and the lab approve the
write-back workflow.

## UCSD IT Approval Implications

Write-back is materially different from read-only sync. The read-only MVP only
indexes content the signed-in user can already read. Write-back would create or
modify official notebook content.

Approval should be separated into two phases:

1. Read-only MVP approval for search, extraction, and local analysis.
2. Optional future write-back approval for creating reviewed notebook entries.

UCSD IT may require a UCSD-owned Microsoft Entra app registration, admin consent,
security review, logging expectations, and lab policy approval before write-back.

## Audit And Logging

Future write-back should record enough metadata to support audit and debugging
without leaking secrets:

- User confirmation timestamp.
- Target notebook ID/name.
- Target section ID/name.
- Created OneNote page ID.
- Local draft ID or hash.
- ResearchOS version.
- Whether AI formatting was used.
- Error code/message when write-back fails.

Logs must never include access tokens, refresh tokens, authorization codes, or
client secrets. Full notebook content should not be written to logs.

## Error Handling

Future write-back should return clear messages for:

- User not signed in.
- Missing write permission.
- UCSD tenant/admin consent not granted.
- Target notebook or section unavailable.
- Invalid OneNote HTML.
- Microsoft Graph throttling.
- Network failure.
- Duplicate page prevention or retry ambiguity.

When page creation status is ambiguous, ResearchOS should not retry blindly. It
should ask the user to inspect the target section or retry with explicit
confirmation.

## Future Endpoint Design

Possible endpoint:

```http
POST /entries/save-onenote
```

Example request:

```json
{
  "markdown": "# NK-EXPT-31...",
  "title": "NK-EXPT-31",
  "notebook_id": "...",
  "section_id": "...",
  "confirmed": true
}
```

Example response:

```json
{
  "status": "created",
  "provider": "onenote",
  "page_id": "...",
  "section_id": "...",
  "notebook_id": "...",
  "created_at": "..."
}
```

This endpoint should not be implemented until write permissions are approved.
