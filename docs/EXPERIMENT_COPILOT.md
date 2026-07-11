# Experiment Design Copilot

Experiment Design Copilot converts typed or spoken scientific planning notes into a reviewed draft experiment.

It does not create an active experiment automatically. The workflow is:

1. Researcher enters a narrative or voice transcript.
2. ResearchOS extracts candidate structure.
3. ResearchOS records evidence and confidence for each extracted field.
4. ResearchOS asks clarification questions for missing or ambiguous details.
5. Researcher reviews and answers.
6. Researcher explicitly approves the draft.
7. ResearchOS creates a draft structured experiment.

## API

```bash
curl http://127.0.0.1:8001/experiment-copilot/demo-narrative
```

```bash
curl -X POST http://127.0.0.1:8001/experiment-copilot/draft \
  -H "Content-Type: application/json" \
  -d '{"narrative":"Using the Meyer retinal organoid protocol, compare D1 and D9 SAG treatment..."}'
```

```bash
curl -X POST http://127.0.0.1:8001/experiment-copilot/drafts/{session_id}/clarify \
  -H "Content-Type: application/json" \
  -d '{"answers":{"replicates":"3","sample_counts":"6 organoids per replicate","protocol_version":"current Meyer version"}}'
```

```bash
curl -X POST http://127.0.0.1:8001/experiment-copilot/drafts/{session_id}/approve \
  -H "Content-Type: application/json" \
  -d '{"experiment_id":"NK_Expt_26"}'
```

## Current Scope

Phase 1 uses a deterministic extractor. It recognizes common planning language for protocols, cohorts, conditions, treatments, concentrations, collections, imaging days, and endpoints. It is intentionally conservative.

If a field is not present in the narrative, ResearchOS stores it as unknown and asks for clarification when required. It does not invent biological replicate counts, sample counts, protocol versions, collection quantities, or dosing details.

## Demo Narrative

The built-in demo narrative covers the retinal organoid SAG example:

- Meyer retinal organoid protocol
- early D1 cohort
- late D9 cohort
- untreated, DMSO, SAG 300 nM, SAG 300 nM + GRKi 10 nM
- D16, D25, and D35 imaging
- D90 endpoint
- BMP4 D6 inherited from protocol
- missing replicate/sample counts flagged for clarification

## Flutter

In the mobile app, choose **New Experiment** then **Describe Experiment**. The screen supports:

- free-form narrative entry
- loading the SAG demo
- draft generation
- evidence cards
- confidence chips
- clarification answers
- explicit draft approval

## Safety Rule

The Copilot assists scientific planning. The researcher owns the final interpretation and must approve before any experiment is created.
