# Scientific Evidence Engine

The Scientific Evidence Engine synthesizes evidence across ResearchOS records without inventing observations.

It distinguishes:

- observed evidence
- supporting evidence
- contradictory evidence
- missing evidence
- confidence
- recommendations
- provenance

Every evidence statement must reference source records when sources exist.

## Endpoint

```bash
curl -X POST http://127.0.0.1:8001/evidence/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Does early SAG improve retinal differentiation?"}'
```

Response shape:

```json
{
  "question": "...",
  "summary": "...",
  "observed_evidence": [],
  "supporting_evidence": [],
  "contradictory_evidence": [],
  "missing_evidence": [],
  "related_experiments": [],
  "related_literature": [],
  "confidence": {
    "level": "insufficient|low|moderate|moderate-high",
    "score": 0.0,
    "factors": {}
  },
  "recommendations": [],
  "provenance": [],
  "conflicts": []
}
```

## Architecture

The Evidence Engine uses existing provider outputs rather than creating a separate evidence database.

Sources include:

- Notebook records
- Knowledge Graph entities and relationships
- Extracted experiments
- Statistics assets
- GraphPad assets
- Spreadsheet assets
- Microscopy/image assets
- Literature records
- Scientific Memory

The engine starts with Knowledge Graph traversal. It searches graph entities from the question, then gathers connected experiments, literature, statistics, spreadsheets, GraphPad assets, microscopy assets, and related historical experiments.

## Confidence

ResearchOS does not invent confidence.

Confidence is computed from transparent factors:

- number of related experiments
- number of independent datasets
- supporting statement count
- contradictory statement count
- missing evidence count
- statistical support count
- related literature count

Confidence remains low when evidence is sparse, contradictory, or missing quantitative support.

## Copilot Integration

Experiment Workspace now includes an `evidence` section.

Research Copilot reads that section before generating local summaries, so Copilot can surface:

- observed evidence
- graph-backed supporting evidence
- contradictory or non-supportive evidence
- missing evidence

Copilot still does not create observations.

## Limitations

- The first implementation is deterministic.
- It relies on provider metadata and Knowledge Graph coverage.
- It does not perform causal inference.
- It does not replace statistical review.
- It does not claim confidence beyond available records.

Future versions can add stronger evidence grading, study-design metadata, replicate tracking, and protocol-aware confidence scoring.
