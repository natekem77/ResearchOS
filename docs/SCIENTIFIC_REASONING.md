# Scientific Reasoning Engine

The Scientific Reasoning Engine helps ResearchOS answer lab questions by
combining multiple local evidence types instead of relying on one search result.

## Goal

For questions such as:

```text
Does early SAG improve retinal differentiation?
```

ResearchOS gathers local evidence from:

- Notebook entries and source document chunks
- Extracted structured experiments
- GraphPad CSV statistics
- Microscopy/image assets
- Literature matches
- Experiment comparisons
- Timeline events linked through experiment IDs and assets

## API

```bash
curl -X POST http://127.0.0.1:8001/assistant/reason \
  -H "Content-Type: application/json" \
  -d '{"question":"Does early SAG improve retinal differentiation?","use_ai":false}'
```

The response includes:

- `answer`: concise scientific answer
- `reasoning.observations`: key observations from local evidence
- `reasoning.supporting_evidence`: experiments, statistics, images, notes, and literature supporting the answer
- `reasoning.conflicting_evidence`: evidence with cautionary or conflicting language
- `reasoning.limitations`: missing data and interpretation limits
- `reasoning.confidence`: local confidence estimate
- `reasoning.recommended_next_experiments`: suggested next experiments
- `sources`: normalized source objects

## Local-First Behavior

If no AI provider is configured, ResearchOS uses deterministic local reasoning:

1. Extracts terms from the question.
2. Searches local notebook and literature chunks.
3. Scores structured experiments by term overlap.
4. Scores assets and GraphPad statistics by filename, metadata, and parsed statistics fields.
5. Adds linked timeline context.
6. Produces observations, limitations, confidence, and follow-up experiments.

This path requires no external API key.

## Optional AI Synthesis

If an AI provider is configured, ResearchOS sends the same local evidence package
to the provider for a cleaner narrative. The evidence collection step remains
local and provider-agnostic.

## Current Limitations

- Microscopy evidence is filename/metadata based only; image pixels are not
  analyzed yet.
- GraphPad evidence depends on exported CSV files, not proprietary Prism parsing.
- Experiment comparisons use extracted structured fields, so missing extraction
  fields can limit conclusions.
- Literature reasoning depends on papers that have been locally ingested.

## UI

The dashboard now includes a **Scientific Reasoning** page. The AI Chat page
also has a mode toggle:

- **Search** uses `/assistant/ask`
- **Scientific Reasoning** uses `/assistant/reason`
