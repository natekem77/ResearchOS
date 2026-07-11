# Protocol Import

Protocol Hub is designed to import existing protocol documents into structured workflows.

## Supported Sources

Planned source types:

- PDF
- Word
- Markdown
- Plain text
- OneNote export

The current implementation provides the structured destination model and deterministic demo data. Full document parsing should be added through a provider abstraction so imported content can be reviewed before becoming an approved protocol version.

## Import Targets

Imported protocols should be split into:

- Notebook content
- Timeline events
- Materials
- Media recipes
- Equipment
- Expected results
- QC checkpoints
- Troubleshooting entries
- Linked papers

Uncertain extracted sections must be flagged and require review.

## Review Before Approval

Imported protocol versions should start as `draft`. A researcher or PI should review:

- timing
- reagent names
- concentrations
- required/optional steps
- QC criteria
- ambiguous instructions

Only reviewed versions should become `approved`.

## Future Endpoint Shape

```http
POST /protocol-hub/import-preview
POST /protocol-hub/import-confirm
```

The preview endpoint should return proposed structured sections and confidence/warnings. The confirm endpoint should create a draft protocol version.

