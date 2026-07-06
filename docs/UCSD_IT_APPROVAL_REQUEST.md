# UCSD IT Approval Request: ResearchOS Development

## Plain-Language Summary

ResearchOS is an AI-powered research operating system for scientific
laboratories. The current prototype helps researchers search, summarize, and
structure lab notebook information while keeping the official lab notebook in
Microsoft OneNote.

We are requesting Microsoft Graph delegated read-only access so ResearchOS can
read OneNote notebook content for the signed-in researcher during local
development.

## Why The Lab Wants This

The lab already uses OneNote for day-to-day research notes. Researchers need a
better way to find prior experiments, compare treatments, extract structured
experiment records, identify compounds and markers, and prepare summaries from
existing notes.

ResearchOS is intended to reduce manual note searching and make experiments
easier to review without changing the lab's official notebook workflow.

## OneNote Remains The Official Notebook

OneNote remains the official electronic notebook. ResearchOS does not replace
OneNote. The initial integration only reads notebook data into a local
development environment for indexing and analysis.

## Read-Only Initial Scope

The initial ResearchOS OneNote integration is read-only. It will not create,
modify, delete, or annotate OneNote pages.

Initial capabilities:

- List notebooks, sections, and pages for the signed-in user.
- Read page content for local indexing after approval.
- Convert pages into local ResearchOS documents.
- Run local search, experiment extraction, and optional AI-assisted summaries.

## Application Details

- App name: `ResearchOS Development`
- Client ID: `<CLIENT_ID_PROVIDED_BY_UCSD_OR_APP_REGISTRATION>`
- Redirect URI: `http://localhost:8001/auth/callback`
- App type: public client / local development client
- Client secret: not required for local public-client delegated auth

## Requested Delegated Microsoft Graph Permissions

Please approve or register an app with these delegated permissions:

- `User.Read`
- `Notes.Read`
- `openid`
- `profile`
- `offline_access`

These permissions allow the signed-in user to authenticate and allow ResearchOS
to read OneNote content that the user is already allowed to access.

## Data Handling And Privacy Model

ResearchOS is local-first during development:

- OneNote content is read into the user's local machine.
- Local storage uses SQLite and a local vector index.
- No ResearchOS-hosted cloud database is used in the current prototype.
- Access tokens and refresh tokens must not be committed to source control.
- Secrets are configured through environment variables, not hardcoded.
- Logs should not contain access tokens, refresh tokens, authorization codes, or
  sensitive notebook content.

## Optional Cloud AI Warning

ResearchOS can support optional AI providers in the future. If cloud AI is
enabled, selected note snippets may be sent to the configured AI provider for
summarization or question answering.

For UCSD review, this should be treated as optional and separately governed by
lab policy, data classification, and approved vendor requirements. The OneNote
read-only sync can function independently from cloud AI.

## Security Boundaries

The requested integration:

- Uses delegated user login.
- Reads only data the signed-in user can already access.
- Does not request write permissions.
- Does not use hardcoded secrets.
- Runs locally for development.
- Can be disabled by revoking consent or removing the app registration.

## Request

Please either:

1. Approve the `ResearchOS Development` app for use in the UCSD tenant, or
2. Register a UCSD-owned Microsoft Entra app for ResearchOS development with the
   delegated permissions and redirect URI listed above.

The lab's preference is a UCSD-owned app registration if that is the standard
path for internal research software prototypes.
