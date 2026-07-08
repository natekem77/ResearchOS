# Protocol Intelligence

Protocol Intelligence turns protocol-like documents and registered protocol assets into first-class, read-only ResearchOS objects.

The goal is not to edit protocols automatically. ResearchOS detects, versions, links, compares, and summarizes protocol performance using evidence already stored locally.

## What Counts as a Protocol

ResearchOS currently detects protocols from:

- ResearchDocuments whose title or content contains `protocol`
- ResearchDocuments with metadata `document_type=protocol`
- Registered assets with `asset_type=protocol`

This keeps the system provider-agnostic. Markdown, OneNote, future file providers, and future ELN providers can all contribute protocol records by emitting ordinary document or asset metadata.

## Protocol Model

Each protocol contains:

- `id`
- `title`
- `version`
- `family`
- `provider`
- `source_document_id`
- `source_path`
- `created_at`
- `updated_at`
- `usage_statistics`
- `success_metrics`

The full protocol workspace also includes:

- source content
- version history
- timeline
- linked experiments
- related literature
- linked statistics
- Research Copilot protocol summary

## Versioning

Protocol versions are detected from titles or content using labels such as:

- `v1`
- `v2`
- `version 1`
- `version 2.1`

Versions with the same normalized protocol family are grouped into a history. For example:

- `BMP4 differentiation protocol v1`
- `BMP4 differentiation protocol v2`

belong to the same protocol family.

## Automatic Experiment Linking

Protocols link to experiments using:

- exact source document matches
- term overlap between protocol text and experiment fields
- compounds, treatments, markers, imaging methods, notes, and conclusions

Links are evidence suggestions. They do not overwrite source records and they do not imply causality.

## Usage Statistics

Usage statistics include:

- linked experiment count
- first use
- last use
- protocol terms used for linking
- linking method

## Success Metrics

Success metrics are deliberately conservative. They are keyword-derived from existing experiment notes and conclusions and are not statistical claims.

Metrics include:

- linked experiment count
- positive outcome count
- concern count
- rough success rate when linked experiments exist
- method note explaining the limitation

## Protocol Comparison

ResearchOS compares protocol versions with a unified text diff.

It returns:

- added lines
- removed lines
- whether content changed
- compact interpretation of likely concentration, timing, control, antibody, incubation, wash, or temperature changes

ResearchOS never edits either protocol version.

## API

List protocols:

```bash
curl http://127.0.0.1:8001/protocols
```

Open a Protocol Workspace:

```bash
curl http://127.0.0.1:8001/protocols/protocol:example
```

View version history:

```bash
curl http://127.0.0.1:8001/protocols/protocol:example/history
```

Compare two versions:

```bash
curl http://127.0.0.1:8001/protocols/protocol:example/compare/protocol:other
```

## UI

The dashboard includes a Protocols page and Protocol Workspace.

The workspace shows:

- overview metrics
- Research Copilot protocol performance summary
- version history
- timeline
- linked experiments
- related literature
- statistics
- detected protocol terms
- source content
- version comparison when more than one version exists

## Research Copilot Guardrail

Protocol Copilot can summarize observed performance and suggest review areas, but it must never automatically edit protocols.

Suggested improvements should be framed as review prompts, such as:

- add missing controls
- clarify concentrations
- clarify timing
- document success criteria

## Future Extensions

Planned extensions include:

- richer protocol section parsing
- structured reagent and timing extraction
- protocol-to-protocol semantic diffs
- protocol success metrics backed by statistical outcomes
- explicit protocol approval workflows
- optional OneNote protocol page creation after separate write-back approval
