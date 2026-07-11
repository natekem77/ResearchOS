# Protocol Import Experience

Protocol import turns source material into a reviewable draft. ResearchOS never treats imported or pasted protocol text as approved scientific truth.

## Entry Points

- Import Document: stores source metadata for PDF, DOCX, Markdown, TXT, or image-based sources.
- Paste Protocol Text: preserves exact pasted text and generates a structured draft.
- Describe Protocol: accepts typed or dictated plain-language protocol descriptions.
- Create from Scratch: creates an incomplete blank protocol draft.
- Browse Templates: starts from section-only protocol templates.
- Scan Printed Protocol: future OCR workflow; currently informational only.

## API

```bash
curl http://127.0.0.1:8001/protocol-hub/templates

curl -X POST http://127.0.0.1:8001/protocol-hub/imports \
  -H "Content-Type: application/json" \
  -d '{"source_type":"pdf","original_filename":"meyer.pdf","mime_type":"application/pdf"}'

curl -X POST http://127.0.0.1:8001/protocol-hub/drafts/from-text \
  -H "Content-Type: application/json" \
  -d '{"source_text":"Add BMP4 on D6. Attach organoids on D9.","origin":"pasted_text","proposed_title":"Meyer notes"}'

curl -X POST http://127.0.0.1:8001/protocol-hub/create-blank \
  -H "Content-Type: application/json" \
  -d '{"title":"New protocol draft","category":"custom"}'
```

## Source Preservation

Original source text is retained exactly in `ProtocolExtractionDraft.source_text`. Import metadata is stored in `ProtocolImport`. Large binary files should be stored by an attachment/storage layer and referenced by `storage_reference`, not embedded in normal records.

## Review First

Extraction creates proposals only. A researcher must review fields, resolve required gaps, provide a version label, and explicitly confirm before approval.
