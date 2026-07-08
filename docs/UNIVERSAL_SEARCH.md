# Universal Scientific Search

Universal Scientific Search is the global ResearchOS search layer. It is meant
to feel like Spotlight or a command palette: one fast search box that finds
experiments, notebook entries, Knowledge Graph entities, assets, quantitative
data, literature, timeline events, and useful commands.

## Endpoint

```http
GET /search/universal?q={query}
```

Example:

```bash
curl "http://127.0.0.1:8001/search/universal?q=SAG"
curl "http://127.0.0.1:8001/search/universal?q=D32"
curl "http://127.0.0.1:8001/search/universal?q=BRN3B"
curl "http://127.0.0.1:8001/search/universal?q=%22SAG%20D32%22"
curl "http://127.0.0.1:8001/search/universal?q=SAG%20BRN3B&limit_per_group=5"
```

Response shape:

```json
{
  "query": "SAG",
  "total_results": 12,
  "grouped_results": {
    "experiments": [],
    "notebook_entries": [],
    "entities": [],
    "images": [],
    "graphpad": [],
    "spreadsheets": [],
    "statistics": [],
    "literature": [],
    "timeline": [],
    "commands": []
  },
  "suggested_queries": [],
  "related_entities": []
}
```

Each result includes:

- `id`
- `type`
- `title`
- `subtitle`
- `provider`
- `href`
- `score`
- `updated_at`
- `metadata`

## Search Sources

The universal index is built from existing ResearchOS records:

- Notebook entries
- Experiments
- Knowledge Graph entities
- Microscopy/image assets
- GraphPad assets
- Spreadsheet assets
- Statistics assets
- Literature documents
- Timeline events derived from experiments and linked assets
- Command shortcuts

Future providers should store useful titles, identifiers, paths, metadata, and
provider names in SQLite. The Universal Search service can then include them
without a provider-specific database.

## Matching Behavior

Universal Search supports:

- Case-insensitive matching
- Exact matches
- Partial matches
- Lightweight fuzzy matching
- Quoted phrases
- Multiple keywords

Ranking considers:

- Exact title matches
- Prefix and partial title matches
- Body/metadata matches
- Entity and experiment relevance
- Provider confidence
- Knowledge Graph relationships

## UI

Use the global search button in the top navigation or press:

```text
Ctrl+K
Cmd+K
```

Results update while typing and are grouped by category. Clicking a result
navigates directly to the matching ResearchOS object when a route is available.

## Examples

`SAG` should return matching experiments, notebook pages, GraphPad/statistics
assets, spreadsheets, images, literature, and the SAG Knowledge Graph entity.

`D32` should return timeline events, experiments, images, and notebook entries
where day/timepoint metadata mentions D32.

`BRN3B` should return every indexed object that mentions BRN3B, including
markers, staining notes, microscopy files, statistics, spreadsheets, and related
experiments.

## Limitations

- Search is local-first and only covers data already ingested or registered.
- Fuzzy matching is intentionally lightweight.
- Ranking is deterministic and does not require an AI provider.
- The service does not invent missing metadata; providers should preserve
  unknown scientific terms in metadata so they can be indexed.
