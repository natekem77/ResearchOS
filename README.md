# ResearchOS

ResearchOS is an AI-powered research operating system for scientific laboratories.

The first planned module is a Microsoft OneNote integration that allows researchers
to continue using OneNote while adding AI-powered search, summarization, protocol
generation, and experiment comparison.

This repository is currently a foundation, not a product implementation. It is
structured so future modules can be added without forcing a rewrite, including:

- Microscopy image analysis
- RNA-seq integration
- Inventory management
- Protocol versioning
- Paper writing
- Literature management
- Experiment planning

## Current Scope

This initial scaffold includes:

- Python 3.12 backend
- FastAPI application
- SQLite-ready configuration
- ChromaDB-ready configuration
- Environment-based settings
- Structured logging setup
- Docker-ready project layout
- Documentation for architecture and MVP planning

The core system health endpoint is:

```http
GET /health
```

Response:

```json
{
  "status": "ok",
  "project": "ResearchOS"
}
```

Read-only OneNote page sync is implemented behind Microsoft Graph delegated
login. Real UCSD notebook access still requires tenant consent or a UCSD-owned
app registration before lab OneNote content can be synced.

## Run The Demo In One Command

After creating `backend/.venv` and installing `backend/requirements.txt`, run:

```bash
./scripts/demo.sh
```

The script restarts the backend, waits for `/health`, loads sample lab notes,
and prints the dashboard URL:

```text
http://127.0.0.1:8001
```

For the PI/lab walkthrough, use [docs/DEMO_CHECKLIST.md](docs/DEMO_CHECKLIST.md).

## ResearchOS v0.1 Demo Release

This repository is prepared as a `v0.1 demo` for PI/lab discussion and UCSD IT
handoff. The demo is local-first, uses bundled sample notes/paper records, and
does not require UCSD OneNote access.

Start the demo:

```bash
./scripts/demo.sh
```

Run the endpoint smoke test after the backend is running:

```bash
./scripts/smoke_test.sh
```

Release notes:

- [docs/V0_1_DEMO_RELEASE_NOTES.md](docs/V0_1_DEMO_RELEASE_NOTES.md)
- [docs/DEMO_CHECKLIST.md](docs/DEMO_CHECKLIST.md)
- [docs/UCSD_IT_APPROVAL_REQUEST.md](docs/UCSD_IT_APPROVAL_REQUEST.md)

## What Works Today

- Local FastAPI backend and browser dashboard.
- Markdown demo note ingestion.
- SQLite document and experiment storage.
- Local chunking, vector indexing, and keyword fallback search.
- Structured experiment extraction.
- Retinal organoid entity pages for compounds, markers, cell lines, and batches.
- Knowledge Graph Explorer for connected experiments, papers, protocols, and entities.
- Local literature ingestion for paper notes and PDFs.
- Scientific research assistant with local fallback answers.
- Provider status Settings page.
- Read-only Microsoft Graph auth and OneNote sync pipeline scaffolding.
- Optional OpenAI-compatible AI chat when configured.

## What Needs UCSD IT Approval

Real UCSD OneNote access needs Microsoft tenant approval or a UCSD-owned app
registration for the ResearchOS Development app. The requested initial Graph
permissions are delegated and read-only: `User.Read`, `Notes.Read`, `openid`,
`profile`, and `offline_access`.

See [docs/UCSD_IT_APPROVAL_REQUEST.md](docs/UCSD_IT_APPROVAL_REQUEST.md) for the
email-ready approval request.

## Repository Layout

```text
ResearchOS/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── graph_auth.py
│   │   ├── graph_client.py
│   │   ├── logging.py
│   │   ├── main.py
│   │   └── onenote_provider.py
│   ├── pyproject.toml
│   └── requirements.txt
├── data/
│   └── .gitkeep
├── docs/
│   ├── ARCHITECTURE.md
│   ├── AZURE_APP_SETUP.md
│   ├── CORE_ARCHITECTURE.md
│   ├── DEMO_CHECKLIST.md
│   ├── DEMO_SCRIPT.md
│   ├── DESIGN.md
│   └── MVP_ROADMAP.md
├── frontend/
│   ├── README.md
│   ├── app.js
│   ├── index.html
│   └── styles.css
├── .env.example
├── .gitignore
├── LICENSE
├── samples/
│   └── lab_notes/
└── README.md
```

## Backend Quickstart

Requirements:

- Python 3.12

Create and activate a virtual environment:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Copy environment defaults:

```bash
cp ../.env.example ../.env
```

Run the API:

```bash
uvicorn app.main:app --reload
```

Check health:

```bash
curl http://127.0.0.1:8000/health
```

For Milestone 3 local ingestion and search development, run on port `8001`:

```bash
cd backend
source .venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

## Development Scripts

WSL/Linux development scripts are available for managing the local backend on
port `8001`:

```bash
./scripts/demo.sh
./scripts/start.sh
./scripts/status.sh
./scripts/stop.sh
./scripts/restart.sh
```

The scripts use `backend/.venv`, start Uvicorn on `127.0.0.1:8001`, print the
health URL, and help recover from stuck port issues. Override the port for local
experiments with `RESEARCHOS_DEV_PORT`.

For Windows setup, see [docs/INSTALL_WINDOWS_WSL.md](docs/INSTALL_WINDOWS_WSL.md).
For common failure modes, see [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Web UI Demo

The backend serves the ResearchOS dashboard at:

```text
http://127.0.0.1:8001
```

Launch the backend:

```bash
./scripts/start.sh
```

Load sample data for the demo:

```bash
curl -X POST http://127.0.0.1:8001/ingest/markdown \
  -H "Content-Type: application/json" \
  -d '{"folder_path":"../samples/lab_notes"}'
```

Then open `http://127.0.0.1:8001` in a browser. The dashboard includes top
navigation, provider/sync status, sidebar navigation, metrics, recent activity,
experiments, documents, search, and AI chat when a provider is configured.

## Knowledge Graph Explorer

The dashboard includes a Graph Explorer page at:

```text
http://127.0.0.1:8001/#/graph
```

Useful local graph endpoints:

```bash
curl http://127.0.0.1:8001/graph/stats
curl http://127.0.0.1:8001/graph/entity/compounds/SAG
curl http://127.0.0.1:8001/graph/entity/markers/BRN3B
```

The graph is local-first and derived from SQLite documents, extracted
experiments, ingested literature, and protocol notes.

## Provider Status

ResearchOS exposes a provider status endpoint for the dashboard Settings page:

```bash
curl http://127.0.0.1:8001/status/providers
```

It reports backend health, Markdown demo provider status, Microsoft Graph
OneNote auth state, OneNote sync availability, AI provider configuration, local
database status, vector index status, document count, and experiment count.

The Settings page uses this endpoint to show integration cards and actions:

- Load demo notes
- Sync OneNote
- Test AI chat
- Show UCSD IT approval instructions

If OneNote sync is blocked because Microsoft Graph is not connected or UCSD
tenant approval is still pending, the UI shows the returned message directly.

## Scientific Research Assistant

Ask structured scientific questions with local fallback support:

```bash
curl -X POST http://127.0.0.1:8001/assistant/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Which experiments used SAG?"}'
```

The assistant combines document search, structured experiments, ontology
entities, and source snippets. If an AI provider is configured, it adds AI
synthesis. If no AI provider is configured, it still returns a local evidence
answer.

Entity-specific questions are filtered for direct matches first. For example,
SAG questions only include SAG experiments unless the user asks for a comparison.

Suggested demo prompts:

- Compare our SAG experiments with the literature.
- What does the literature say about BMP4 timing?
- Do our SIX6/BRN3B results match published expectations?
- Which experiments used SAG?
- Compare BMP4 and SAG experiments.
- What markers were used with BRN3B?
- Summarize retinal organoid differentiation notes.

See [docs/AI_RESEARCH_ASSISTANT.md](docs/AI_RESEARCH_ASSISTANT.md) for endpoint
details and response shape.

## Experiment Comparison

Compare structured experiment records side-by-side:

```bash
curl -X POST http://127.0.0.1:8001/experiments/compare \
  -H "Content-Type: application/json" \
  -d '{"experiment_ids":["<experiment-id-1>","<experiment-id-2>"]}'
```

The response includes shared features, differences, a likely scientific
interpretation, limitations, and the source experiment records. The Experiments
page also has checkboxes and a **Compare selected** button for the same workflow.

## Lab-Literature Comparison

Compare internal experiments against ingested literature:

```bash
curl -X POST http://127.0.0.1:8001/assistant/compare-literature \
  -H "Content-Type: application/json" \
  -d '{"question":"Compare our SAG experiments with the literature.","use_ai":false}'
```

The response separates matching lab experiments, matching literature sources,
similarities, differences, protocol/treatment differences, limitations, and
source snippets. It works locally without an AI key, and uses a configured AI
provider for synthesis when available.

The dashboard and AI Chat page include a **Compare with literature** button.
Load demo notes, ingest papers, enter a question such as `Do our SIX6/BRN3B
results match published expectations?`, then click **Compare with literature**.

## Voice-To-Experiment Entry Drafts

Prototype a dictated experiment entry:

```bash
curl -X POST http://127.0.0.1:8001/entries/draft \
  -H "Content-Type: application/json" \
  -d '{"dictation":"Create NK Expt 31. Day 1 SAG plus GRK inhibitor. Treat with 100 nM SAG from D18 to D24. DMSO vehicle control. Planned readouts brightfield and BRN3B staining."}'
```

The dashboard includes a **New Experiment** page with a dictation text area,
structured Markdown preview, and disabled **Save to OneNote** placeholder.
Write-back requires UCSD IT approval and Microsoft Graph permissions such as
`Notes.Create` or `Notes.ReadWrite`.

Export a reviewed draft as local Markdown:

```bash
curl -X POST http://127.0.0.1:8001/entries/export-markdown \
  -H "Content-Type: application/json" \
  -d '{"filename":"nk-expt-31.md","markdown":"# NK-EXPT-31\n\nReviewed local draft."}'
```

See [docs/VOICE_ENTRY_DESIGN.md](docs/VOICE_ENTRY_DESIGN.md) and
[docs/ONENOTE_WRITEBACK_DESIGN.md](docs/ONENOTE_WRITEBACK_DESIGN.md).

## Retinal Organoid Intelligence

ResearchOS now builds a retinal organoid ontology from provider-agnostic
documents and extracted experiments. It links experiment IDs, cell lines,
organoid batches, differentiation days, compounds, concentrations, treatment
windows, markers, cell types, imaging modalities, RNA-seq, flow cytometry, and
protocols.

Ontology pages:

```text
http://127.0.0.1:8001/compounds
http://127.0.0.1:8001/markers
http://127.0.0.1:8001/cell-lines
http://127.0.0.1:8001/organoid-batches
```

Clicking an entity such as `BMP4`, `SAG`, `SIX6`, or `BRN3B` shows linked
experiments, protocols, documents, images, and AI summaries when available.

Ontology API examples:

```bash
curl http://127.0.0.1:8001/ontology/compounds
curl http://127.0.0.1:8001/ontology/compounds/BMP4
curl http://127.0.0.1:8001/ontology/markers/SIX6
```

## Screenshots

Screenshots should be added here as the UI stabilizes:

- Dashboard overview
- Experiments table
- Experiment detail page
- Search results with highlighted markers and compounds
- AI chat with source snippets

Recommended capture path:

1. Run `./scripts/restart.sh`.
2. Open `http://127.0.0.1:8001`.
3. Click **Load demo notes**.
4. Capture the dashboard and experiment detail views.

## 5-Minute Lab Demo

Use this flow for a quick lab-member demo:

1. Start the backend:

```bash
./scripts/restart.sh
```

2. Open the web UI:

```text
http://127.0.0.1:8001
```

3. Click **Load demo notes**.
4. Open Literature and click **Ingest papers**.
5. Show the Documents, Experiments, and Literature panels.
6. Search:

```text
SAG BRN3B staining
```

7. Ask chat:

```text
What do the SAG and BRN3B notes suggest?
```

8. Click **Compare with literature** using:

```text
Compare our SAG experiments with the literature.
```

The demo uses local Markdown notes, so it does not require Microsoft or UCSD
tenant approval. See [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) for a short
presentation script.

Presentation-ready materials:

- [Lab demo talk track](docs/LAB_DEMO_TALK_TRACK.md)
- [PI one-page summary](docs/PI_ONE_PAGE_SUMMARY.md)
- [UCSD IT approval request](docs/UCSD_IT_APPROVAL_REQUEST.md)
- [Windows/WSL install guide](docs/INSTALL_WINDOWS_WSL.md)
- [Troubleshooting guide](docs/TROUBLESHOOTING.md)
- [AI research assistant](docs/AI_RESEARCH_ASSISTANT.md)
- [Literature ingestion](docs/LITERATURE_INGESTION.md)
- [Voice entry design](docs/VOICE_ENTRY_DESIGN.md)
- [OneNote write-back design](docs/ONENOTE_WRITEBACK_DESIGN.md)

## Microsoft Graph Auth Setup

ResearchOS uses Microsoft Authentication Library (MSAL) for delegated Microsoft
Graph login. This is required before OneNote sync can read notebook data on
behalf of a user.

For detailed Azure app registration steps, see
[docs/AZURE_APP_SETUP.md](docs/AZURE_APP_SETUP.md).

Before using real login, register an Azure app in the Microsoft Entra admin
center:

- Application type: public client or single-page/native style development app.
- Redirect URI: `http://localhost:8000/auth/callback`
- Delegated Graph permissions: start with `User.Read` and `Notes.Read`
- Client secret: not required for this local delegated public-client scaffold.

Then set the values in `.env`:

```bash
MICROSOFT_CLIENT_ID=<your-azure-app-client-id>
MICROSOFT_TENANT_ID=common
MICROSOFT_REDIRECT_URI=http://localhost:8000/auth/callback
GRAPH_SCOPES="User.Read Notes.Read"
```

Auth routes:

```http
GET /auth/login
GET /auth/callback
GET /auth/status
```

Token storage is temporary and local-development only. Tokens are stored in
process memory, are not encrypted, are not user-scoped, and disappear when the
API restarts. Replace this before handling real laboratory data.

## OneNote Metadata Listing And Sync

After completing Microsoft Graph login, the backend can list OneNote metadata in
read-only mode:

```http
GET /onenote/notebooks
GET /onenote/sections
GET /onenote/pages
```

Optional filters:

```bash
curl "http://127.0.0.1:8000/onenote/sections?notebook_id=<notebook-id>"
curl "http://127.0.0.1:8000/onenote/pages?section_id=<section-id>"
```

These endpoints return notebook, section, and page metadata only. They do not
fetch full page content and do not write to OneNote.

Read-only page sync is available after login:

```bash
curl -X POST http://127.0.0.1:8001/sync/onenote
```

The sync pipeline fetches notebooks, sections, pages, and page HTML content,
converts pages to clean text, stores them as `ResearchDocument` records with
`provider="onenote"`, then reuses the existing chunking, vector indexing,
search, and experiment extraction pipeline.

If Microsoft Graph is not connected, the endpoint returns a clear setup message.
If UCSD tenant consent, licensing, or notebook access blocks the request, the
endpoint returns the Microsoft Graph error with guidance to request tenant
approval.

## Local Markdown Ingestion and Search

Milestone 3 adds provider-agnostic local ingestion and search. It does not
require Microsoft auth.

Ingest the sample lab notes:

```bash
curl -X POST http://127.0.0.1:8001/ingest/markdown
```

Or pass a custom folder:

```bash
curl -X POST http://127.0.0.1:8001/ingest/markdown \
  -H "Content-Type: application/json" \
  -d '{"folder_path":"../samples/lab_notes"}'
```

Markdown ingestion stores documents, chunks text for search, updates the local
vector index, and automatically extracts structured experiment records when
experiment-like fields are detected.

List documents:

```bash
curl http://127.0.0.1:8001/documents
```

Get one document:

```bash
curl "http://127.0.0.1:8001/documents/<document-id>"
```

Search documents. This works without an AI provider because SQLite keyword
search is available as a fallback:

```bash
curl -X POST http://127.0.0.1:8001/search \
  -H "Content-Type: application/json" \
  -d '{"query":"SAG BRN3B staining","limit":5}'
```

Chat with a configured AI provider:

```bash
curl -X POST http://127.0.0.1:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Summarize the SAG experiment and staining result."}'
```

If no AI provider is configured, `/chat` returns a setup error. `/search`
continues to work locally.

## Literature Ingestion

ResearchOS can ingest local paper notes and PDFs from:

```text
samples/papers/
data/papers/
```

Ingest papers:

```bash
curl -X POST http://127.0.0.1:8001/ingest/papers
```

List papers:

```bash
curl http://127.0.0.1:8001/papers
```

Search across lab notes and literature:

```bash
curl -X POST http://127.0.0.1:8001/search \
  -H "Content-Type: application/json" \
  -d '{"query":"BRN3B immunostaining literature","limit":5}'
```

Ask the assistant with literature context separated from lab notebook evidence:

```bash
curl -X POST http://127.0.0.1:8001/assistant/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"What does the literature say about BRN3B staining?"}'
```

PDF text extraction uses `pypdf`; text and Markdown paper notes work for local
demo use even when no PDFs are available. See
[docs/LITERATURE_INGESTION.md](docs/LITERATURE_INGESTION.md).

Compare lab experiments against literature:

```bash
curl -X POST http://127.0.0.1:8001/assistant/compare-literature \
  -H "Content-Type: application/json" \
  -d '{"message":"Do our SIX6/BRN3B results match published expectations?","use_ai":false}'
```

## AI Chat Setup

ResearchOS chat uses an OpenAI-compatible provider abstraction. Do not hardcode
API keys; set them in `.env`.

OpenAI:

```bash
AI_PROVIDER=openai_compatible
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=<your-openai-api-key>
AI_MODEL=gpt-4o-mini
```

OpenRouter:

```bash
AI_PROVIDER=openai_compatible
AI_BASE_URL=https://openrouter.ai/api/v1
AI_API_KEY=<your-openrouter-api-key>
AI_MODEL=openai/gpt-4o-mini
```

LM Studio:

```bash
AI_PROVIDER=openai_compatible
AI_BASE_URL=http://localhost:1234/v1
AI_API_KEY=
AI_MODEL=<loaded-local-model>
```

Ollama with an OpenAI-compatible endpoint:

```bash
AI_PROVIDER=openai_compatible
AI_BASE_URL=http://localhost:11434/v1
AI_API_KEY=
AI_MODEL=llama3.1
```

Chat returns an assistant answer and the source chunks used for retrieval:

```bash
curl -X POST http://127.0.0.1:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What do the SAG and BRN3B notes suggest?","use_search_context":true,"limit":5}'
```

`/chat` also accepts `question`:

```bash
curl -X POST http://127.0.0.1:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"What do the SAG and BRN3B notes suggest?","limit":5}'
```

## Experiment Extraction

ResearchOS can extract structured scientific experiments from provider-agnostic
documents. The current extractor is regex-first and designed so future LLM
extractors can plug into the same pipeline.

Run extraction manually across all stored documents:

```bash
curl -X POST http://127.0.0.1:8001/extract \
  -H "Content-Type: application/json" \
  -d '{}'
```

Extract from one document:

```bash
curl -X POST http://127.0.0.1:8001/extract \
  -H "Content-Type: application/json" \
  -d '{"document_id":"<document-id>"}'
```

List extracted experiments:

```bash
curl http://127.0.0.1:8001/experiments
```

Get one extracted experiment:

```bash
curl "http://127.0.0.1:8001/experiments/<experiment-id>"
```

The extracted schema includes experiment ID, date, researcher, cell line,
organoid batch, compounds, treatments, concentrations, time points, markers,
antibodies, imaging methods, sequencing, notes, and conclusions when present.

## Configuration

Runtime settings are loaded from environment variables. See `.env.example` for
the supported keys.

The initial defaults are suitable for local development:

- SQLite database at `./data/researchos.db`
- ChromaDB persistence at `./data/chroma`
- API host `0.0.0.0`
- API port `8000`
- Microsoft Graph delegated auth values for future OneNote login

## Design Blueprint

See [docs/DESIGN.md](docs/DESIGN.md) for the main ResearchOS architecture
blueprint, including MVP scope, provider interfaces, security model, development
standards, distribution plan, and milestone roadmap.

See [docs/CORE_ARCHITECTURE.md](docs/CORE_ARCHITECTURE.md) for the local
document ingestion, SQLite, vector search, and AI provider architecture.

See [docs/ONENOTE_SYNC_DESIGN.md](docs/ONENOTE_SYNC_DESIGN.md) for the planned
read-only OneNote sync architecture and Microsoft Graph integration design.

## Development Principles

ResearchOS is designed around a modular architecture:

- Keep domain modules independent.
- Prefer explicit configuration over hidden runtime behavior.
- Keep external integrations behind service boundaries.
- Treat laboratory data as sensitive by default.
- Build testable components before adding automation.

## License

ResearchOS is released under the MIT License. See [LICENSE](LICENSE).
