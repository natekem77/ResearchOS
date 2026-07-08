# Laboratory Intelligence Feed

Laboratory Intelligence is ResearchOS's proactive attention feed. It summarizes important developments across the local lab workspace without waiting for a user to search.

The feed is deterministic by default. It never invents scientific observations. Every item must reference one or more provenance records such as an experiment, notebook document, asset, resource, workflow, session, literature record, or knowledge graph summary.

## Feed Sources

ResearchOS builds feed items from existing local records:

- Experiments and extracted notebook metadata
- Workflow stages and blocking issues
- Active experiment sessions
- GraphPad and statistics assets
- Spreadsheets and microscopy/image assets
- Literature documents
- Research Resources
- Knowledge Graph summaries
- Scientific Memory similarity results
- Research Copilot gap checks

The service does not maintain a duplicate scientific database. It dynamically derives feed items from provider metadata already stored in SQLite and the Knowledge Graph.

## Feed Item Types

Current item types include:

- Experiment Reminder
- Workflow Reminder
- Missing Analysis
- Missing Notebook
- Protocol Insight
- Statistical Finding
- Knowledge Graph Insight
- New Literature
- Similar Experiment
- Resource Warning
- Copilot Recommendation

## Feed Item Schema

Each item contains:

- `item_id`: stable deterministic ID
- `item_type`: category
- `title`
- `summary`
- `priority`: `critical`, `high`, `medium`, or `low`
- `timestamp`
- `related_experiments`
- `related_resources`
- `related_literature`
- `suggested_action`
- `provenance`
- `pinned`
- `dismissed`

Dismiss and pin state is stored separately from the generated scientific content.

## API

```bash
curl http://127.0.0.1:8001/intelligence/feed
curl "http://127.0.0.1:8001/intelligence/feed?item_type=Missing%20Analysis"
curl -X POST http://127.0.0.1:8001/intelligence/feed/feed:ITEM_ID/pin \
  -H "Content-Type: application/json" \
  -d '{"pinned":true}'
curl -X POST http://127.0.0.1:8001/intelligence/feed/feed:ITEM_ID/dismiss
```

Mobile clients should use the compact endpoint:

```bash
curl http://127.0.0.1:8001/mobile/intelligence/feed
```

## Dashboard and Mobile

The browser dashboard uses the Laboratory Intelligence feed as its primary "Today" panel. Users can:

- View newest and highest-priority items first
- Filter by item type
- Pin important items
- Dismiss items that have been reviewed

The Flutter mobile preview includes a dedicated Intelligence Feed page.

## Provenance Rules

Every feed item must include supporting provenance. Examples:

- Missing analysis item: experiment row from SQLite
- Statistical finding: asset row and parsed statistics metadata
- New literature: literature document
- Resource warning: resource record
- Knowledge graph insight: dynamic Knowledge Graph summary

If ResearchOS cannot point to a source, it should not create the item.

## Future Extensions

Future providers can contribute to Laboratory Intelligence by publishing events and storing structured metadata. The feed service should continue to consume provider-agnostic metadata rather than adding provider-specific coupling.

Likely future contributors:

- OneNote sync
- PubMed monitoring
- Folder watchers
- Sequencing providers
- Flow cytometry providers
- Microscopy image analysis
- Protocol version monitoring
- Lab inventory expiration checks
