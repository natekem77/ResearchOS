# Experiment Attachments

Experiment attachments are first-class records, not notebook body text.

## Source Types

- `uploaded_file`: a file stored by the ResearchOS attachment storage provider.
- `external_link`: a validated HTTP or HTTPS URL such as Google Sheets, Google Drive, OneDrive, SharePoint, or Dropbox.

## Storage

The initial provider is local development storage under `DATA_DIR/attachments`.
Database rows store stable object keys and metadata, not device-local temporary paths.

The storage abstraction is designed so a future provider can use Azure Blob Storage,
S3, or another object store without changing experiment notebook semantics.

## Attachment Metadata

Each attachment records:

- stable attachment ID
- experiment and notebook document ID
- attachment type
- source type
- display name
- original filename
- MIME type
- extension
- size
- storage path or external URL
- description
- upload and processing status
- creator
- checksum for uploaded files
- metadata JSON

## Spreadsheet AI Interface

Uploaded spreadsheets and delimited text files retain the original file and expose
a stable attachment ID for future jobs.

Future services should consume attachment IDs and implement:

- summarize spreadsheet
- inspect columns
- generate an experimental design
- compare experiments
- suggest statistical analyses
- generate plots

Until those jobs exist, spreadsheet attachments are marked `metadata_pending` and
the UI does not show a functional analysis button.

