# Experiment Extraction Architecture

Experiment extraction is future-ready but does not call an LLM in this milestone.

Model:

- `ExperimentExtractionDraft`

Provider interface:

```python
class ExperimentExtractionProvider:
    def extract_from_text(...)
    def extract_from_transcript(...)
    def reconcile_with_protocol(...)
    def validate_draft(...)
```

Current provider:

- deterministic/mock provider for tests and demos
- extracts simple conditions/events from text
- marks output as `awaiting_confirmation`

AI-generated or imported fields must not become active without researcher confirmation.

## API

```bash
curl -X POST http://127.0.0.1:8001/experiment-extraction-drafts \
  -H "Content-Type: application/json" \
  -H "X-ResearchOS-User: user:researcher-a" \
  -d '{"source_type":"typed_text","source_text":"Untreated and DMSO controls with imaging on D35"}'
```

