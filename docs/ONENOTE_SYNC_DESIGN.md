# OneNote Sync Design

ResearchOS will use Microsoft Graph to read OneNote notebooks, sections, and
pages into the local ResearchOS document pipeline. The MVP remains read-only:
OneNote stays the official lab notebook, and ResearchOS adds local indexing,
search, extraction, and AI workflows around it.

## Microsoft Graph OneNote Sync

Microsoft Graph exposes OneNote content through delegated user permissions. A
signed-in researcher grants ResearchOS read access to their notebooks, then the
backend calls Graph endpoints on that user's behalf.

The intended traversal is:

1. List notebooks with `GET /me/onenote/notebooks`.
2. List sections for each notebook with `GET /me/onenote/notebooks/{id}/sections`.
3. List pages for each section with `GET /me/onenote/sections/{id}/pages`.
4. Fetch page content only during sync with `GET /me/onenote/pages/{id}/content`.

Current ResearchOS endpoints already list notebook, section, and page metadata.
The sync engine should build on those helpers rather than duplicating Graph
request code.

## Current Implementation Status

ResearchOS now exposes:

```http
POST /sync/onenote
```

The endpoint is read-only. It uses the existing Microsoft Graph delegated token,
fetches notebooks, sections, pages, and page HTML content, converts page HTML to
clean text, and stores each page as a provider-agnostic `ResearchDocument` with
`provider="onenote"`.

After storage, the sync reuses the existing ResearchOS pipeline:

1. Chunk page text.
2. Store chunks in SQLite.
3. Upsert chunks into ChromaDB.
4. Run regex-first experiment extraction.
5. Make OneNote pages available to `/documents`, `/search`, `/experiments`, and
   ontology views when relevant entities are detected.

UCSD production use still depends on Microsoft tenant approval or a UCSD-owned
app registration with the requested delegated read permissions.

## Auth Flow Already Implemented

ResearchOS currently has Microsoft delegated authentication scaffolding:

- `GET /auth/login` builds a Microsoft authorization URL.
- `GET /auth/callback` exchanges the authorization code for a delegated token.
- `GET /auth/status` reports safe auth status without exposing tokens.

The app is designed as a public local development client. It must not require a
client secret for local use. Token storage is temporary and local-only until a
production credential store is designed.

## Data Mapping

OneNote content maps into provider-agnostic `ResearchDocument` records:

| OneNote object | ResearchOS field |
| --- | --- |
| Notebook ID | `metadata["notebook_id"]` |
| Notebook display name | `metadata["notebook_name"]` |
| Section ID | `metadata["section_id"]` |
| Section display name | `metadata["section_name"]` |
| Page ID | `source_id` |
| Page title | `title` |
| Page web URL | `source_url` |
| Created timestamp | `created_at` |
| Last modified timestamp | `updated_at` |
| Converted page body | `content` |
| Provider | `provider = "onenote"` |

The OneNote provider should produce the same `ResearchDocument` model used by
Markdown ingestion so downstream chunking, search, ontology extraction, and
experiment extraction remain provider-agnostic.

This is the implemented mapping for synced pages. Source metadata is stored in
`metadata_json` and includes notebook ID/name, section ID/name, page ID/title,
Graph timestamps, and `contentUrl` when Graph provides it.

## Page HTML Conversion

Microsoft Graph returns OneNote page bodies as HTML. The sync engine should:

1. Parse HTML with a structured parser.
2. Remove scripts, styles, navigation artifacts, and empty layout nodes.
3. Preserve headings, paragraphs, lists, tables, image alt text, and links.
4. Convert the cleaned structure to readable text or Markdown.
5. Store the converted text in `ResearchDocument.content`.
6. Store selected original metadata, but avoid storing unnecessary Graph tokens
   or auth artifacts.

The first implementation converts to plain Markdown-like text with a standard
library HTML parser. It preserves visible text, basic block breaks, list
markers, and image alt text. A later version can preserve richer block structure
for tables, protocols, embedded files, and images.

## Incremental Sync

The current sync upserts pages by stable OneNote page ID and records
`lastModifiedDateTime` in the document's `updated_at` and metadata fields. The
next optimization should use `lastModifiedDateTime` to avoid fetching unchanged
page content:

1. Store each OneNote page ID and its last synced `lastModifiedDateTime`.
2. During sync, list page metadata first.
3. Fetch full page content only when the page is new or has a newer
   `lastModifiedDateTime`.
4. Upsert the corresponding `ResearchDocument`.
5. Re-chunk, re-index, and re-run extraction only for changed pages.
6. Keep a provider sync log with counts, timestamps, and errors.

Deleted or moved pages should be handled conservatively. The first version can
mark missing pages as inactive rather than deleting local records immediately.

## Local-First Storage

ResearchOS stores synced content locally in SQLite and the local vector index.
This keeps development unblocked and allows the lab to demo search and
extraction without relying on cloud-hosted ResearchOS infrastructure.

Local-first does not mean low-security. The sync engine should keep secrets out
of source control, avoid logging tokens, and document where local data is stored.

## Read-Only MVP

The OneNote MVP is read-only:

- Read notebooks, sections, pages, and page content.
- Convert pages into local `ResearchDocument` records.
- Run local search, extraction, ontology linking, and optional AI workflows.
- Do not create, edit, delete, or annotate OneNote pages.

This read-only boundary should be visible in code, docs, and UCSD IT review
materials.

## Future Write-Back Options

Write-back is out of scope for the MVP. Possible future options include:

- Add AI-generated summaries back to OneNote as clearly labeled append-only
  sections.
- Create draft protocol pages from approved templates.
- Add links from OneNote pages to ResearchOS experiment views.
- Write structured metadata only after explicit user approval.

Any write-back feature would require new permissions, explicit UI confirmation,
audit logging, and a separate security review.

## Error Handling

The sync engine should surface common Microsoft and tenant issues clearly:

- Tenant admin approval required.
- User lacks a OneNote license.
- Notebook access denied.
- Delegated consent denied or revoked.
- Token expired and refresh failed.
- Graph throttling or transient service errors.
- Page content is unavailable or malformed.

Errors should be logged with request context, but never with access tokens,
refresh tokens, authorization codes, or sensitive page content unless the user
explicitly enables local debug logging.

## Modules

Initial implementation can be split into small modules:

- `graph_client.py`: authenticated Microsoft Graph GET helper.
- `onenote_provider.py`: metadata listing, page content fetches, HTML
  conversion, and `ResearchDocument` mapping.
- `ingestion.py`: shared provider-agnostic document ingestion pipeline.
- `storage.py`: local document, chunk, experiment, and sync metadata storage.

This keeps OneNote-specific code at the provider boundary and preserves the
ResearchOS core as notebook-provider agnostic.
