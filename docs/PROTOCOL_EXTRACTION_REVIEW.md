# Protocol Extraction Review

Protocol extraction drafts preserve uncertainty. Unknown values remain unknown instead of being inferred.

## Draft Fields

`ProtocolExtractionDraft` stores proposed overview fields, timeline events, materials, media, equipment, expected results, QC, troubleshooting, references, warnings, ambiguities, confidence, and evidence.

Each extracted field should include:

- source excerpt
- confidence: `high`, `medium`, `low`, or `unknown`
- origin: `document`, `pasted_text`, `voice`, `manual`, or `template`

## Minimum Approval Requirements

Approval requires:

- protocol title
- lab
- owner
- version label
- narrative content or at least one structured event
- explicit researcher confirmation

Structured details such as media recipes, concentrations, expected markers, or catalog numbers are not required. If absent, they remain unknown.

## Clarification Questions

ResearchOS generates targeted questions when important fields are missing or ambiguous, for example:

- Which protocol version is this?
- What is the final BMP4 concentration?
- What media-change schedule should be used?
- What is the expected protocol endpoint?

These questions guide review; they do not automatically create facts.
