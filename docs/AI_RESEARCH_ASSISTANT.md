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

## Example

```bash
curl -X POST http://127.0.0.1:8001/assistant/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"What markers were used with BRN3B?"}'
```

## AI Provider Behavior

If an OpenAI-compatible provider is configured, the assistant sends a structured
research context prompt to the provider. If the provider is not configured or
fails, the endpoint still returns a local fallback answer and includes the
limitation in `limitations_uncertainties`.

The older `/chat` endpoint remains available for basic RAG chat. The dashboard
chat uses `/assistant/ask` because it returns richer scientific evidence.
