# ResearchOS Architecture

ResearchOS is designed as a modular research operating system. The first module
will integrate with Microsoft OneNote, but the repository should support many
future laboratory workflows without turning the OneNote integration into the
center of the entire application.

## Guiding Principles

- Keep modules independent and explicit.
- Put shared platform concerns in common backend services.
- Keep vendor integrations behind adapters.
- Store normalized metadata separately from raw external content.
- Treat laboratory data as sensitive by default.
- Prefer observable background jobs over hidden automation.

## Initial Components

```text
backend/app/
├── config.py    # Environment-driven settings.
├── logging.py   # Process-wide logging configuration.
├── main.py      # FastAPI application entrypoint.
└── __init__.py  # Backend package metadata.
```

## Backend

The backend uses FastAPI as the API layer. The current application exposes only
`GET /health`, which is enough for local smoke tests, uptime probes, and future
container health checks.

As the application grows, new modules should be added as focused packages under
`backend/app`, for example:

```text
backend/app/
├── core/
├── modules/
│   ├── onenote/
│   ├── microscopy/
│   ├── rnaseq/
│   ├── inventory/
│   └── protocols/
└── services/
```

## Configuration

Configuration is loaded from environment variables with the `RESEARCHOS_`
prefix. This keeps local development, Docker, CI, and future hosted deployments
on the same configuration path.

The initial configuration includes:

- Project name
- Runtime environment
- Log level
- API host and port
- SQLite database URL
- ChromaDB persistence directory

## Storage

SQLite is the initial relational store. It is appropriate for early development,
local-first workflows, and simple deployment. The architecture should avoid
SQLite-specific assumptions in domain logic so a future migration to PostgreSQL
remains straightforward.

ChromaDB is the initial vector store. It will support semantic search over
research notes, protocols, and other laboratory records once ingestion exists.

## OneNote Module Boundary

The OneNote module should eventually own:

- Microsoft Graph authentication.
- Notebook and page synchronization.
- Content extraction and normalization.
- Source metadata and backlinks.
- Sync state and retry behavior.

It should not own unrelated research workflows such as inventory, microscopy, or
paper writing. Those should become separate modules that consume shared platform
services where appropriate.

## Future Docker Shape

The repository is ready for Docker-specific files, but they are intentionally
not included in this scaffold because the requested file list is limited.

A future container setup should include:

- Backend Dockerfile.
- Compose file for local development.
- Mounted data volume for SQLite and ChromaDB.
- Explicit environment variable wiring.
- Health check using `GET /health`.
