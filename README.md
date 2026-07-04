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
│   │   ├── logging.py
│   │   └── main.py
│   ├── pyproject.toml
│   └── requirements.txt
├── data/
│   └── .gitkeep
├── docs/
│   ├── ARCHITECTURE.md
│   └── MVP_ROADMAP.md
├── frontend/
│   └── README.md
├── .env.example
├── .gitignore
├── LICENSE
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

## Microsoft Graph Auth Setup

ResearchOS uses Microsoft Authentication Library (MSAL) for delegated Microsoft
Graph login. This is required before future OneNote sync work can read notebook
data on behalf of a user.

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

## Configuration

Runtime settings are loaded from environment variables. See `.env.example` for
the supported keys.

The initial defaults are suitable for local development:

- SQLite database at `./data/researchos.db`
- ChromaDB persistence at `./data/chroma`
- API host `0.0.0.0`
- API port `8000`
- Microsoft Graph delegated auth values for future OneNote login

## Development Principles

ResearchOS is designed around a modular architecture:

- Keep domain modules independent.
- Prefer explicit configuration over hidden runtime behavior.
- Keep external integrations behind service boundaries.
- Treat laboratory data as sensitive by default.
- Build testable components before adding automation.

## License

ResearchOS is released under the MIT License. See [LICENSE](LICENSE).
