# UCSD IT Approval Request: ResearchOS Development

## Copy/Paste Email

Subject: Request for UCSD Microsoft Graph approval for read-only OneNote research prototype

Hello UCSD IT team,

I am developing a local research software prototype called ResearchOS
Development for our lab. ResearchOS is intended to help researchers search,
summarize, and structure existing lab notebook information while keeping
Microsoft OneNote as the official notebook.

I am requesting guidance or approval for a Microsoft Entra app registration that
allows read-only delegated Microsoft Graph access to OneNote for the signed-in
user.

Requested app details:

- App name: ResearchOS Development
- Client ID: `<CLIENT_ID_PROVIDED_BY_UCSD_OR_APP_REGISTRATION>`
- Redirect URI: `http://localhost:8001/auth/callback`
- App type: public client / local development client
- Client secret: not required
- Delegated permissions requested:
  - User.Read
  - Notes.Read
  - openid
  - profile
  - offline_access

The initial integration is read-only. ResearchOS will not create, modify,
delete, or annotate OneNote pages. It will read notebook content that the
signed-in user is already allowed to access, then index it locally for search and
experiment extraction.

Optional future write-back, such as saving a reviewed dictated experiment entry
back to OneNote, is not part of this request. That workflow would require a
separate approval later for create/write permissions such as `Notes.Create` or
`Notes.ReadWrite`.

The prototype is local-first. Notebook content is stored on the user's local
machine in SQLite and a local vector index. No secrets are hardcoded. Tokens and
configuration values are not committed to source control. Optional cloud AI
features are separate and would be governed by lab and UCSD policy before use
with real notebook content.

Could you please advise whether UCSD can either approve this ResearchOS
Development app for the UCSD tenant or create a UCSD-owned app registration with
the permissions above?

Thank you,
Nathan

## Short Project Summary

ResearchOS is an AI-powered research operating system for scientific
laboratories. The first integration is a read-only OneNote companion that helps
researchers search notes, extract structured experiments, and connect related
protocols, compounds, markers, and organoid batches.

OneNote remains the official lab notebook. ResearchOS is an analysis and search
layer around notebook content.

## Why The Lab Wants This

Researchers need a faster way to find prior experiments, compare conditions, and
summarize related notes. ResearchOS reduces manual notebook searching while
preserving the lab's existing OneNote workflow.

## Requested Microsoft Graph Permissions

For the read-only MVP:

- `User.Read`: sign in and read basic user profile.
- `Notes.Read`: read OneNote notebooks and pages available to the user.
- `openid`: OpenID Connect sign-in.
- `profile`: basic profile claims.
- `offline_access`: refresh delegated access during local development sessions.

No write permissions are requested.

## Optional Future Write-Back

ResearchOS may later support a PI-requested workflow where a researcher dictates
an experiment, reviews a structured draft, and explicitly saves it to OneNote.
That is intentionally separate from the read-only MVP.

Future write-back would require separate UCSD IT and lab approval before any
scope changes. Potential future delegated permissions include:

- `Notes.Create`
- `Notes.ReadWrite`

ResearchOS should not request those permissions in the current read-only app
registration.

## Data Handling And Privacy

- Local-first development prototype.
- OneNote content is stored locally after sync.
- SQLite is used for local metadata and document storage.
- A local vector index is used for search.
- No hardcoded secrets.
- No committed tokens.
- Logs should not include tokens, authorization codes, or sensitive notebook
  content.
- Cloud AI is optional and should not be enabled for real notebook content
  without lab and UCSD approval.

## Specific Request

Please either:

1. Approve the `ResearchOS Development` app for the UCSD tenant, or
2. Register a UCSD-owned Microsoft Entra app for this prototype.

Preferred redirect URI:

```text
http://localhost:8001/auth/callback
```
