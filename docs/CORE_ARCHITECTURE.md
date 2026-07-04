# ResearchOS Core Architecture

This document describes the provider-agnostic ingestion, storage, search, and AI
foundation used by ResearchOS.

The core is intentionally independent from Microsoft OneNote. OneNote remains a
future notebook provider, but local Markdown ingestion lets development continue
without Microsoft tenant approval.

## ResearchDocument

`ResearchDocument` is the normalized document model for ResearchOS.

Every notebook or document provider should map its native data into this shape:

- `id`: stable ResearchOS document ID.
- `provider`: source provider name, such as `markdown` or `onenote`.
- `source_id`: provider-native identifier.
- `title`: human-readable document title.
- `content`: source text for indexing and AI context.
- `source_path`: local file path when available.
- `source_url`: provider URL when available.
- `created_at` and `updated_at`: provider timestamps when available.
- `metadata`: provider-specific string metadata.

The model lives in `backend/app/research_document.py`.

## Provider Model

Providers are adapters. Their job is to load external or local source data and
normalize it into `ResearchDocument`.

Current provider:

- Markdown folder provider in `backend/app/markdown_provider.py`.

Planned providers:

- OneNote through Microsoft Graph.
- Obsidian vaults.
- Notion workspaces.
- Local protocol folders.

Provider code should not own search, AI prompts, storage, or indexing behavior.
Those are shared platform concerns.

## Ingestion Pipeline

The ingestion pipeline is:

1. Provider loads source records.
2. Provider returns `ResearchDocument` instances.
3. The chunker splits document content into `DocumentChunk` records.
4. SQLite stores documents and chunks.
5. The vector index stores chunk vectors and metadata.

The Markdown ingestion endpoint is:

```http
POST /ingest/markdown
```

Default local sample folder:

```text
../samples/lab_notes
```

## SQLite

SQLite stores durable local records:

- `documents`
- `chunks`

SQLite is local-first and simple for early development. It is used for document
listing, document detail, and keyword fallback search.

The current database URL is configured through:

```bash
RESEARCHOS_DATABASE_URL=sqlite:///./data/researchos.db
```

Relative paths resolve from the repository root.

## Vector Search

The vector index abstraction lives in `backend/app/vector_index.py`.

Current implementation:

- `ChromaVectorIndex`
- Persistent local ChromaDB collection
- Deterministic local hash embeddings for development

The deterministic embedding is not a semantic model. It exists so the ChromaDB
integration can be exercised without API keys, downloads, or cloud calls.

`POST /search` attempts vector search first and falls back to SQLite keyword
search when vector results are unavailable. Keyword search works before any AI
provider is configured.

## AI Provider Abstraction

The AI provider interface lives in `backend/app/ai_providers.py`.

Current providers:

- `OpenAICompatibleProvider`: works with OpenAI-compatible chat completion APIs.
- Ollama and LM Studio: supported through custom OpenAI-compatible base URLs.
- `ClaudeProvider`: placeholder that returns a clear not-implemented error.

Configuration:

```bash
RESEARCHOS_AI_PROVIDER=none
RESEARCHOS_AI_API_KEY=
RESEARCHOS_AI_BASE_URL=
RESEARCHOS_AI_MODEL=gpt-4o-mini
```

Examples:

```bash
RESEARCHOS_AI_PROVIDER=ollama
RESEARCHOS_AI_BASE_URL=http://localhost:11434/v1
RESEARCHOS_AI_MODEL=llama3.1
```

```bash
RESEARCHOS_AI_PROVIDER=lmstudio
RESEARCHOS_AI_BASE_URL=http://localhost:1234/v1
RESEARCHOS_AI_MODEL=local-model
```

If no provider is configured, `POST /chat` returns a helpful setup error instead
of silently pretending to answer.

## How OneNote Plugs In Later

The existing OneNote code already handles Microsoft Graph login and metadata
listing. Future OneNote ingestion should add a provider that:

1. Uses the Microsoft Graph auth/token scaffold.
2. Reads OneNote pages in read-only mode.
3. Converts page metadata and text into `ResearchDocument`.
4. Sends those documents through the same chunking, SQLite, vector, search, and
   AI pipeline used by Markdown.

This keeps OneNote as one provider among many rather than a special-case core
architecture.
