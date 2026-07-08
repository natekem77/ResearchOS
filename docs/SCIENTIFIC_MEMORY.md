# Scientific Memory

Scientific Memory is the ResearchOS layer that relates new experiments to historical lab work.

The goal is for ResearchOS to behave less like a search engine and more like an experienced scientist who remembers prior experiments, related protocols, quantitative results, image assets, literature, and workflow context.

## Current Implementation

Milestone 71 uses deterministic similarity. No machine learning is required yet.

For each experiment, ResearchOS builds:

- `memory_vector`
- `feature_vector`
- `similarity_vector`

These vectors are derived from existing ResearchOS evidence:

- notebook/extracted experiment fields
- Knowledge Graph relationships
- workflow stage
- timeline-linked assets
- GraphPad assets
- statistics metadata
- spreadsheets
- microscopy/image metadata
- literature documents
- protocol-like assets
- general research assets

## Similarity

The deterministic scorer compares normalized feature vectors. Shared features increase similarity:

- compounds
- treatments
- concentrations
- time points
- markers
- antibodies
- imaging methods
- sequencing fields
- cell lines
- organoid batches
- Knowledge Graph entities
- linked asset types
- statistics presence

Important differences are reported from high-weight features present in one experiment but not the other.

## API

Memory index status:

```bash
curl http://127.0.0.1:8001/memory
```

One experiment memory:

```bash
curl http://127.0.0.1:8001/memory/experiment/NK_Expt_31
```

Find similar work:

```bash
curl -X POST http://127.0.0.1:8001/memory/similar \
  -H "Content-Type: application/json" \
  -d '{"experiment_id":"NK_Expt_31","limit":5}'
```

The similar endpoint returns:

- most similar experiments
- similarity scores
- key similarities
- important differences
- related protocols
- related literature
- related statistics
- related microscopy

## Workspace Integration

Experiment Workspaces include a `scientific_memory` section. The UI shows similar historical experiments with scores, similarities, and differences.

## Research Copilot Integration

Research Copilot uses Scientific Memory to produce statements such as:

```text
Scientific Memory links this experiment to NK_Expt_31 with similarity score 0.72.
```

These statements are marked as inferred and do not invent experimental observations.

## Dashboard Integration

The Daily Dashboard includes a Similar Experiments card generated from Scientific Memory.

## Future Architecture

Scientific Memory is designed to support future predictive AI:

- embeddings
- graph neural networks
- contrastive learning
- cross-lab similarity search
- protocol outcome prediction
- microscopy phenotype memory
- literature-aware experiment planning

Future implementations should preserve provenance and never convert inferred similarity into observed findings.

## Limitations

- Similarity quality depends on extracted metadata.
- Sparse notebook entries produce sparse vectors.
- Provider coverage affects memory quality.
- No learned embeddings are used yet.
- Related protocol/statistics/image/literature matching is deterministic and conservative.
