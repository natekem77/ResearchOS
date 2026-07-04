# ResearchOS Design Blueprint

ResearchOS is an AI-powered research operating system for scientific
laboratories. It is intended to connect the tools researchers already use with
AI-assisted search, summarization, comparison, planning, and writing workflows.

This document is the main architecture blueprint for the project. It describes
the product direction and the engineering boundaries that should guide future
development.

## 1. Project Vision

ResearchOS should help scientists preserve experimental context, find prior
work quickly, compare related experiments, and turn lab records into reusable
knowledge.

The project should support laboratories that already have existing workflows.
The first version should enhance those workflows rather than force a migration
to a new notebook system. Over time, ResearchOS should become a modular platform
for research operations across notes, protocols, data analysis, inventory,
literature, and experiment planning.

The core product goals are:

- Make laboratory knowledge searchable across tools.
- Keep source records linked to their original location.
- Generate useful summaries without hiding uncertainty.
- Help researchers compare experiments and protocols.
- Keep sensitive research data under clear user control.
- Allow labs to choose local or cloud AI providers.

## 2. MVP Scope: Read-Only OneNote AI Companion

The MVP is a read-only AI companion for Microsoft OneNote.

Researchers should be able to keep using OneNote while ResearchOS adds:

- Microsoft Graph delegated login.
- Read-only notebook discovery.
- Read-only page extraction.
- Local indexing of notebook content.
- AI-powered search across notes.
- Summaries of experiments and notebook sections.
- Comparison of related experiments.
- Draft protocol generation from prior notes.
- Source links back to the original OneNote pages.

The MVP must not modify OneNote content. Any generated summary, comparison, or
protocol draft should be stored separately from the source notebook unless a
future explicit write workflow is designed, reviewed, and enabled by the user.

Current non-goals:

- No OneNote write-back.
- No automatic edits to source notebooks.
- No multi-user production auth.
- No cloud deployment requirement.
- No image analysis, RNA-seq, inventory, or paper writing implementation yet.

## 3. Long-Term Modular Architecture

ResearchOS should be built as a modular platform rather than a OneNote-specific
application. OneNote is the first notebook provider, not the center of the
architecture.

Recommended backend shape:

```text
backend/app/
├── core/              # Shared app services, config, security, logging.
├── providers/         # External notebook and AI provider adapters.
├── modules/           # Product modules such as notes, protocols, inventory.
├── storage/           # Database, vector store, migrations, repositories.
├── api/               # FastAPI routers and request/response models.
└── jobs/              # Background sync and indexing tasks.
```

Long-term modules may include:

- Notebook ingestion and search.
- Microscopy image analysis.
- RNA-seq integration.
- Inventory management.
- Protocol versioning.
- Paper writing.
- Literature management.
- Experiment planning.

Modules should communicate through typed internal interfaces and shared domain
models. Vendor-specific code should stay in provider adapters so a module can
use OneNote, Markdown, or another source without rewriting the module itself.

## 4. Notebook Provider Interface

Notebook providers should expose a common read interface for discovering,
loading, and linking back to source records.

OneNote should be implemented first through Microsoft Graph. Future providers
should include Markdown folders, Obsidian vaults, and Notion workspaces.

The conceptual interface should support:

- Listing notebooks or workspaces.
- Listing sections, folders, or collections.
- Listing pages or documents.
- Fetching page content in a normalized format.
- Returning source metadata and stable source URLs.
- Reporting provider-specific sync state.

Example interface shape:

```python
from typing import Protocol


class NotebookProvider(Protocol):
    provider_name: str

    def list_collections(self) -> list[NotebookCollection]:
        ...

    def list_documents(self, collection_id: str) -> list[NotebookDocument]:
        ...

    def fetch_document(self, document_id: str) -> NotebookDocumentContent:
        ...
```

Planned providers:

- `onenote`: Microsoft OneNote through Microsoft Graph.
- `markdown`: Local Markdown directories.
- `obsidian`: Obsidian vaults with Markdown and metadata conventions.
- `notion`: Notion pages and databases through the Notion API.

Provider adapters should not decide how AI summaries work. They should only
provide normalized source content and metadata to the rest of the system.

## 5. AI Provider Interface

ResearchOS should start with an OpenAI-compatible interface because many hosted
and local tools support that API shape.

The first interface should support:

- Chat or response generation.
- Embedding generation.
- Model selection.
- Token and cost metadata where available.
- Optional local endpoint configuration.

Supported or planned AI providers:

- OpenAI.
- Claude.
- Gemini.
- Ollama.
- LM Studio.
- Local models behind an OpenAI-compatible server.

The interface should avoid tying application logic to a single vendor SDK.
Provider-specific code should live behind an adapter that can be swapped through
configuration.

Example interface shape:

```python
from typing import Protocol


class AIProvider(Protocol):
    provider_name: str

    def generate_text(self, prompt: str, *, model: str) -> AITextResult:
        ...

    def embed_texts(self, texts: list[str], *, model: str) -> list[list[float]]:
        ...
```

AI outputs should preserve citations or source references wherever possible.
For scientific workflows, generated text should clearly distinguish source
facts, inferred summaries, and speculative suggestions.

## 6. Data Model Overview

The initial storage plan uses SQLite for relational metadata and ChromaDB for
local vector search.

Core entities:

- `ProviderAccount`: a local connection to a notebook provider.
- `NotebookCollection`: a notebook, workspace, vault, folder, or database.
- `NotebookDocument`: a page, note, document, or lab record.
- `DocumentChunk`: a searchable text segment derived from a document.
- `EmbeddingRecord`: vector metadata associated with a chunk.
- `AISummary`: generated summaries tied to source documents or chunks.
- `Experiment`: normalized experiment metadata when it can be extracted.
- `Protocol`: generated or imported protocol content.
- `AuditEvent`: important local events such as sync, index, or generation.

SQLite should own durable structured records. ChromaDB should own vector index
state and enough metadata to resolve vectors back to SQLite records.

Source content should keep:

- Provider name.
- Provider object ID.
- Source title.
- Source URL or local path.
- Last observed modified timestamp.
- Content hash.
- Sync timestamp.

This makes indexing repeatable and helps prevent generated outputs from losing
their connection to source evidence.

## 7. Security and Privacy Model

ResearchOS should assume laboratory notes may contain sensitive, unpublished,
regulated, or proprietary information.

Default security posture:

- Read-only by default.
- Local-first storage.
- No hardcoded secrets.
- Environment-variable configuration.
- Optional cloud AI.
- Explicit source links for generated outputs.
- Clear separation between source data and AI-generated artifacts.

Read-only by default means provider integrations should request the minimum
delegated permissions needed to read source data. Write permissions should be
separate, optional, and reviewed before implementation.

Local-first storage means SQLite, ChromaDB, and generated artifacts should run
on the user's machine or lab-controlled infrastructure by default. Cloud storage
and cloud AI providers should be opt-in.

Secrets must never be committed. Local `.env` files, tokens, API keys, and
provider credentials should stay out of Git. Example files may show variable
names but must not include real credentials.

Microsoft Graph token storage is currently temporary development scaffolding.
Before production use, token storage must become encrypted, user-scoped,
revocable, and auditable.

## 8. Development Standards

ResearchOS should stay easy to understand and safe to extend.

Standards:

- Use type hints for new Python code.
- Use clear logging for startup, auth, sync, indexing, and AI operations.
- Keep modules small and focused.
- Keep `backend/requirements.txt` and `backend/pyproject.toml` updated together.
- Add tests for new functionality.
- Keep provider-specific code behind provider interfaces.
- Avoid hidden global state except for clearly marked development scaffolding.
- Keep public API responses free of secrets and raw tokens.
- Prefer explicit errors over silent fallback behavior.

New functionality should include:

- Typed request and response models.
- Unit tests for core behavior.
- Integration tests where external systems are mocked.
- Documentation updates when routes, settings, or workflows change.

## 9. Installation and Distribution Plan for Labmates

Early ResearchOS distribution should optimize for a small lab team that wants
to try the tool locally before any hosted deployment exists.

Planned installation path:

- Clone the GitHub repository.
- Install Python 3.12.
- Create a backend virtual environment.
- Install `backend/requirements.txt`.
- Copy `.env.example` to `.env`.
- Register a Microsoft Azure app for OneNote read access.
- Start the FastAPI backend locally.
- Open a local web UI once the frontend exists.

Near-term packaging improvements:

- Add a backend Dockerfile.
- Add a Docker Compose file for local SQLite and ChromaDB persistence.
- Add a setup script for common local development commands.
- Add health checks and smoke tests.
- Add clear troubleshooting docs for Azure app registration.

Long-term distribution options:

- Local desktop-style package.
- Lab server deployment.
- Docker Compose deployment.
- Optional managed cloud deployment for labs that want it.

Any distribution method must preserve the same privacy posture: local-first by
default, no hardcoded secrets, and explicit opt-in for cloud AI.

## 10. Milestone Roadmap

### Milestone 0: Repository Foundation

- Create GitHub-ready repository structure.
- Add FastAPI backend scaffold.
- Add configuration and logging.
- Add SQLite and ChromaDB configuration placeholders.
- Add architecture and roadmap docs.

### Milestone 1: Microsoft Graph Auth Scaffolding

- Add Microsoft Graph configuration.
- Add delegated login route.
- Add OAuth callback route.
- Add local development token status route.
- Keep token storage temporary and clearly marked.

### Milestone 2: OneNote Metadata Listing

- List notebooks, sections, and pages through Microsoft Graph.
- Return normalized metadata fields for early UI and integration work.
- Keep all OneNote access read-only.
- Handle missing delegated tokens with clear login guidance.
- Do not fetch full page content yet.

### Milestone 3: Local Indexing and Search

- Fetch page content in read-only mode.
- Store normalized metadata and content chunks in SQLite.
- Convert OneNote content into text chunks.
- Generate embeddings through the configured AI provider.
- Store vectors in ChromaDB.
- Add semantic search endpoints.

### Milestone 4: AI Research Workflows

- Summarize notebook sections and experiment records.
- Compare related experiments.
- Generate protocol drafts from prior notes.
- Include source references with generated outputs.

### Milestone 5: Frontend MVP

- Add a web UI for login, sync status, search, summaries, and comparisons.
- Provide clear source links back to OneNote.
- Make local setup usable by labmates without backend knowledge.

### Milestone 6: Provider and Module Expansion

- Add Markdown provider.
- Add Obsidian provider.
- Add Notion provider.
- Add protocol versioning.
- Add inventory and experiment planning foundations.
- Add optional microscopy and RNA-seq modules.
