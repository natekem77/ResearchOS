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

OneNote synchronization is intentionally not implemented yet.

Microsoft Graph delegated authentication scaffolding is included for future
OneNote access. It currently supports login, callback handling, and local auth
status only. It is read-only with respect to Microsoft Graph and does not sync
OneNote content.

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
│   ├── DESIGN.md
│   └── MVP_ROADMAP.md
├── frontend/
│   └── README.md
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
./scripts/start.sh
./scripts/status.sh
./scripts/stop.sh
./scripts/restart.sh
```

The scripts use `backend/.venv`, start Uvicorn on `127.0.0.1:8001`, print the
health URL, and help recover from stuck port issues. Override the port for local
experiments with `RESEARCHOS_DEV_PORT`.

## Microsoft Graph Auth Setup

ResearchOS uses Microsoft Authentication Library (MSAL) for delegated Microsoft
Graph login. This is required before future OneNote sync work can read notebook
data on behalf of a user.

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

## OneNote Metadata Listing

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

## Local Markdown Ingestion and Search

Milestone 3 adds provider-agnostic local ingestion and search. It does not
require Microsoft auth.

Ingest the sample lab notes:

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

## Development Principles

ResearchOS is designed around a modular architecture:

- Keep domain modules independent.
- Prefer explicit configuration over hidden runtime behavior.
- Keep external integrations behind service boundaries.
- Treat laboratory data as sensitive by default.
- Build testable components before adding automation.

## License

ResearchOS is released under the MIT License. See [LICENSE](LICENSE).
