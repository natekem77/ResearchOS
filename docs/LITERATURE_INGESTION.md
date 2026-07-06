# Literature Ingestion

ResearchOS can ingest local paper files so search and the scientific assistant can
separate published literature context from lab notebook context.

This foundation is local-first. Files are read from disk, converted into
provider-agnostic `ResearchDocument` records with `provider="literature"`,
chunked, stored in SQLite, and indexed with the same search pipeline used for
Markdown and OneNote documents.

## Local Folders

ResearchOS scans these folders by default:

```text
samples/papers/
data/papers/
```

Use `samples/papers/` for demo notes and examples. Use `data/papers/` for local
development files that should stay on the machine.

Supported extensions:

- `.pdf`
- `.txt`
- `.md`

PDF text extraction uses `pypdf`. If no PDFs are present, the sample text and
Markdown paper notes still demonstrate the workflow.

## Ingest Papers

Start the backend:

```bash
./scripts/restart.sh
```

Ingest papers:

```bash
curl -X POST http://127.0.0.1:8001/ingest/papers
```

List ingested papers:

```bash
curl http://127.0.0.1:8001/papers
```

Get one paper:

```bash
curl "http://127.0.0.1:8001/papers/<paper-id>"
```

If no supported files exist under `samples/papers/` or `data/papers/`, the
ingestion endpoint returns a clear message instead of failing.

## Metadata Extraction

ResearchOS extracts lightweight metadata when possible:

- Title
- Authors
- Year
- Journal
- DOI
- Abstract
- Compounds
- Markers and genes
- Cell types
- Methods

For text or Markdown notes, simple labels such as `Title:`, `Authors:`, `Year:`,
`Journal:`, `DOI:`, and `Abstract:` improve extraction quality.

## Search And Assistant Context

Search includes literature chunks automatically:

```bash
curl -X POST http://127.0.0.1:8001/search \
  -H "Content-Type: application/json" \
  -d '{"query":"BRN3B immunostaining literature","limit":5}'
```

The research assistant reports literature context separately from lab notebook
evidence:

```bash
curl -X POST http://127.0.0.1:8001/assistant/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"What does the literature say about BRN3B staining?"}'
```

If an AI provider is configured, ResearchOS can use the retrieved literature in
its synthesis. Without an AI provider, the local fallback still returns matching
experiments, source snippets, extracted facts, and separate literature context.

## Future Work

This milestone does not implement citation graph management, PubMed lookup,
Zotero/Mendeley import, full PDF layout reconstruction, or paper-to-experiment
claim comparison. The current goal is a small, reliable ingestion foundation that
can be extended without blocking OneNote or Markdown development.
