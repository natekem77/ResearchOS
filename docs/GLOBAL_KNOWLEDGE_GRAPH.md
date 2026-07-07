# Global Knowledge Graph

Milestone 46 adds the provider-agnostic ResearchOS knowledge layer. The graph
indexes scientific entities and relationships from existing SQLite records
without maintaining a duplicate graph database.

## Purpose

The Global Knowledge Graph is intended to become the central relationship layer
for ResearchOS. Future features such as semantic search, scientific reasoning,
experiment planning, reagent tracking, RNA-seq integration, protocol comparison,
manuscript drafting, grant writing, and lab analytics should query this layer
instead of rebuilding their own relationship logic.

## Architecture

The graph is built by `KnowledgeGraphService` in
`backend/app/global_knowledge_graph.py`.

The service reads:

- `documents`: notebook entries, OneNote pages, Markdown notes, and literature
- `experiments`: structured experiments extracted from documents
- `assets`: microscopy, GraphPad, spreadsheets, PDFs, presentations, sequencing,
  and other registered research assets
- `pending_entries`: local notebook-entry drafts awaiting OneNote write-back
- provider metadata: parsed entities, image metadata, spreadsheet summaries,
  GraphPad statistics, and literature metadata

The graph is cached in memory after build. It is invalidated automatically when
the SQLite database file fingerprint changes. `refresh()` can also force a
rebuild.

## Provider Contract

Providers should emit metadata rather than graph-specific code. The preferred
format is:

```json
{
  "entities": {
    "compound": ["SAG"],
    "marker": ["SIX6", "BRN3B"],
    "cell_line": ["SIX6 reporter iPSC"],
    "unknown_scientific_term": ["Any lab-specific term"]
  }
}
```

Future providers can add new entity types without changing the graph service:

```json
{
  "entities": {
    "metabolite": ["lactate"],
    "behavioral_assay": ["open field"],
    "sequencing_cluster": ["cluster_7"]
  }
}
```

The service also recognizes common top-level metadata fields such as
`compounds`, `genes`, `proteins`, `markers`, `antibodies`, `cell_lines`,
`organoid_batches`, `samples`, `patients`, `animals`, `treatments`, and
`unknown_scientific_terms`.

Optional aliases can be provided:

```json
{
  "aliases": {
    "SAG": ["Smoothened agonist"]
  }
}
```

Aliases, case differences, whitespace differences, and punctuation differences
are merged into one entity node.

## Entity Types

The graph supports arbitrary entity types. The initial normalized types include:

- `compound`
- `marker`
- `gene`
- `protein`
- `antibody`
- `cell_line`
- `patient`
- `animal`
- `sample`
- `sample_batch`
- `organoid_batch`
- `cell_population`
- `sequencing_cluster`
- `treatment`
- `unknown_scientific_term`

Unknown future entity types are preserved rather than discarded.

## Relationships

Each entity relationship stores:

- `object_type`
- `object_id`
- `source`
- `relationship_type`
- `where`
- `title`

Object types include:

- `experiment`
- `notebook_entry`
- `literature`
- `microscopy_asset`
- `graphpad_asset`
- `spreadsheet_asset`
- `statistical_analysis`
- `asset`

Related entities are ranked by co-occurrence across shared objects.

## API

Start the backend:

```bash
./scripts/demo.sh
```

Graph summary:

```bash
curl http://127.0.0.1:8001/knowledgegraph
```

Search entities:

```bash
curl "http://127.0.0.1:8001/knowledgegraph/search?q=SAG"
curl "http://127.0.0.1:8001/knowledgegraph/search?q=six"
```

Entity detail:

```bash
curl http://127.0.0.1:8001/knowledgegraph/entity/SAG
curl http://127.0.0.1:8001/knowledgegraph/entity/SIX6
curl http://127.0.0.1:8001/knowledgegraph/entity/BRN3B
```

Entities by type:

```bash
curl http://127.0.0.1:8001/knowledgegraph/type/compound
curl http://127.0.0.1:8001/knowledgegraph/type/marker
curl http://127.0.0.1:8001/knowledgegraph/type/gene
curl http://127.0.0.1:8001/knowledgegraph/type/cell_line
```

Experiment neighborhood:

```bash
curl http://127.0.0.1:8001/knowledgegraph/experiment/NK_Expt_31
```

## Example Entity Response

`GET /knowledgegraph/entity/SAG` returns:

```json
{
  "entity": "SAG",
  "entity_type": "compound",
  "experiments": [],
  "notebook_entries": [],
  "literature": [],
  "microscopy_assets": [],
  "graphpad_assets": [],
  "spreadsheet_assets": [],
  "statistics": [],
  "related_entities": [],
  "relationships": [],
  "relationship_counts": {},
  "summary": "SAG is indexed as compound..."
}
```

The exact counts depend on currently ingested local data.

## Testing

Run the graph tests:

```bash
cd backend
.venv/bin/python -m unittest tests.test_global_knowledge_graph
```

Run the full backend unit suite:

```bash
cd backend
.venv/bin/python -m unittest discover -s tests
```

The tests cover duplicate entity merging, case-insensitive lookup, alias
merging, refresh/rebuild behavior, entity search, experiment relationships,
notebook relationships, spreadsheet relationships, GraphPad relationships,
statistics relationships, literature relationships, image relationships,
unknown entity lookup, and larger synthetic graph build performance.
