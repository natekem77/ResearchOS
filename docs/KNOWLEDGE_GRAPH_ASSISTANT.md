# Knowledge Graph Assistant

Milestone 47 makes the Global Knowledge Graph the first-class evidence source
for assistant answers.

## What Changed

ResearchOS now exposes:

```http
POST /assistant/knowledge
```

The endpoint accepts either request shape:

```json
{"question": "What do we know about SAG?"}
```

```json
{"message": "What data exists for NK_Expt_31?"}
```

The assistant detects entity-specific and experiment-specific questions, then
uses the Global Knowledge Graph internally:

- `GET /knowledgegraph/entity/{entity}` for entity questions
- `GET /knowledgegraph/experiment/{experiment_id}` for experiment questions

## Answer Sections

Responses include:

- direct answer
- Knowledge Graph summary
- experiments
- notebook entries
- literature
- GraphPad/statistics
- spreadsheets
- microscopy/images
- related entities
- limitations

If an AI provider is configured, the graph evidence package is passed as the
AI context. If no AI provider is configured, ResearchOS returns a deterministic
local fallback.

## Existing Assistant Integration

`POST /assistant/ask` now consults Knowledge Graph evidence before falling back
to older local search and ontology logic.

`POST /assistant/reason` now includes a `knowledge_graph` evidence package in
the structured reasoning object.

## Curl Examples

```bash
curl -X POST http://127.0.0.1:8001/assistant/knowledge \
  -H "Content-Type: application/json" \
  -d '{"question":"What do we know about SAG?","use_ai":false}'
```

```bash
curl -X POST http://127.0.0.1:8001/assistant/knowledge \
  -H "Content-Type: application/json" \
  -d '{"question":"Show everything involving SIX6.","use_ai":false}'
```

```bash
curl -X POST http://127.0.0.1:8001/assistant/knowledge \
  -H "Content-Type: application/json" \
  -d '{"question":"Which experiments involve BRN3B?","use_ai":false}'
```

```bash
curl -X POST http://127.0.0.1:8001/assistant/knowledge \
  -H "Content-Type: application/json" \
  -d '{"question":"What data exists for NK_Expt_31?","use_ai":false}'
```

## UI

The AI Chat page has a `Knowledge Graph` mode. Entity pages include an
`Ask about this entity` button that opens the assistant and asks a graph-grounded
question.

## Design Rule

Future assistant features should query the Global Knowledge Graph first, then
layer search, AI synthesis, or provider-specific views on top of that evidence.
