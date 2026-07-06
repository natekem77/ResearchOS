# AI Scientific Research Assistant

ResearchOS includes a provider-agnostic scientific assistant endpoint:

```http
POST /assistant/ask
```

It accepts either request shape:

```json
{"question":"Which experiments used SAG?"}
```

```json
{"message":"Compare BMP4 and SAG experiments."}
```

## Context Sources

The assistant gathers local ResearchOS context from:

- document search results
- structured experiment records
- retinal organoid ontology entities
- source document chunks
- optional AI provider synthesis

The assistant is designed to work without Microsoft OneNote approval and without
an AI key when the Markdown demo provider has been loaded.

## Response Shape

The response includes:

- `direct_answer`
- `direct_matches`
- `related_context`
- `evidence_from_experiments`
- `source_document_citations`
- `extracted_facts`
- `ai_synthesis`
- `limitations_uncertainties`
- `sources`
- `ai_used`
- `provider`

When no AI provider is configured, ResearchOS returns a local fallback answer
based on retrieved experiments, ontology entities, and search snippets.

## Relevance Filtering

For entity-specific questions, ResearchOS separates direct matches from related
context. For example, a question about `SAG` only treats experiments containing
`SAG` as direct matches unless the user explicitly asks for a comparison. A
question comparing `BMP4` and `SAG` can include direct matches for either
compound.

The assistant applies a relevance threshold before including experiments or
source snippets. Related context may still be returned, but it is labeled
separately so it is not confused with direct evidence.

## Example

```bash
curl -X POST http://127.0.0.1:8001/assistant/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"What markers were used with BRN3B?"}'
```

Other useful examples:

```bash
curl -X POST http://127.0.0.1:8001/assistant/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Which experiments used SAG?"}'

curl -X POST http://127.0.0.1:8001/assistant/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Which experiments used BMP4?"}'

curl -X POST http://127.0.0.1:8001/assistant/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Compare BMP4 and SAG experiments."}'
```

## AI Provider Behavior

If an OpenAI-compatible provider is configured, the assistant sends a structured
research context prompt to the provider. If the provider is not configured or
fails, the endpoint still returns a local fallback answer and includes the
limitation in `limitations_uncertainties`.

The older `/chat` endpoint remains available for basic RAG chat. The dashboard
chat uses `/assistant/ask` because it returns richer scientific evidence.
