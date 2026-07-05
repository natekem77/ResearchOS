"""FastAPI entrypoint for the ResearchOS backend."""

import logging
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.ai_providers import AIProviderError, get_ai_provider
from app.config import get_settings
from app.experiment_extraction import extract_experiment
from app.graph_auth import build_auth_url, exchange_code_for_token, get_token_status
from app.graph_client import GraphRequestError, MissingGraphTokenError
from app.ingestion import ingest_markdown_folder
from app.logging import configure_logging
from app.onenote_provider import list_notebooks, list_pages, list_sections
from app.storage import SQLiteStore
from app.vector_index import ChromaVectorIndex

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"

app = FastAPI(
    title=settings.project_name,
    description="AI-powered research operating system for scientific laboratories.",
    version="0.1.0",
)

if FRONTEND_DIR.exists():
    app.mount(
        "/frontend-assets",
        StaticFiles(directory=FRONTEND_DIR),
        name="frontend-assets",
    )


class HealthResponse(BaseModel):
    """Response model for the health check endpoint."""

    status: Literal["ok"]
    project: Literal["ResearchOS"]


class AuthStatusResponse(BaseModel):
    """Safe authentication status response.

    This model intentionally excludes access tokens and refresh tokens.
    """

    authenticated: bool
    expires_at: int | None
    scopes: list[str]
    token_type: str | None


class OneNoteMetadataResponse(BaseModel):
    """Read-only OneNote metadata response.

    Page content is intentionally excluded at this milestone.
    """

    id: str
    displayName: str | None = None
    title: str | None = None
    createdDateTime: str | None = None
    lastModifiedDateTime: str | None = None


class MarkdownIngestRequest(BaseModel):
    """Request body for local Markdown ingestion."""

    folder_path: str = "../samples/lab_notes"


class IngestResponse(BaseModel):
    """Summary of a document ingestion run."""

    provider: str
    documents_ingested: int
    chunks_indexed: int
    experiments_extracted: int


class DocumentSummaryResponse(BaseModel):
    """Stored document summary returned by list endpoints."""

    id: str
    provider: str
    source_id: str
    title: str
    source_path: str | None = None
    source_url: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    ingested_at: str


class DocumentDetailResponse(DocumentSummaryResponse):
    """Stored document detail with content."""

    content: str
    metadata: dict[str, str]
    chunk_count: int


class SearchRequest(BaseModel):
    """Search request for local research documents."""

    query: str
    limit: int = 10


class SearchResultResponse(BaseModel):
    """Normalized search result from vector or keyword search."""

    document_id: str | None
    title: str | None
    provider: str | None
    chunk_id: str | None
    snippet: str
    score: float | None
    source: str


class ChatRequest(BaseModel):
    """Chat request against configured AI provider."""

    message: str
    use_search_context: bool = True
    limit: int = 5


class ChatResponse(BaseModel):
    """Chat response from a configured AI provider."""

    provider: str
    answer: str
    sources: list[SearchResultResponse]


class ExtractRequest(BaseModel):
    """Request body for structured experiment extraction."""

    document_id: str | None = None


class ExtractResponse(BaseModel):
    """Summary of an extraction run."""

    documents_scanned: int
    experiments_extracted: int


class ExperimentResponse(BaseModel):
    """Structured experiment response."""

    id: str
    source_document_id: str
    source_provider: str
    title: str
    experiment_id: str | None = None
    date: str | None = None
    researcher: str | None = None
    cell_line: str | None = None
    organoid_batch: str | None = None
    compounds: list[str]
    treatments: list[str]
    concentrations: list[str]
    time_points: list[str]
    markers: list[str]
    antibodies: list[str]
    imaging_methods: list[str]
    sequencing: list[str]
    notes: str | None = None
    conclusions: str | None = None
    extracted_at: str


def _handle_graph_error(exc: Exception) -> HTTPException:
    """Convert provider-level Graph errors into helpful API responses."""

    if isinstance(exc, MissingGraphTokenError):
        return HTTPException(status_code=401, detail=str(exc))

    if isinstance(exc, GraphRequestError):
        logger.warning("Microsoft Graph read request failed: %s", exc)
        return HTTPException(status_code=502, detail=str(exc))

    logger.exception("Unexpected OneNote listing failure.")
    return HTTPException(status_code=500, detail="Unexpected OneNote listing failure.")


def _search_local_documents(query: str, limit: int) -> list[dict[str, object]]:
    """Run ResearchOS local retrieval with keyword fallback preserved."""

    store = SQLiteStore(settings=settings)
    if settings.ai_provider.lower() in {"", "none"}:
        return store.keyword_search(query, limit=limit)

    vector_results = ChromaVectorIndex(settings=settings).search(query, limit=limit)
    return vector_results or store.keyword_search(query, limit=limit)


def _build_rag_prompt(question: str, sources: list[SearchResultResponse]) -> str:
    """Build a concise RAG prompt from retrieved ResearchOS chunks."""

    if not sources:
        return (
            "Answer the user's research question. No relevant ResearchOS source "
            "chunks were found, so say that clearly and avoid inventing details.\n\n"
            f"Question: {question}"
        )

    source_blocks = []
    for index, source in enumerate(sources, start=1):
        source_blocks.append(
            "\n".join(
                [
                    f"[{index}] Title: {source.title or 'Untitled'}",
                    f"Provider: {source.provider or 'unknown'}",
                    f"Document ID: {source.document_id or 'unknown'}",
                    f"Chunk ID: {source.chunk_id or 'unknown'}",
                    f"Snippet: {source.snippet}",
                ]
            )
        )

    return (
        "Answer the user's research question using only the ResearchOS source "
        "chunks below. Be concise, preserve scientific uncertainty, and cite "
        "sources inline as [1], [2], etc. If the sources are insufficient, say so.\n\n"
        f"Question: {question}\n\n"
        "Sources:\n"
        + "\n\n".join(source_blocks)
    )


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Return a minimal health check for uptime probes and local smoke tests."""

    logger.debug("Health check requested.")
    return HealthResponse(status="ok", project="ResearchOS")


@app.get("/", include_in_schema=False)
def homepage() -> FileResponse:
    """Serve the local ResearchOS web UI."""

    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="ResearchOS frontend is not available.")

    return FileResponse(index_path)


@app.get("/auth/login", tags=["auth"])
def auth_login() -> RedirectResponse:
    """Redirect the user to Microsoft login for delegated Graph consent."""

    try:
        auth_url = build_auth_url(settings)
    except ValueError as exc:
        logger.warning("Microsoft Graph login is not configured: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return RedirectResponse(auth_url)


@app.get("/auth/callback", response_model=AuthStatusResponse, tags=["auth"])
def auth_callback(
    code: str = Query(..., description="Authorization code returned by Microsoft."),
) -> AuthStatusResponse:
    """Handle Microsoft's OAuth callback and store a temporary local token."""

    try:
        token_status = exchange_code_for_token(code=code, settings=settings)
    except ValueError as exc:
        logger.warning("Microsoft Graph token exchange failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return AuthStatusResponse(**token_status.__dict__)


@app.get("/auth/status", response_model=AuthStatusResponse, tags=["auth"])
def auth_status() -> AuthStatusResponse:
    """Return safe delegated Microsoft Graph authentication status."""

    token_status = get_token_status(settings=settings)
    return AuthStatusResponse(**token_status.__dict__)


@app.get("/onenote/notebooks", response_model=list[OneNoteMetadataResponse], tags=["onenote"])
def onenote_notebooks() -> list[OneNoteMetadataResponse]:
    """List OneNote notebooks for the signed-in user."""

    try:
        return [OneNoteMetadataResponse(**item.__dict__) for item in list_notebooks()]
    except (MissingGraphTokenError, GraphRequestError) as exc:
        raise _handle_graph_error(exc) from exc


@app.get("/onenote/sections", response_model=list[OneNoteMetadataResponse], tags=["onenote"])
def onenote_sections(
    notebook_id: str | None = Query(default=None, description="Optional OneNote notebook ID."),
) -> list[OneNoteMetadataResponse]:
    """List OneNote sections, optionally scoped to a notebook."""

    try:
        return [OneNoteMetadataResponse(**item.__dict__) for item in list_sections(notebook_id)]
    except (MissingGraphTokenError, GraphRequestError) as exc:
        raise _handle_graph_error(exc) from exc


@app.get("/onenote/pages", response_model=list[OneNoteMetadataResponse], tags=["onenote"])
def onenote_pages(
    section_id: str | None = Query(default=None, description="Optional OneNote section ID."),
) -> list[OneNoteMetadataResponse]:
    """List OneNote pages, optionally scoped to a section, without fetching content."""

    try:
        return [OneNoteMetadataResponse(**item.__dict__) for item in list_pages(section_id)]
    except (MissingGraphTokenError, GraphRequestError) as exc:
        raise _handle_graph_error(exc) from exc


@app.post("/ingest/markdown", response_model=IngestResponse, tags=["ingestion"])
def ingest_markdown(request: MarkdownIngestRequest) -> IngestResponse:
    """Ingest local Markdown files into SQLite and the vector index."""

    try:
        result = ingest_markdown_folder(request.folder_path)
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return IngestResponse(**result.__dict__)


@app.get("/documents", response_model=list[DocumentSummaryResponse], tags=["documents"])
def documents() -> list[DocumentSummaryResponse]:
    """List locally ingested research documents."""

    store = SQLiteStore(settings=settings)
    return [DocumentSummaryResponse(**document) for document in store.list_documents()]


@app.get("/documents/{document_id}", response_model=DocumentDetailResponse, tags=["documents"])
def document_detail(document_id: str) -> DocumentDetailResponse:
    """Return one locally ingested research document."""

    store = SQLiteStore(settings=settings)
    document = store.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")

    return DocumentDetailResponse(**document)


@app.post("/search", response_model=list[SearchResultResponse], tags=["search"])
def search(request: SearchRequest) -> list[SearchResultResponse]:
    """Search local research documents.

    Vector search is attempted first. SQLite keyword search is always available
    as a no-AI fallback and is used when vector search returns no results.
    """

    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Search query must not be empty.")

    limit = max(1, min(request.limit, 50))
    results = _search_local_documents(request.query, limit=limit)

    return [SearchResultResponse(**result) for result in results]


@app.post("/chat", response_model=ChatResponse, tags=["ai"])
def chat(request: ChatRequest) -> ChatResponse:
    """Answer a question with configured AI provider and ResearchOS source chunks."""

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Chat message must not be empty.")

    try:
        provider = get_ai_provider(settings=settings)
    except AIProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    source_results: list[SearchResultResponse] = []
    if request.use_search_context:
        raw_results = _search_local_documents(request.message, limit=max(1, min(request.limit, 10)))
        source_results = [SearchResultResponse(**result) for result in raw_results]

    prompt = _build_rag_prompt(request.message, source_results)

    try:
        answer = provider.chat(message=prompt)
    except AIProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ChatResponse(provider=provider.provider_name, answer=answer, sources=source_results)


@app.get("/experiments", response_model=list[ExperimentResponse], tags=["experiments"])
def experiments() -> list[ExperimentResponse]:
    """List structured experiments extracted from research documents."""

    store = SQLiteStore(settings=settings)
    return [ExperimentResponse(**experiment) for experiment in store.list_experiments()]


@app.get("/experiments/{experiment_id}", response_model=ExperimentResponse, tags=["experiments"])
def experiment_detail(experiment_id: str) -> ExperimentResponse:
    """Return one structured experiment."""

    store = SQLiteStore(settings=settings)
    experiment = store.get_experiment(experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail=f"Experiment not found: {experiment_id}")

    return ExperimentResponse(**experiment)


@app.post("/extract", response_model=ExtractResponse, tags=["experiments"])
def extract(request: ExtractRequest) -> ExtractResponse:
    """Extract structured experiments from stored research documents."""

    store = SQLiteStore(settings=settings)
    if request.document_id:
        document = store.get_research_document(request.document_id)
        if document is None:
            raise HTTPException(status_code=404, detail=f"Document not found: {request.document_id}")
        documents_to_scan = [document]
    else:
        documents_to_scan = store.get_all_research_documents()

    extracted_count = 0
    for document in documents_to_scan:
        experiment = extract_experiment(document)
        if experiment is not None:
            store.upsert_experiment(experiment)
            extracted_count += 1

    return ExtractResponse(
        documents_scanned=len(documents_to_scan),
        experiments_extracted=extracted_count,
    )
