"""FastAPI entrypoint for the ResearchOS backend."""

import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.agents.manager import create_default_agent_manager
from app.ai_providers import AIProviderError, get_ai_provider
from app.config import get_settings
from app.dashboard_service import DashboardService
from app.entry_drafting import available_entry_templates, draft_entry_from_notes
from app.events.automation_engine import AutomationEngine
from app.events.event_bus import get_event_bus
from app.events.event_models import EventType, ResearchOSEvent
from app.experiment_comparison import compare_experiments
from app.experiment_extraction import extract_experiment
from app.experiment_lifecycle import (
    LIFECYCLE_STAGES,
    lifecycle_definition,
    recommended_actions_for_experiment,
    remaining_stages,
    validate_transition,
)
from app.experiment_planner import plan_follow_up_experiment
from app.experiment_workspace import build_experiment_workspace
from app.graph_auth import build_auth_url, exchange_code_for_token, get_token_status
from app.graph_client import GraphRequestError, MissingGraphTokenError
from app.global_knowledge_graph import KnowledgeGraphService
from app.graphpad_provider import (
    compact_graphpad_statistics_summary,
    graphpad_asset_statistics_summary,
    graphpad_statistics_assets,
    graphpad_status,
    scan_graphpad_assets,
)
from app.ingestion import ingest_documents, ingest_literature, ingest_markdown_folder
from app.knowledge_graph_assistant import answer_with_knowledge_graph
from app.knowledge_graph import build_knowledge_graph_entity, build_knowledge_graph_stats
from app.lab_workspaces import bootstrap_default_workspace, current_workspace, workspace_with_membership
from app.literature_comparison import compare_lab_with_literature
from app.logging import configure_logging
from app.microscopy_provider import microscopy_assets, microscopy_status, scan_microscopy_assets
from app.onenote_provider import list_notebooks, list_pages, list_sections, sync_onenote_pages
from app.permissions import permission_summary
from app.protocol_intelligence import ProtocolService
from app.retinal_ontology import build_retinal_ontology
from app.research_assistant import ask_research_assistant
from app.scientific_reasoning import reason_scientifically
from app.spreadsheet_provider import (
    compact_spreadsheet_summary,
    scan_spreadsheet_assets,
    spreadsheet_assets,
    spreadsheet_status,
    spreadsheet_summary,
)
from app.statistics_engine import interpret_statistics_asset
from app.storage import SQLiteStore
from app.universal_search import UniversalSearchService
from app.users import auth_mode, current_user, normalize_role, user_with_permissions
from app.vector_index import ChromaVectorIndex
from app.workflow_engine import WorkflowEngine, experiment_workflow_id

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
knowledge_graph_service = KnowledgeGraphService(settings=settings)
dashboard_service = DashboardService(settings=settings, knowledge_graph=knowledge_graph_service)
protocol_service = ProtocolService(settings=settings)
universal_search_service = UniversalSearchService(settings=settings, knowledge_graph=knowledge_graph_service)
event_bus = get_event_bus()
automation_engine = AutomationEngine(
    event_bus=event_bus,
    refreshables={
        "knowledge_graph": knowledge_graph_service,
        "search_index": universal_search_service,
        "dashboard": dashboard_service,
    },
)
automation_engine.start()
agent_manager = create_default_agent_manager(
    event_bus=event_bus,
    refreshables={"knowledge_graph": knowledge_graph_service},
)
agent_manager.start()

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


def _publish_event(event_type: EventType, source: str, payload: dict[str, object]) -> None:
    """Publish a ResearchOS event without letting automation break API work."""

    try:
        event_bus.publish(ResearchOSEvent(event_type=event_type, source=source, payload=payload))
    except Exception as exc:
        logger.warning("ResearchOS event publication failed for %s: %s", event_type.value, exc)


def _current_user_payload() -> dict[str, object]:
    """Return current user with auth mode metadata."""

    store = SQLiteStore(settings=settings)
    user = current_user(settings, store)
    workspace = current_workspace(settings, store)
    return {
        **user,
        "auth_mode": auth_mode(settings),
        "auth_enabled": settings.auth_enabled,
        "permission_summary": permission_summary(user),
        "current_workspace": workspace,
    }


def _require_admin() -> dict[str, object]:
    """Return current user or raise if admin access is unavailable."""

    user = _current_user_payload()
    permissions = user.get("permissions") if isinstance(user.get("permissions"), dict) else {}
    if not permissions.get("can_admin"):
        raise HTTPException(status_code=403, detail="Admin role required.")
    return user


class HealthResponse(BaseModel):
    """Response model for the health check endpoint."""

    status: Literal["ok"]
    project: Literal["ResearchOS"]


class AgentStatusResponse(BaseModel):
    """Deterministic scientific agent status."""

    agent_id: str
    name: str
    description: str
    enabled: bool
    event_types: list[str]
    run_count: int
    error_count: int
    last_run: str | None = None
    last_error: str | None = None
    last_event_type: str | None = None
    actions: list[str] = Field(default_factory=list)


class AgentManagerStatusResponse(BaseModel):
    """Agent manager status for Settings UI."""

    started: bool
    agent_count: int
    enabled_count: int
    handled_event_count: int
    agents: list[AgentStatusResponse]
    failures: list[dict[str, object]] = Field(default_factory=list)


class AuthStatusResponse(BaseModel):
    """Safe authentication status response.

    This model intentionally excludes access tokens and refresh tokens.
    """

    authenticated: bool
    expires_at: int | None
    scopes: list[str]
    token_type: str | None


class UserResponse(BaseModel):
    """ResearchOS user response."""

    user_id: str
    email: str
    display_name: str
    role: Literal["admin", "researcher", "viewer"]
    created_at: str | None = None
    last_login: str | None = None
    auth_provider: str
    permissions: dict[str, bool]
    can_view: bool
    can_edit: bool
    can_admin: bool
    permission_summary: dict[str, object] | None = None
    current_workspace: dict[str, object] | None = None
    auth_mode: str | None = None
    auth_enabled: bool | None = None


class BootstrapAdminRequest(BaseModel):
    """Create or update an initial ResearchOS admin user."""

    email: str
    display_name: str
    user_id: str | None = None
    auth_provider: str = "local"


class WorkspaceResponse(BaseModel):
    """Lab workspace response."""

    workspace_id: str
    name: str
    institution: str | None = None
    description: str | None = None
    created_at: str | None = None
    owner_user_id: str | None = None
    settings: dict[str, object] = Field(default_factory=dict)
    current_user_membership: dict[str, object] | None = None
    members: list[dict[str, object]] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


class BootstrapWorkspaceRequest(BaseModel):
    """Create or update the default lab workspace."""

    name: str = "Demo Lab Workspace"
    institution: str = "ResearchOS Local Demo"
    description: str = "Default local development workspace for ResearchOS demos."
    settings: dict[str, object] = Field(default_factory=dict)


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


class PaperIngestResponse(IngestResponse):
    """Summary of a literature ingestion run."""

    message: str


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


class PaperSummaryResponse(BaseModel):
    """Literature paper summary with extracted metadata."""

    id: str
    title: str
    source_path: str | None = None
    ingested_at: str
    authors: str | None = None
    year: str | None = None
    journal: str | None = None
    doi: str | None = None
    abstract: str | None = None
    compounds: list[str]
    markers: list[str]
    genes: list[str]
    cell_types: list[str]
    methods: list[str]


class PaperDetailResponse(PaperSummaryResponse):
    """Detailed literature paper response."""

    content: str
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

    message: str | None = None
    question: str | None = None
    use_search_context: bool = True
    limit: int = 5


class ChatResponse(BaseModel):
    """Chat response from a configured AI provider."""

    provider: str
    answer: str
    sources: list[SearchResultResponse]


class AssistantRequest(BaseModel):
    """Natural-language request for the scientific research assistant."""

    question: str | None = None
    message: str | None = None
    use_ai: bool = True


class AssistantResponse(BaseModel):
    """Structured scientific assistant answer."""

    question: str
    direct_answer: str
    direct_matches: list[dict[str, object]]
    related_context: list[dict[str, object]]
    evidence_from_experiments: list[dict[str, object]]
    source_document_citations: list[dict[str, object]]
    literature_context: list[dict[str, object]]
    extracted_facts: dict[str, list[str]]
    ai_synthesis: str | None
    limitations_uncertainties: list[str]
    sources: list[dict[str, object]]
    ai_used: bool
    provider: str


class ScientificReasoningResponse(BaseModel):
    """Structured scientific reasoning response."""

    question: str
    answer: str
    reasoning: dict[str, object]
    sources: list[dict[str, object]]
    ai_used: bool
    provider: str


class KnowledgeAssistantResponse(BaseModel):
    """Knowledge Graph grounded assistant response."""

    question: str
    direct_answer: str
    knowledge_graph_summary: str
    experiments: list[dict[str, object]]
    notebook_entries: list[dict[str, object]]
    literature: list[dict[str, object]]
    graphpad_statistics: list[dict[str, object]]
    spreadsheets: list[dict[str, object]]
    microscopy_images: list[dict[str, object]]
    related_entities: list[dict[str, object]]
    limitations: list[str]
    sources: list[dict[str, object]]
    entity: str | None = None
    entity_type: str | None = None
    experiment: dict[str, object] | None = None
    ai_synthesis: str | None = None
    ai_used: bool
    provider: str


class ExperimentPlanResponse(BaseModel):
    """Concrete follow-up experiment plan response."""

    question: str
    proposed_experiment_title: str
    hypothesis: str
    rationale: str
    experimental_groups: list[str]
    treatment_schedule: list[str]
    controls: list[str]
    planned_readouts: list[str]
    suggested_markers: list[str]
    statistical_analysis_plan: str
    risks_confounders: list[str]
    expected_outcomes: list[str]
    suggested_onenote_draft_entry: str
    structured: dict[str, object]
    sources: list[dict[str, object]]
    ai_used: bool
    provider: str


class LiteratureComparisonResponse(BaseModel):
    """Structured lab-literature comparison response."""

    question: str
    direct_answer: str
    matching_lab_experiments: list[dict[str, object]]
    matching_literature_sources: list[dict[str, object]]
    relevant_source_documents: list[dict[str, object]]
    similarities: list[str]
    differences: list[str]
    protocol_treatment_differences: list[str]
    limitations: list[str]
    citations: list[dict[str, object]]
    ai_synthesis: str | None
    ai_used: bool
    provider: str


class DraftEntryRequest(BaseModel):
    """Raw dictated notes for generating a structured entry draft."""

    dictation: str | None = None
    notes: str | None = None
    template: str | None = None
    use_ai: bool = True


class EntryTemplateResponse(BaseModel):
    """Available notebook-entry template metadata."""

    id: str
    name: str
    description: str
    sections: list[str]


class DraftEntryResponse(BaseModel):
    """Structured entry draft plus Markdown preview."""

    structured: dict[str, object]
    markdown: str
    template: str
    confidence: float
    missing_fields: list[str]
    ai_used: bool
    provider: str


class ExportMarkdownRequest(BaseModel):
    """Markdown export request for a reviewed draft entry."""

    markdown: str
    filename: str | None = None


class ExportMarkdownResponse(BaseModel):
    """Downloadable Markdown content metadata."""

    filename: str
    content_type: Literal["text/markdown"]
    content: str


class PendingEntrySaveRequest(BaseModel):
    """Local pending notebook-entry save/update request."""

    id: str | None = None
    title: str
    experiment_id: str | None = None
    template: str
    structured: dict[str, object]
    markdown: str
    status: Literal["draft", "ready_for_onenote", "exported"] = "draft"


class PendingEntrySummaryResponse(BaseModel):
    """Saved pending notebook-entry summary."""

    id: str
    title: str
    experiment_id: str | None = None
    template: str
    status: Literal["draft", "ready_for_onenote", "exported"]
    created_at: str
    updated_at: str


class PendingEntryResponse(PendingEntrySummaryResponse):
    """Saved pending notebook-entry detail."""

    structured: dict[str, object]
    markdown: str


SessionStatus = Literal["active", "ended"]
SessionEventType = Literal[
    "voice_note",
    "manual_note",
    "observation",
    "treatment",
    "media_change",
    "image_imported",
    "file_imported",
    "graphpad_imported",
    "spreadsheet_imported",
    "notebook_draft_updated",
]


class SessionStartRequest(BaseModel):
    """Start a live experiment session."""

    experiment_id: str | None = None
    notes: str | None = None


class SessionEndRequest(BaseModel):
    """End a live experiment session."""

    notes: str | None = None


class SessionEventAppendRequest(BaseModel):
    """Append one timeline event to a session."""

    event_type: SessionEventType = "manual_note"
    title: str
    content: str | None = None
    asset_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class SessionEventResponse(BaseModel):
    """One event in an experiment session timeline."""

    event_id: str
    session_id: str
    event_type: SessionEventType
    title: str
    content: str | None = None
    asset_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: str


class SessionResponse(BaseModel):
    """Experiment session workspace response."""

    session_id: str
    experiment_id: str | None = None
    start_time: str
    end_time: str | None = None
    status: SessionStatus
    notes: str | None = None
    voice_transcripts: list[str] = Field(default_factory=list)
    assets: list[dict[str, object]] = Field(default_factory=list)
    timeline: list[SessionEventResponse] = Field(default_factory=list)
    recent_notes: list[SessionEventResponse] = Field(default_factory=list)
    created_at: str
    updated_at: str


AssetType = Literal[
    "notebook",
    "protocol",
    "literature",
    "image",
    "graphpad",
    "spreadsheet",
    "csv",
    "pdf",
    "presentation",
    "sequencing",
    "microscopy",
    "other",
]


class AssetRegisterRequest(BaseModel):
    """Local research asset registration request."""

    asset_id: str | None = None
    asset_type: AssetType = "other"
    experiment_id: str | None = None
    title: str
    filename: str
    provider: str = "local"
    path: str
    metadata: dict[str, object] = Field(default_factory=dict)


class AssetLinkRequest(BaseModel):
    """Request to link or unlink an asset from an experiment."""

    asset_id: str
    experiment_id: str | None = None


class AssetResponse(BaseModel):
    """Registered research asset metadata."""

    asset_id: str
    asset_type: AssetType
    experiment_id: str | None = None
    link_status: Literal["unlinked", "resolved", "unresolved"] = "unlinked"
    linked_experiment: dict[str, object] | None = None
    title: str
    filename: str
    provider: str
    path: str
    created_at: str
    updated_at: str
    metadata: dict[str, object] = Field(default_factory=dict)


class GraphPadFolderStatusResponse(BaseModel):
    """Configured GraphPad scan folder status."""

    path: str
    exists: bool


class GraphPadStatusResponse(BaseModel):
    """GraphPad provider readiness and local asset count."""

    provider: Literal["graphpad"]
    status: str
    folders: list[GraphPadFolderStatusResponse]
    supported_extensions: list[str]
    asset_count: int
    message: str


class GraphPadScanResponse(BaseModel):
    """Summary of a GraphPad provider scan."""

    provider: Literal["graphpad"]
    folders: list[str]
    supported_extensions: list[str]
    files_found: int
    assets_registered: int
    assets_skipped: int
    registered_assets: list[AssetResponse]
    skipped_assets: list[AssetResponse]


class ImageProviderFolderStatusResponse(BaseModel):
    """Configured microscopy/image scan folder status."""

    path: str
    exists: bool


class ImageProviderStatusResponse(BaseModel):
    """Microscopy/image provider readiness and local asset count."""

    provider: Literal["microscopy"]
    status: str
    folders: list[ImageProviderFolderStatusResponse]
    supported_extensions: list[str]
    asset_count: int
    message: str


class ImageProviderScanResponse(BaseModel):
    """Summary of a microscopy/image provider scan."""

    provider: Literal["microscopy"]
    folders: list[str]
    supported_extensions: list[str]
    files_found: int
    assets_registered: int
    assets_skipped: int
    registered_assets: list[AssetResponse]
    skipped_assets: list[AssetResponse]


class SpreadsheetProviderFolderStatusResponse(BaseModel):
    """Configured spreadsheet scan folder status."""

    path: str
    exists: bool


class SpreadsheetProviderStatusResponse(BaseModel):
    """Generic spreadsheet provider readiness and local asset count."""

    provider: Literal["spreadsheet"]
    status: str
    folders: list[SpreadsheetProviderFolderStatusResponse]
    supported_extensions: list[str]
    asset_count: int
    message: str


class SpreadsheetProviderScanResponse(BaseModel):
    """Summary of a generic spreadsheet provider scan."""

    provider: Literal["spreadsheet"]
    folders: list[str]
    supported_extensions: list[str]
    files_found: int
    assets_registered: int
    assets_skipped: int
    registered_assets: list[AssetResponse]
    skipped_assets: list[AssetResponse]


class SpreadsheetSummaryResponse(BaseModel):
    """Parsed generic spreadsheet summary for one asset."""

    asset_id: str
    title: str
    filename: str
    provider: str
    experiment_id: str | None = None
    path: str
    extension: str | None = None
    sheet_names: list[str] = Field(default_factory=list)
    row_count: int = 0
    column_count: int = 0
    detected_tables: list[dict[str, object]] = Field(default_factory=list)
    entities: dict[str, list[str]] = Field(default_factory=dict)
    created_timestamp: str | None = None
    modified_timestamp: str | None = None
    limitations: list[str] = Field(default_factory=list)
    ontology_source: str | None = None


class CompactQuantitativeSummaryResponse(BaseModel):
    """Concise quantitative summary for demo and assistant use."""

    asset_id: str
    title: str | None = None
    experiment_id: str | None = None
    detected_markers_entities: list[str] = Field(default_factory=list)
    detected_treatments_groups: list[str] = Field(default_factory=list)
    key_numeric_measurements: list[dict[str, object]] = Field(default_factory=list)
    per_group_means: dict[str, object] = Field(default_factory=dict)
    n_per_group: dict[str, object] = Field(default_factory=dict)
    p_values: list[object] = Field(default_factory=list)
    short_interpretation: str
    statistical_results: list[dict[str, object]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    source: str


class StatisticsInterpretationResponse(BaseModel):
    """Standardized statistics interpretation for one quantitative asset."""

    asset_id: str
    title: str | None = None
    experiment_id: str | None = None
    provider: str | None = None
    results: list[dict[str, object]] = Field(default_factory=list)
    summary: str
    limitations: list[str] = Field(default_factory=list)


class GraphPadStatisticsSummaryResponse(BaseModel):
    """Parsed GraphPad CSV statistics summary for one asset."""

    asset_id: str
    title: str
    filename: str
    provider: str
    experiment_id: str | None = None
    parsed: bool
    message: str | None = None
    group_names: list[str] = Field(default_factory=list)
    variables: list[str] = Field(default_factory=list)
    sample_sizes: list[float] = Field(default_factory=list)
    means: list[float] = Field(default_factory=list)
    standard_deviations: list[float] = Field(default_factory=list)
    standard_errors: list[float] = Field(default_factory=list)
    p_values: list[float] = Field(default_factory=list)
    statistical_tests: list[str] = Field(default_factory=list)
    comparison_labels: list[str] = Field(default_factory=list)
    rows: list[dict[str, object]] = Field(default_factory=list)
    row_count: int = 0
    limitations: list[str] = Field(default_factory=list)


class ExperimentTimelineEventResponse(BaseModel):
    """One chronological event in an experiment timeline."""

    timestamp: str
    event_type: str
    title: str
    description: str
    source: str
    linked_asset_ids: list[str] = Field(default_factory=list)
    linked_document_ids: list[str] = Field(default_factory=list)


class ExperimentTimelineResponse(BaseModel):
    """Unified timeline for one experiment and its linked research assets."""

    experiment_id: str
    human_experiment_id: str | None = None
    title: str
    events: list[ExperimentTimelineEventResponse]


class ExperimentLifecycleTransitionRequest(BaseModel):
    """Lifecycle transition request."""

    to_stage: str
    reason: str | None = None
    actor: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class ExperimentLifecycleResponse(BaseModel):
    """Experiment lifecycle state, rules, and recommendations."""

    experiment_id: str
    current_stage: str
    allowed_transitions: list[str]
    completion_criteria: list[str]
    recommended_next_actions: list[str]
    remaining_stages: list[str]
    history: list[dict[str, object]] = Field(default_factory=list)
    all_stages: list[str] = Field(default_factory=lambda: list(LIFECYCLE_STAGES))


class WorkflowTransitionRequest(BaseModel):
    """Generic workflow transition request."""

    to_stage: str
    reason: str | None = None
    actor: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class WorkflowNoteRequest(BaseModel):
    """Append a note to the current or specified workflow stage."""

    note: str
    stage: str | None = None
    actor: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class WorkflowResponse(BaseModel):
    """Generic workflow payload."""

    workflow_id: str
    workflow_type: str
    subject_id: str
    subject: dict[str, object] = Field(default_factory=dict)
    current_stage: str
    stage: dict[str, object]
    definition: dict[str, object]
    progress: dict[str, object]
    completed_stages: list[str]
    remaining_stages: list[str]
    suggested_next_actions: list[str]
    recommended_next_actions: list[str]
    blocking_issues: list[str]
    history: list[dict[str, object]] = Field(default_factory=list)
    notes: list[dict[str, object]] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


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
    linked_assets: list[AssetResponse] = Field(default_factory=list)


class ExperimentCompareRequest(BaseModel):
    """Request body for comparing structured experiments."""

    experiment_ids: list[str]
    use_ai: bool = True


class ExperimentCompareResponse(BaseModel):
    """Structured experiment comparison response."""

    experiment_ids: list[str]
    shared_features: dict[str, object]
    differences: dict[str, dict[str, object]]
    likely_scientific_interpretation: str
    limitations: list[str]
    source_experiment_records: list[dict[str, object]]
    ai_used: bool
    provider: str


class DemoResetResponse(IngestResponse):
    """Response returned after resetting and loading local demo notes."""

    documents_deleted: int


class DemoStatusResponse(BaseModel):
    """Pre-demo readiness status for Nathan's PI/lab walkthrough."""

    backend_healthy: bool
    demo_notes_loaded: bool
    demo_note_count: int
    experiments_extracted: bool
    experiment_count: int
    papers_loaded: bool
    paper_count: int
    pending_entry_count: int
    drafts_ready_for_onenote: int
    assistant_available: bool
    onenote_status: dict[str, object]
    ai_provider_status: dict[str, object]


class OntologyEntityResponse(BaseModel):
    """Linked retinal organoid ontology entity."""

    type: str
    name: str
    experiments: list[dict[str, object]]
    documents: list[dict[str, object]]
    protocols: list[dict[str, object]]
    images: list[dict[str, object]]
    ai_summaries: list[dict[str, object]]


class ProviderStatusResponse(BaseModel):
    """Current status of local and external ResearchOS providers."""

    backend: dict[str, object]
    markdown_provider: dict[str, object]
    onenote_auth: dict[str, object]
    onenote_sync: dict[str, object]
    ai_provider: dict[str, object]
    database: dict[str, object]
    vector_index: dict[str, object]
    document_count: int
    experiment_count: int
    pending_entry_count: int
    drafts_ready_for_onenote: int


class DeploymentStatusResponse(BaseModel):
    """Deployment readiness information safe for Settings UI display."""

    host: str
    port: int
    public_base_url: str | None
    public_base_url_configured: bool
    https_enabled: bool
    data_dir: str
    mode: str
    server_url: str
    mobile_pwa_url: str
    microsoft_redirect_uri: str
    warnings: list[str]


class OneNoteReadinessResponse(BaseModel):
    """OneNote auth/sync readiness details safe for Settings UI display."""

    microsoft_client_id_configured: bool
    tenant_configured: bool
    redirect_uri_configured: bool
    current_redirect_uri: str | None
    required_azure_redirect_uri: str
    configured_scopes: list[str]
    required_scopes: list[str]
    missing_required_scopes: list[str]
    current_auth_status: dict[str, object]
    current_deployment_public_url: str | None
    redirect_uri_compatible: bool
    redirect_uri_message: str
    ucsd_approval_status: str
    ucsd_approval_message: str
    read_only_sync_ready: bool
    read_only_sync_message: str
    write_back_disabled: bool
    write_back_message: str


class GraphEntityResponse(BaseModel):
    """Knowledge graph neighborhood for one local ResearchOS entity."""

    type: str
    name: str
    overview: str
    related_experiments: list[dict[str, object]]
    related_papers: list[dict[str, object]]
    related_protocols: list[dict[str, object]]
    related_compounds: list[str]
    related_markers: list[str]
    related_cell_lines: list[str]
    related_batches: list[str]
    related_genes: list[str]
    related_images: list[dict[str, object]] = Field(default_factory=list)
    timeline: list[dict[str, object]]
    ai_summary: str
    source_citations: list[dict[str, object]]
    relationship_counts: dict[str, int]


class GraphStatsResponse(BaseModel):
    """Graph-wide entity and relationship statistics."""

    entity_counts: dict[str, int]
    relationship_counts: dict[str, int]
    node_count: int
    edge_count: int
    nodes: list[dict[str, object]]
    links: list[dict[str, object]]


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


def _chat_question(request: ChatRequest) -> str:
    """Accept both `message` and `question` request shapes for chat."""

    question = request.message or request.question or ""
    return question.strip()


def _assistant_question(request: AssistantRequest) -> str:
    """Accept both `question` and `message` request shapes."""

    question = request.question or request.message or ""
    return question.strip()


def _draft_entry_notes(request: DraftEntryRequest) -> str:
    """Accept both `dictation` and `notes` request shapes."""

    notes = request.dictation or request.notes or ""
    return notes.strip()


def _metadata_terms(value: str | None) -> list[str]:
    """Split comma-separated metadata terms."""

    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _paper_summary(document: dict[str, object]) -> dict[str, object]:
    """Normalize a stored literature document into paper response fields."""

    metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
    assert isinstance(metadata, dict)
    return {
        "id": document["id"],
        "title": document["title"],
        "source_path": document.get("source_path"),
        "ingested_at": document.get("ingested_at", ""),
        "authors": metadata.get("authors") or None,
        "year": metadata.get("year") or None,
        "journal": metadata.get("journal") or None,
        "doi": metadata.get("doi") or None,
        "abstract": metadata.get("abstract") or None,
        "compounds": _metadata_terms(str(metadata.get("compounds") or "")),
        "markers": _metadata_terms(str(metadata.get("markers") or "")),
        "genes": _metadata_terms(str(metadata.get("genes") or "")),
        "cell_types": _metadata_terms(str(metadata.get("cell_types") or "")),
        "methods": _metadata_terms(str(metadata.get("methods") or "")),
    }


def _safe_markdown_filename(title: str | None, fallback: str = "researchos-entry") -> str:
    """Build a conservative Markdown filename for local downloads."""

    raw = (title or fallback).strip() or fallback
    safe = "".join(char.lower() if char.isalnum() else "-" for char in raw)
    safe = "-".join(part for part in safe.split("-") if part)
    return f"{safe or fallback}.md"


def _ontology() -> dict[str, list[dict[str, object]]]:
    """Build the current local retinal organoid ontology."""

    store = SQLiteStore(settings=settings)
    experiments = store.list_experiments()
    documents = [document.__dict__ for document in store.get_all_research_documents()]
    ontology = build_retinal_ontology(experiments=experiments, documents=documents)
    image_assets = [
        _asset_with_link_info(store, asset)
        for asset in microscopy_assets(settings=settings)
    ]
    for entity in ontology.get("markers", []):
        marker = str(entity.get("name") or "")
        entity["images"] = _image_assets_for_marker(image_assets, marker)
    return ontology


def _ai_provider_configured() -> bool:
    """Return whether chat has enough provider settings to attempt a call."""

    provider = settings.ai_provider.lower().strip()
    if provider in {"", "none"}:
        return False
    if not settings.ai_base_url.strip() or not settings.ai_model.strip():
        return False
    if settings.ai_base_url.startswith("https://") and not settings.ai_api_key.strip():
        return False
    return True


def _ontology_entities(entity_type: str) -> list[OntologyEntityResponse]:
    """Return linked ontology entities for a known entity type."""

    entities = _ontology().get(entity_type)
    if entities is None:
        raise HTTPException(status_code=404, detail=f"Unknown ontology entity type: {entity_type}")
    return [OntologyEntityResponse(**entity) for entity in entities]


def _ontology_entity(entity_type: str, entity_name: str) -> OntologyEntityResponse:
    """Return one linked ontology entity by name."""

    entities = _ontology().get(entity_type)
    if entities is None:
        raise HTTPException(status_code=404, detail=f"Unknown ontology entity type: {entity_type}")

    for entity in entities:
        if entity["name"].lower() == entity_name.lower():
            return OntologyEntityResponse(**entity)

    raise HTTPException(status_code=404, detail=f"Ontology entity not found: {entity_name}")


@app.get("/graph/stats", response_model=GraphStatsResponse, tags=["graph"])
def graph_stats() -> GraphStatsResponse:
    """Return local knowledge graph counts and visualization data."""

    store = SQLiteStore(settings=settings)
    return GraphStatsResponse(**build_knowledge_graph_stats(store))


@app.get("/graph/entity/{entity_type}/{entity_name:path}", response_model=GraphEntityResponse, tags=["graph"])
def graph_entity(entity_type: str, entity_name: str) -> GraphEntityResponse:
    """Return a local graph neighborhood for a clickable ResearchOS entity."""

    store = SQLiteStore(settings=settings)
    try:
        entity = build_knowledge_graph_entity(store, entity_type, entity_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return GraphEntityResponse(**entity)


@app.get("/knowledgegraph", tags=["knowledgegraph"])
def global_knowledge_graph() -> dict[str, object]:
    """Return global provider-agnostic knowledge graph statistics."""

    return knowledge_graph_service.summary()


@app.get("/knowledgegraph/search", tags=["knowledgegraph"])
def global_knowledge_graph_search(q: str = Query(..., min_length=1), limit: int = Query(25, ge=1, le=100)) -> list[dict[str, object]]:
    """Search scientific entities with case-insensitive partial matching."""

    return knowledge_graph_service.search(q, limit=limit)


@app.get("/knowledgegraph/type/{entity_type}", tags=["knowledgegraph"])
def global_knowledge_graph_type(entity_type: str) -> list[dict[str, object]]:
    """Return every indexed entity of one entity type."""

    return knowledge_graph_service.entities_by_type(entity_type)


@app.get("/knowledgegraph/entity/{entity:path}", tags=["knowledgegraph"])
def global_knowledge_graph_entity(entity: str) -> dict[str, object]:
    """Return all local objects and co-occurring entities linked to one entity."""

    detail = knowledge_graph_service.entity_detail(entity)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Knowledge graph entity not found: {entity}")
    return detail


@app.get("/knowledgegraph/experiment/{experiment_id:path}", tags=["knowledgegraph"])
def global_knowledge_graph_experiment(experiment_id: str) -> dict[str, object]:
    """Return all graph objects connected to one experiment."""

    neighborhood = knowledge_graph_service.experiment_neighborhood(experiment_id)
    if neighborhood is None:
        raise HTTPException(status_code=404, detail=f"Experiment not found in knowledge graph: {experiment_id}")
    return neighborhood


@app.get("/search/universal", tags=["search"])
def universal_search(q: str = Query(..., min_length=1), limit_per_group: int = Query(8, ge=1, le=25)) -> dict[str, object]:
    """Search all local ResearchOS objects across providers."""

    return universal_search_service.search(q, limit_per_group=limit_per_group)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Return a minimal health check for uptime probes and local smoke tests."""

    logger.debug("Health check requested.")
    return HealthResponse(status="ok", project="ResearchOS")


@app.get("/status/automation", tags=["system"])
def automation_status() -> dict[str, object]:
    """Return event bus and automation engine diagnostics."""

    return {
        "event_bus": {
            "processed_event_count": len(event_bus.history()),
            "recent_events": [event.as_dict() for event in event_bus.history()[-10:]],
        },
        "automation_engine": automation_engine.status(),
    }


@app.get("/agents", response_model=AgentManagerStatusResponse, tags=["agents"])
def agents() -> AgentManagerStatusResponse:
    """Return deterministic scientific agent status."""

    return AgentManagerStatusResponse(**agent_manager.status())


@app.post("/agents/{agent_id}/enable", response_model=AgentManagerStatusResponse, tags=["agents"])
def enable_agent(agent_id: str) -> AgentManagerStatusResponse:
    """Enable one deterministic scientific agent."""

    if not agent_manager.enable_agent(agent_id):
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    return AgentManagerStatusResponse(**agent_manager.status())


@app.post("/agents/{agent_id}/disable", response_model=AgentManagerStatusResponse, tags=["agents"])
def disable_agent(agent_id: str) -> AgentManagerStatusResponse:
    """Disable one deterministic scientific agent."""

    if not agent_manager.disable_agent(agent_id):
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    return AgentManagerStatusResponse(**agent_manager.status())


def _deployment_status() -> dict[str, object]:
    """Return sanitized deployment information for shared-lab-server setup."""

    host = settings.api_host
    port = settings.api_port
    public_base_url = settings.public_base_url.strip().rstrip("/")
    server_url = public_base_url or f"http://{host}:{port}"
    https_enabled = server_url.startswith("https://")
    localhost_only = host in {"127.0.0.1", "localhost"}
    warnings: list[str] = []
    if localhost_only:
        warnings.append("Server is bound to localhost only; phones and other lab devices cannot connect.")
    if not public_base_url:
        warnings.append("PUBLIC_BASE_URL is not configured; mobile/PWA users need a reachable server URL.")
    if not https_enabled:
        warnings.append("HTTPS is not enabled. Use HTTPS for shared lab access and production-like OneNote auth.")
    if settings.microsoft_redirect_uri and public_base_url and not settings.microsoft_redirect_uri.startswith(public_base_url):
        warnings.append("MICROSOFT_REDIRECT_URI does not match PUBLIC_BASE_URL; OneNote auth may fail after deployment.")

    mode = "local_dev" if localhost_only or not public_base_url else "lab_server"
    return {
        "host": host,
        "port": port,
        "public_base_url": public_base_url or None,
        "public_base_url_configured": bool(public_base_url),
        "https_enabled": https_enabled,
        "data_dir": settings.data_dir,
        "mode": mode,
        "server_url": server_url,
        "mobile_pwa_url": server_url,
        "microsoft_redirect_uri": settings.microsoft_redirect_uri,
        "warnings": warnings,
    }


def _normalized_scope_set(scopes: list[str]) -> set[str]:
    """Normalize Graph scopes for case-insensitive readiness comparison."""

    return {scope.strip().lower() for scope in scopes if scope.strip()}


def _expected_onenote_redirect_uri(deployment: dict[str, object]) -> str:
    """Return the Azure redirect URI that should match the current mode."""

    public_base_url = str(deployment.get("public_base_url") or "").strip().rstrip("/")
    if public_base_url:
        return f"{public_base_url}/auth/callback"
    return settings.microsoft_redirect_uri or "http://localhost:8001/auth/callback"


def _redirect_uri_readiness(current_redirect_uri: str, expected_redirect_uri: str, deployment: dict[str, object]) -> tuple[bool, str]:
    """Validate whether the configured callback fits local/dev/server mode."""

    if not current_redirect_uri:
        return False, "MICROSOFT_REDIRECT_URI is not configured."

    parsed_current = urlparse(current_redirect_uri)
    parsed_expected = urlparse(expected_redirect_uri)
    if parsed_current.path.rstrip("/") != "/auth/callback":
        return False, "MICROSOFT_REDIRECT_URI must end with /auth/callback."

    public_base_url = str(deployment.get("public_base_url") or "").strip().rstrip("/")
    if public_base_url:
        if current_redirect_uri.rstrip("/") == expected_redirect_uri.rstrip("/"):
            return True, "Redirect URI matches PUBLIC_BASE_URL for lab-server/PWA mode."
        return (
            False,
            "MICROSOFT_REDIRECT_URI must exactly match the Azure redirect URI for this PUBLIC_BASE_URL.",
        )

    localhost_hosts = {"localhost", "127.0.0.1"}
    if parsed_current.scheme == "http" and parsed_current.hostname in localhost_hosts:
        return True, "Redirect URI is compatible with local development mode."

    if parsed_current.scheme == "https" and parsed_expected.netloc and parsed_current.netloc == parsed_expected.netloc:
        return True, "Redirect URI appears compatible with the configured deployment host."

    return False, "Redirect URI does not look compatible with local development or the configured public URL."


def _onenote_readiness() -> dict[str, object]:
    """Build a safe OneNote readiness report without changing auth state."""

    deployment = _deployment_status()
    token_status = get_token_status(settings=settings)
    configured_scopes = settings.graph_scope_list
    required_scopes = ["User.Read", "Notes.Read", "openid", "profile", "offline_access"]
    configured_scope_set = _normalized_scope_set(configured_scopes)
    missing_required_scopes = [
        scope for scope in required_scopes if scope.lower() not in configured_scope_set
    ]
    expected_redirect_uri = _expected_onenote_redirect_uri(deployment)
    redirect_compatible, redirect_message = _redirect_uri_readiness(
        current_redirect_uri=settings.microsoft_redirect_uri,
        expected_redirect_uri=expected_redirect_uri,
        deployment=deployment,
    )

    client_id_configured = bool(settings.microsoft_client_id.strip())
    tenant_configured = bool(settings.microsoft_tenant_id.strip())
    redirect_uri_configured = bool(settings.microsoft_redirect_uri.strip())
    notes_read_configured = "notes.read" in configured_scope_set

    if token_status.authenticated:
        ucsd_status = "connected"
        ucsd_message = "Microsoft Graph is connected for the current local session."
    elif not client_id_configured:
        ucsd_status = "not_configured"
        ucsd_message = "Register or obtain a Microsoft Entra app before OneNote login."
    elif settings.microsoft_tenant_id.strip().lower() == "common":
        ucsd_status = "prototype_common_tenant"
        ucsd_message = (
            "Tenant is set to common for prototype login. UCSD deployment should use an approved "
            "UCSD tenant app or UCSD-owned registration."
        )
    else:
        ucsd_status = "pending_or_not_connected"
        ucsd_message = (
            "App settings exist, but Graph login is not connected. If UCSD blocks consent, "
            "request tenant approval for delegated read-only Notes.Read access."
        )

    read_only_ready = (
        client_id_configured
        and tenant_configured
        and redirect_uri_configured
        and redirect_compatible
        and notes_read_configured
        and token_status.authenticated
    )
    if read_only_ready:
        read_only_message = "Read-only OneNote sync is ready for this session."
    elif not token_status.authenticated:
        read_only_message = "Read-only sync is not ready until Microsoft Graph login succeeds."
    elif not notes_read_configured:
        read_only_message = "Read-only sync requires the Notes.Read delegated permission."
    elif not redirect_compatible:
        read_only_message = "Read-only sync is blocked by redirect URI mismatch."
    else:
        read_only_message = "Read-only sync needs completed Microsoft app configuration."

    return {
        "microsoft_client_id_configured": client_id_configured,
        "tenant_configured": tenant_configured,
        "redirect_uri_configured": redirect_uri_configured,
        "current_redirect_uri": settings.microsoft_redirect_uri or None,
        "required_azure_redirect_uri": expected_redirect_uri,
        "configured_scopes": configured_scopes,
        "required_scopes": required_scopes,
        "missing_required_scopes": missing_required_scopes,
        "current_auth_status": {
            "authenticated": token_status.authenticated,
            "expires_at": token_status.expires_at,
            "scopes": token_status.scopes,
            "token_type": token_status.token_type,
        },
        "current_deployment_public_url": deployment.get("public_base_url"),
        "redirect_uri_compatible": redirect_compatible,
        "redirect_uri_message": redirect_message,
        "ucsd_approval_status": ucsd_status,
        "ucsd_approval_message": ucsd_message,
        "read_only_sync_ready": read_only_ready,
        "read_only_sync_message": read_only_message,
        "write_back_disabled": True,
        "write_back_message": (
            "OneNote write-back is intentionally disabled. Future create/write support would "
            "need separate UCSD IT approval for Notes.Create or Notes.ReadWrite."
        ),
    }


@app.get("/status/deployment", response_model=DeploymentStatusResponse, tags=["system"])
def deployment_status() -> DeploymentStatusResponse:
    """Return lab-server deployment status without exposing secrets."""

    return DeploymentStatusResponse(**_deployment_status())


@app.get("/status/onenote-readiness", response_model=OneNoteReadinessResponse, tags=["system"])
def onenote_readiness() -> OneNoteReadinessResponse:
    """Return OneNote local/server/PWA readiness without exposing secrets."""

    return OneNoteReadinessResponse(**_onenote_readiness())


@app.get("/status/providers", response_model=ProviderStatusResponse, tags=["system"])
def provider_status() -> ProviderStatusResponse:
    """Return integration and local provider status for the dashboard."""

    token_status = get_token_status(settings=settings)
    documents: list[dict[str, object]] = []
    experiments_list: list[dict[str, object]] = []
    pending_entries_list: list[dict[str, object]] = []
    database_status: dict[str, object]
    try:
        store = SQLiteStore(settings=settings)
        documents = store.list_documents()
        experiments_list = store.list_experiments()
        pending_entries_list = store.list_pending_entries()
        database_status = {
            "status": "active",
            "message": "SQLite local database is active.",
            "path": str(store.path),
        }
    except Exception as exc:
        logger.warning("Provider status database check failed: %s", exc)
        database_status = {
            "status": "error",
            "message": f"SQLite database check failed: {exc}",
        }

    try:
        ChromaVectorIndex(settings=settings)
        vector_status = {
            "status": "active",
            "message": "Local vector index is active.",
        }
    except Exception as exc:
        logger.warning("Provider status vector index check failed: %s", exc)
        vector_status = {
            "status": "error",
            "message": f"Vector index check failed: {exc}",
        }

    if token_status.authenticated:
        onenote_state = "connected"
        onenote_message = "Microsoft Graph is connected for this local session."
        sync_state = "available"
        sync_message = "Read-only OneNote sync can run."
    elif settings.microsoft_client_id.strip():
        onenote_state = "not_connected"
        onenote_message = "Microsoft Graph is configured but not connected. Use /auth/login."
        sync_state = "auth_required"
        sync_message = "Connect Microsoft Graph before syncing OneNote."
    else:
        onenote_state = "pending_ucsd_approval"
        onenote_message = "OneNote integration is pending UCSD IT approval or app registration."
        sync_state = "pending_ucsd_approval"
        sync_message = "UCSD tenant approval is needed before real OneNote sync."

    ai_configured = _ai_provider_configured()

    return ProviderStatusResponse(
        backend={
            "status": "ok",
            "project": "ResearchOS",
            "message": "Backend API is healthy.",
        },
        markdown_provider={
            "status": "active",
            "message": "Local Markdown demo provider is active.",
            "sample_path": str(PROJECT_ROOT / "samples" / "lab_notes"),
        },
        onenote_auth={
            "status": onenote_state,
            "authenticated": token_status.authenticated,
            "expires_at": token_status.expires_at,
            "scopes": token_status.scopes,
            "message": onenote_message,
        },
        onenote_sync={
            "status": sync_state,
            "available": token_status.authenticated,
            "read_only": True,
            "message": sync_message,
        },
        ai_provider={
            "status": "configured" if ai_configured else "not_configured",
            "configured": ai_configured,
            "provider": settings.ai_provider,
            "model": settings.ai_model if ai_configured else None,
            "message": (
                "AI chat provider is configured."
                if ai_configured
                else "AI chat is not configured. Search still works locally."
            ),
        },
        database=database_status,
        vector_index=vector_status,
        document_count=len(documents),
        experiment_count=len(experiments_list),
        pending_entry_count=len(pending_entries_list),
        drafts_ready_for_onenote=sum(
            1 for entry in pending_entries_list if entry.get("status") == "ready_for_onenote"
        ),
    )


@app.get("/api/compounds", response_model=list[OntologyEntityResponse], tags=["ontology"])
@app.get("/compounds", response_model=list[OntologyEntityResponse], include_in_schema=False)
def compounds_api() -> list[OntologyEntityResponse]:
    """Return compound ontology entities as JSON."""

    return _ontology_entities("compounds")


@app.get("/api/compounds/{entity_name:path}", response_model=OntologyEntityResponse, tags=["ontology"])
@app.get("/compounds/{entity_name:path}", response_model=OntologyEntityResponse, include_in_schema=False)
def compound_api(entity_name: str) -> OntologyEntityResponse:
    """Return one compound ontology entity as JSON."""

    return _ontology_entity("compounds", entity_name)


@app.get("/api/markers", response_model=list[OntologyEntityResponse], tags=["ontology"])
@app.get("/markers", response_model=list[OntologyEntityResponse], include_in_schema=False)
def markers_api() -> list[OntologyEntityResponse]:
    """Return marker ontology entities as JSON."""

    return _ontology_entities("markers")


@app.get("/api/markers/{entity_name:path}", response_model=OntologyEntityResponse, tags=["ontology"])
@app.get("/markers/{entity_name:path}", response_model=OntologyEntityResponse, include_in_schema=False)
def marker_api(entity_name: str) -> OntologyEntityResponse:
    """Return one marker ontology entity as JSON."""

    return _ontology_entity("markers", entity_name)


@app.get("/api/cell-lines", response_model=list[OntologyEntityResponse], tags=["ontology"])
@app.get("/cell-lines", response_model=list[OntologyEntityResponse], include_in_schema=False)
def cell_lines_api() -> list[OntologyEntityResponse]:
    """Return cell-line ontology entities as JSON."""

    return _ontology_entities("cell-lines")


@app.get("/api/cell-lines/{entity_name:path}", response_model=OntologyEntityResponse, tags=["ontology"])
@app.get("/cell-lines/{entity_name:path}", response_model=OntologyEntityResponse, include_in_schema=False)
def cell_line_api(entity_name: str) -> OntologyEntityResponse:
    """Return one cell-line ontology entity as JSON."""

    return _ontology_entity("cell-lines", entity_name)


@app.get("/api/organoid-batches", response_model=list[OntologyEntityResponse], tags=["ontology"])
@app.get("/organoid-batches", response_model=list[OntologyEntityResponse], include_in_schema=False)
def organoid_batches_api() -> list[OntologyEntityResponse]:
    """Return organoid-batch ontology entities as JSON."""

    return _ontology_entities("organoid-batches")


@app.get("/api/organoid-batches/{entity_name:path}", response_model=OntologyEntityResponse, tags=["ontology"])
@app.get("/organoid-batches/{entity_name:path}", response_model=OntologyEntityResponse, include_in_schema=False)
def organoid_batch_api(entity_name: str) -> OntologyEntityResponse:
    """Return one organoid-batch ontology entity as JSON."""

    return _ontology_entity("organoid-batches", entity_name)


@app.get("/api/dashboard/daily", tags=["dashboard"])
def daily_dashboard(use_ai: bool = Query(True)) -> dict[str, object]:
    """Return the daily ResearchOS attention dashboard."""

    return dashboard_service.build(use_ai=use_ai)


@app.get("/workflows", response_model=list[WorkflowResponse], tags=["workflows"])
def workflows() -> list[WorkflowResponse]:
    """Return ResearchOS workflows for extracted experiments."""

    store = SQLiteStore(settings=settings)
    return [WorkflowResponse(**workflow) for workflow in WorkflowEngine(store).list_workflows()]


@app.get("/workflows/definitions", tags=["workflows"])
def workflow_definitions() -> dict[str, object]:
    """Return registered workflow definitions and future workflow types."""

    store = SQLiteStore(settings=settings)
    definitions = WorkflowEngine(store).definitions()
    return {
        "definitions": definitions,
        "future_workflow_types": [
            "Experiment",
            "Protocol Development",
            "RNA-seq Analysis",
            "Microscopy Analysis",
            "Manuscript",
            "Grant",
            "Patent",
            "Publication",
        ],
    }


@app.get("/workflows/experiment/{experiment_id}", response_model=WorkflowResponse, tags=["workflows"])
def experiment_workflow(experiment_id: str) -> WorkflowResponse:
    """Return or create the workflow for an extracted experiment."""

    store = SQLiteStore(settings=settings)
    workflow = WorkflowEngine(store).workflow_for_experiment_reference(experiment_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Experiment not found: {experiment_id}")
    return WorkflowResponse(**workflow)


@app.get("/workflows/{workflow_id}", response_model=WorkflowResponse, tags=["workflows"])
def workflow_detail(workflow_id: str) -> WorkflowResponse:
    """Return one generic workflow."""

    store = SQLiteStore(settings=settings)
    workflow = WorkflowEngine(store).get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
    return WorkflowResponse(**workflow)


@app.post("/workflows/{workflow_id}/transition", response_model=WorkflowResponse, tags=["workflows"])
def workflow_transition(workflow_id: str, request: WorkflowTransitionRequest) -> WorkflowResponse:
    """Transition one workflow and publish workflow automation events."""

    store = SQLiteStore(settings=settings)
    try:
        workflow = WorkflowEngine(store).transition(
            workflow_id,
            request.to_stage,
            reason=request.reason,
            actor=request.actor or "ResearchOS",
            metadata=dict(request.metadata),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _publish_event(
        EventType.WORKFLOW_TRANSITIONED,
        "workflow_engine",
        {"workflow_id": workflow_id, "to_stage": workflow.get("current_stage"), "workflow_type": workflow.get("workflow_type")},
    )
    return WorkflowResponse(**workflow)


@app.post("/workflows/{workflow_id}/note", response_model=WorkflowResponse, tags=["workflows"])
def workflow_note(workflow_id: str, request: WorkflowNoteRequest) -> WorkflowResponse:
    """Append a workflow note to the current or specified stage."""

    store = SQLiteStore(settings=settings)
    try:
        workflow = WorkflowEngine(store).add_note(
            workflow_id,
            request.note.strip(),
            actor=request.actor or "ResearchOS",
            stage=request.stage,
            metadata=dict(request.metadata),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _publish_event(
        EventType.WORKFLOW_NOTE_ADDED,
        "workflow_engine",
        {"workflow_id": workflow_id, "stage": workflow.get("current_stage"), "workflow_type": workflow.get("workflow_type")},
    )
    return WorkflowResponse(**workflow)


@app.get("/protocols", tags=["protocols"])
def protocols() -> list[dict[str, object]]:
    """Return detected read-only protocol objects."""

    return protocol_service.list_protocols()


@app.get("/protocols/{protocol_id}/history", tags=["protocols"])
def protocol_history(protocol_id: str) -> list[dict[str, object]]:
    """Return version history for a detected protocol family."""

    history = protocol_service.history(protocol_id)
    if not history:
        raise HTTPException(status_code=404, detail="Protocol not found.")
    return history


@app.get("/protocols/{protocol_id}/compare/{other_id}", tags=["protocols"])
def protocol_compare(protocol_id: str, other_id: str) -> dict[str, object]:
    """Compare two detected protocol versions without editing either source."""

    comparison = protocol_service.compare(protocol_id, other_id)
    if comparison is None:
        raise HTTPException(status_code=404, detail="One or both protocols were not found.")
    return comparison


@app.get("/protocols/{protocol_id}", tags=["protocols"])
def protocol_detail(protocol_id: str) -> dict[str, object]:
    """Return the Protocol Workspace for one detected protocol."""

    protocol = protocol_service.get_protocol(protocol_id)
    if protocol is None:
        raise HTTPException(status_code=404, detail="Protocol not found.")
    return protocol


@app.get("/", include_in_schema=False)
@app.get("/dashboard", include_in_schema=False)
def homepage() -> FileResponse:
    """Serve the local ResearchOS web UI."""

    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="ResearchOS frontend is not available.")

    return FileResponse(index_path)


@app.get("/service-worker.js", include_in_schema=False)
def service_worker() -> FileResponse:
    """Serve the PWA service worker at root scope."""

    worker_path = FRONTEND_DIR / "service-worker.js"
    if not worker_path.exists():
        raise HTTPException(status_code=404, detail="ResearchOS service worker is not available.")
    return FileResponse(worker_path, media_type="application/javascript")


@app.get("/auth/login", tags=["auth"])
def auth_login() -> RedirectResponse:
    """Redirect the user to Microsoft login for delegated Graph consent."""

    try:
        auth_url = build_auth_url(settings)
    except ValueError as exc:
        logger.warning("Microsoft Graph login is not configured: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return RedirectResponse(auth_url)


@app.get("/auth/me", response_model=UserResponse, tags=["auth"])
def auth_me() -> UserResponse:
    """Return the current ResearchOS application user.

    This is separate from Microsoft Graph `/auth/status`. In development mode,
    it returns a local admin user so demos and local workflows remain unblocked.
    """

    return UserResponse(**_current_user_payload())


@app.get("/auth/permissions", tags=["auth"])
def auth_permissions() -> dict[str, object]:
    """Return current user's role-aware permission matrix."""

    user = _current_user_payload()
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "role": user["role"],
        "auth_mode": user["auth_mode"],
        "auth_enabled": user["auth_enabled"],
        **permission_summary(user),
    }


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


@app.get("/users", response_model=list[UserResponse], tags=["users"])
def users() -> list[UserResponse]:
    """Return ResearchOS users."""

    current = _require_admin()
    store = SQLiteStore(settings=settings)
    if not settings.auth_enabled:
        current_user(settings, store)
    return [
        UserResponse(**{**user_with_permissions(user), "auth_mode": current["auth_mode"], "auth_enabled": current["auth_enabled"]})
        for user in store.list_users()
    ]


@app.get("/users/{user_id}", response_model=UserResponse, tags=["users"])
def user_detail(user_id: str) -> UserResponse:
    """Return one ResearchOS user."""

    current = _require_admin()
    store = SQLiteStore(settings=settings)
    user = store.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")
    return UserResponse(**{**user_with_permissions(user), "auth_mode": current["auth_mode"], "auth_enabled": current["auth_enabled"]})


@app.post("/users/bootstrap-admin", response_model=UserResponse, tags=["users"])
def bootstrap_admin(request: BootstrapAdminRequest) -> UserResponse:
    """Create or update an initial admin user for future multi-user setup."""

    current = _require_admin()
    role = normalize_role("admin")
    store = SQLiteStore(settings=settings)
    existing = store.get_user_by_email(request.email.strip())
    user_id = request.user_id or (str(existing["user_id"]) if existing else f"user:{uuid.uuid4().hex}")
    user = store.upsert_user(
        user_id=user_id,
        email=request.email.strip(),
        display_name=request.display_name.strip(),
        role=role,
        auth_provider=request.auth_provider.strip() or "local",
        mark_login=False,
    )
    return UserResponse(**{**user_with_permissions(user), "auth_mode": current["auth_mode"], "auth_enabled": current["auth_enabled"]})


@app.get("/workspaces", response_model=list[WorkspaceResponse], tags=["workspaces"])
def workspaces() -> list[WorkspaceResponse]:
    """Return lab workspaces, bootstrapping the demo workspace in dev mode."""

    current = _require_admin()
    store = SQLiteStore(settings=settings)
    if not settings.auth_enabled:
        bootstrap_default_workspace(settings, store)
    return [
        WorkspaceResponse(**workspace_with_membership(store, workspace, str(current["user_id"])))
        for workspace in store.list_workspaces()
    ]


@app.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse, tags=["workspaces"])
def workspace_detail(workspace_id: str) -> WorkspaceResponse:
    """Return one lab workspace."""

    current = _require_admin()
    store = SQLiteStore(settings=settings)
    workspace = store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_id}")
    return WorkspaceResponse(**workspace_with_membership(store, workspace, str(current["user_id"])))


@app.post("/workspaces/bootstrap-default", response_model=WorkspaceResponse, tags=["workspaces"])
def bootstrap_workspace(request: BootstrapWorkspaceRequest | None = Body(default=None)) -> WorkspaceResponse:
    """Create or update the default local lab workspace."""

    current = _require_admin()
    store = SQLiteStore(settings=settings)
    workspace = bootstrap_default_workspace(settings, store)
    if request is not None:
        workspace = store.upsert_workspace(
            workspace_id=str(workspace["workspace_id"]),
            name=request.name.strip() or "Demo Lab Workspace",
            institution=request.institution.strip() or None,
            description=request.description.strip() or None,
            owner_user_id=str(current["user_id"]),
            settings={**dict(workspace.get("settings") or {}), **dict(request.settings)},
        )
        store.upsert_workspace_membership(str(workspace["workspace_id"]), str(current["user_id"]), "admin")
        workspace = workspace_with_membership(store, workspace, str(current["user_id"]))
    return WorkspaceResponse(**workspace)


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


@app.post("/sync/onenote", response_model=IngestResponse, tags=["onenote"])
def sync_onenote() -> IngestResponse:
    """Read OneNote pages into local ResearchOS storage without writing back."""

    try:
        documents = sync_onenote_pages()
        result = ingest_documents(documents=documents, provider="onenote")
    except MissingGraphTokenError as exc:
        raise HTTPException(
            status_code=401,
            detail=(
                f"{exc} If UCSD blocks consent, request tenant approval for "
                "the ResearchOS Development app."
            ),
        ) from exc
    except GraphRequestError as exc:
        logger.warning("OneNote sync failed during Microsoft Graph read: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=(
                f"OneNote sync could not read Microsoft Graph: {exc}. "
                "Check UCSD tenant consent, OneNote licensing, notebook access, "
                "and Graph delegated Notes.Read approval."
            ),
        ) from exc

    _publish_event(
        EventType.PROVIDER_SYNCED,
        "onenote",
        {
            "provider": "onenote",
            "documents_ingested": result.documents_ingested,
            "chunks_indexed": result.chunks_indexed,
            "experiments_extracted": result.experiments_extracted,
        },
    )
    _publish_event(
        EventType.NOTEBOOK_IMPORTED,
        "onenote",
        {"provider": "onenote", "documents_ingested": result.documents_ingested},
    )
    if result.experiments_extracted:
        _publish_event(
            EventType.EXPERIMENT_EXTRACTED,
            "onenote",
            {"provider": "onenote", "experiments_extracted": result.experiments_extracted},
        )
    return IngestResponse(**result.__dict__)


@app.post("/ingest/markdown", response_model=IngestResponse, tags=["ingestion"])
def ingest_markdown(
    request: MarkdownIngestRequest | None = Body(default=None),
) -> IngestResponse:
    """Ingest local Markdown files into SQLite and the vector index."""

    resolved_request = request or MarkdownIngestRequest()
    try:
        result = ingest_markdown_folder(resolved_request.folder_path)
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _publish_event(
        EventType.NOTEBOOK_IMPORTED,
        "markdown",
        {
            "folder_path": str(resolved_request.folder_path),
            "documents_ingested": result.documents_ingested,
            "chunks_indexed": result.chunks_indexed,
        },
    )
    if result.experiments_extracted:
        _publish_event(
            EventType.EXPERIMENT_EXTRACTED,
            "markdown",
            {"folder_path": str(resolved_request.folder_path), "experiments_extracted": result.experiments_extracted},
        )
    return IngestResponse(**result.__dict__)


@app.post("/ingest/papers", response_model=PaperIngestResponse, tags=["literature"])
def ingest_papers() -> PaperIngestResponse:
    """Ingest local literature files from samples/papers and data/papers."""

    try:
        result = ingest_literature()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    message = (
        f"Ingested {result.documents_ingested} paper document(s)."
        if result.documents_ingested
        else "No paper files found. Add .pdf, .txt, or .md files under samples/papers or data/papers."
    )
    _publish_event(
        EventType.LITERATURE_IMPORTED,
        "literature",
        {"documents_ingested": result.documents_ingested, "chunks_indexed": result.chunks_indexed},
    )
    return PaperIngestResponse(message=message, **result.__dict__)


@app.post("/demo/reset", response_model=DemoResetResponse, tags=["demo"])
def demo_reset() -> DemoResetResponse:
    """Reset local sample data and reload the bundled demo lab notes."""

    sample_path = PROJECT_ROOT / "samples" / "lab_notes"
    store = SQLiteStore(settings=settings)
    deleted_count = store.delete_documents_by_source_prefix(str(sample_path))
    result = ingest_markdown_folder(sample_path)
    _publish_event(
        EventType.NOTEBOOK_IMPORTED,
        "demo",
        {
            "folder_path": str(sample_path),
            "documents_deleted": deleted_count,
            "documents_ingested": result.documents_ingested,
        },
    )
    if result.experiments_extracted:
        _publish_event(
            EventType.EXPERIMENT_EXTRACTED,
            "demo",
            {"folder_path": str(sample_path), "experiments_extracted": result.experiments_extracted},
        )

    return DemoResetResponse(
        documents_deleted=deleted_count,
        provider=result.provider,
        documents_ingested=result.documents_ingested,
        chunks_indexed=result.chunks_indexed,
        experiments_extracted=result.experiments_extracted,
    )


@app.get("/demo/status", response_model=DemoStatusResponse, tags=["demo"])
def demo_status() -> DemoStatusResponse:
    """Return a concise readiness report for the local demo workflow."""

    store = SQLiteStore(settings=settings)
    documents_list = store.list_documents()
    experiments_list = store.list_experiments()
    pending_entries_list = store.list_pending_entries()
    sample_path = str(PROJECT_ROOT / "samples" / "lab_notes")

    demo_note_count = 0
    paper_count = 0
    for document in documents_list:
        provider = str(document.get("provider") or "")
        source_path = str(document.get("source_path") or "")
        if provider == "markdown" and source_path.startswith(sample_path):
            demo_note_count += 1
        if provider == "literature":
            paper_count += 1

    token_status = get_token_status(settings=settings)
    if token_status.authenticated:
        onenote_state = "connected"
        onenote_message = "OneNote is connected for this local session."
    elif settings.microsoft_client_id.strip():
        onenote_state = "not_connected"
        onenote_message = "OneNote app settings exist, but Microsoft Graph login is not connected."
    else:
        onenote_state = "waiting_for_it_approval"
        onenote_message = "OneNote integration is pending UCSD IT approval/app registration."

    ai_configured = _ai_provider_configured()

    return DemoStatusResponse(
        backend_healthy=True,
        demo_notes_loaded=demo_note_count > 0,
        demo_note_count=demo_note_count,
        experiments_extracted=len(experiments_list) > 0,
        experiment_count=len(experiments_list),
        papers_loaded=paper_count > 0,
        paper_count=paper_count,
        pending_entry_count=len(pending_entries_list),
        drafts_ready_for_onenote=sum(
            1 for entry in pending_entries_list if entry.get("status") == "ready_for_onenote"
        ),
        assistant_available=True,
        onenote_status={
            "status": onenote_state,
            "authenticated": token_status.authenticated,
            "read_only": True,
            "message": onenote_message,
        },
        ai_provider_status={
            "status": "configured" if ai_configured else "local_fallback",
            "configured": ai_configured,
            "provider": settings.ai_provider,
            "model": settings.ai_model if ai_configured else None,
            "message": (
                "Configured AI provider can be used for synthesis."
                if ai_configured
                else "Assistant uses local search/structured fallback without an AI key."
            ),
        },
    )


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


@app.get("/papers", response_model=list[PaperSummaryResponse], tags=["literature"])
def papers() -> list[PaperSummaryResponse]:
    """List locally ingested literature papers."""

    store = SQLiteStore(settings=settings)
    paper_summaries = []
    for document in store.list_documents():
        if document["provider"] != "literature":
            continue
        detail = store.get_document(str(document["id"]))
        if detail is not None:
            paper_summaries.append(PaperSummaryResponse(**_paper_summary(detail)))
    return paper_summaries


@app.get("/papers/{paper_id}", response_model=PaperDetailResponse, tags=["literature"])
def paper_detail(paper_id: str) -> PaperDetailResponse:
    """Return one ingested literature paper."""

    store = SQLiteStore(settings=settings)
    document = store.get_document(paper_id)
    if document is None or document["provider"] != "literature":
        raise HTTPException(status_code=404, detail=f"Paper not found: {paper_id}")

    summary = _paper_summary(document)
    return PaperDetailResponse(
        **summary,
        content=str(document["content"]),
        chunk_count=int(document["chunk_count"]),
    )


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

    question = _chat_question(request)
    if not question:
        raise HTTPException(status_code=400, detail="Chat message must not be empty.")

    try:
        provider = get_ai_provider(settings=settings)
    except AIProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    source_results: list[SearchResultResponse] = []
    if request.use_search_context:
        raw_results = _search_local_documents(question, limit=max(1, min(request.limit, 10)))
        source_results = [SearchResultResponse(**result) for result in raw_results]

    prompt = _build_rag_prompt(question, source_results)

    try:
        answer = provider.chat(message=prompt)
    except AIProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ChatResponse(provider=provider.provider_name, answer=answer, sources=source_results)


@app.post("/entries/draft", response_model=DraftEntryResponse, tags=["entries"])
def draft_entry(request: DraftEntryRequest) -> DraftEntryResponse:
    """Generate a structured notebook-entry draft from dictated raw notes."""

    notes = _draft_entry_notes(request)
    if not notes:
        raise HTTPException(status_code=400, detail="Draft entry dictation or notes must not be empty.")

    draft = draft_entry_from_notes(
        raw_notes=notes,
        template=request.template,
        settings=settings,
        use_ai=request.use_ai,
    )
    return DraftEntryResponse(**draft.__dict__)


@app.get("/entry-templates", response_model=list[EntryTemplateResponse], tags=["entries"])
def entry_templates() -> list[EntryTemplateResponse]:
    """Return available reusable lab notebook entry templates."""

    return [EntryTemplateResponse(**template) for template in available_entry_templates()]


@app.post("/entries/save-draft", response_model=PendingEntryResponse, tags=["entries"])
def save_entry_draft(request: PendingEntrySaveRequest) -> PendingEntryResponse:
    """Save or update a generated notebook draft inside local ResearchOS storage."""

    if not request.title.strip():
        raise HTTPException(status_code=400, detail="Saved draft title must not be empty.")
    if not request.markdown.strip():
        raise HTTPException(status_code=400, detail="Saved draft Markdown must not be empty.")

    store = SQLiteStore(settings=settings)
    user = _current_user_payload()
    workspace = user.get("current_workspace") if isinstance(user.get("current_workspace"), dict) else {}
    saved = store.save_pending_entry(
        entry_id=request.id,
        title=request.title.strip(),
        experiment_id=request.experiment_id,
        template=request.template,
        structured=dict(request.structured),
        markdown=request.markdown,
        status=request.status,
        owner_user_id=str(user.get("user_id")),
        created_by=str(user.get("user_id")),
        workspace_id=str(workspace.get("workspace_id") or ""),
    )
    _publish_event(
        EventType.DRAFT_CREATED,
        "entries",
        {"entry_id": saved.get("id"), "experiment_id": saved.get("experiment_id"), "status": saved.get("status")},
    )
    return PendingEntryResponse(**saved)


@app.post("/sessions/start", response_model=SessionResponse, tags=["sessions"])
def start_session(request: SessionStartRequest) -> SessionResponse:
    """Start a live experiment session."""

    store = SQLiteStore(settings=settings)
    user = _current_user_payload()
    workspace = user.get("current_workspace") if isinstance(user.get("current_workspace"), dict) else {}
    session = store.start_session(
        experiment_id=request.experiment_id.strip() if request.experiment_id else None,
        notes=request.notes.strip() if request.notes else None,
        owner_user_id=str(user.get("user_id")),
        created_by=str(user.get("user_id")),
        workspace_id=str(workspace.get("workspace_id") or ""),
    )
    _publish_event(
        EventType.SESSION_STARTED,
        "sessions",
        {"session_id": session.get("session_id"), "experiment_id": session.get("experiment_id")},
    )
    return SessionResponse(**session)


@app.post("/sessions/{session_id}/end", response_model=SessionResponse, tags=["sessions"])
def end_session(session_id: str, request: SessionEndRequest | None = Body(default=None)) -> SessionResponse:
    """End a live experiment session."""

    store = SQLiteStore(settings=settings)
    session = store.end_session(session_id, notes=request.notes.strip() if request and request.notes else None)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    experiment_reference = session.get("experiment_id")
    if experiment_reference:
        experiment = store.find_experiment_by_reference(str(experiment_reference))
        if experiment is not None:
            workflow = WorkflowEngine(store).workflow_for_experiment(experiment)
            if workflow.get("current_stage") == "Running":
                transitioned = WorkflowEngine(store).transition(
                    str(workflow["workflow_id"]),
                    "Waiting",
                    reason="Session completed.",
                    actor="SessionAgent",
                    metadata={"session_id": session_id},
                )
                _publish_event(
                    EventType.WORKFLOW_TRANSITIONED,
                    "sessions",
                    {
                        "session_id": session_id,
                        "experiment_id": experiment.get("id"),
                        "workflow_id": transitioned.get("workflow_id"),
                        "to_stage": transitioned.get("current_stage"),
                    },
                )
    _publish_event(
        EventType.SESSION_ENDED,
        "sessions",
        {"session_id": session.get("session_id"), "experiment_id": session.get("experiment_id")},
    )
    return SessionResponse(**session)


@app.get("/sessions", response_model=list[SessionResponse], tags=["sessions"])
def sessions() -> list[SessionResponse]:
    """List live and completed experiment sessions."""

    store = SQLiteStore(settings=settings)
    return [SessionResponse(**session) for session in store.list_sessions()]


@app.get("/sessions/{session_id}", response_model=SessionResponse, tags=["sessions"])
def session_detail(session_id: str) -> SessionResponse:
    """Return one experiment session workspace."""

    store = SQLiteStore(settings=settings)
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return SessionResponse(**session)


@app.get("/sessions/{session_id}/timeline", response_model=list[SessionEventResponse], tags=["sessions"])
def session_timeline(session_id: str) -> list[SessionEventResponse]:
    """Return one session timeline."""

    store = SQLiteStore(settings=settings)
    if store.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return [SessionEventResponse(**event) for event in store.session_timeline(session_id)]


@app.post("/sessions/{session_id}/events", response_model=SessionEventResponse, tags=["sessions"])
def append_session_event(session_id: str, request: SessionEventAppendRequest) -> SessionEventResponse:
    """Append a note, observation, treatment, media change, image, or file event."""

    if not request.title.strip():
        raise HTTPException(status_code=400, detail="Session event title must not be empty.")
    store = SQLiteStore(settings=settings)
    event = store.append_session_event(
        session_id=session_id,
        event_type=request.event_type,
        title=request.title.strip(),
        content=request.content.strip() if request.content else None,
        asset_id=request.asset_id.strip() if request.asset_id else None,
        metadata=dict(request.metadata),
    )
    if event is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    _publish_event(
        EventType.SESSION_EVENT_APPENDED,
        "sessions",
        {
            "session_id": session_id,
            "event_id": event.get("event_id"),
            "event_type": event.get("event_type"),
            "asset_id": event.get("asset_id"),
        },
    )
    if event.get("event_type") == "image_imported":
        _publish_event(EventType.IMAGE_IMPORTED, "sessions", {"session_id": session_id, "asset_id": event.get("asset_id")})
    elif event.get("event_type") == "file_imported":
        _publish_event(EventType.ASSET_REGISTERED, "sessions", {"session_id": session_id, "asset_id": event.get("asset_id")})
    elif event.get("event_type") == "graphpad_imported":
        _publish_event(EventType.GRAPHPAD_PARSED, "sessions", {"session_id": session_id, "asset_id": event.get("asset_id")})
    elif event.get("event_type") == "spreadsheet_imported":
        _publish_event(EventType.SPREADSHEET_PARSED, "sessions", {"session_id": session_id, "asset_id": event.get("asset_id")})
    elif event.get("event_type") == "notebook_draft_updated":
        _publish_event(EventType.DRAFT_CREATED, "sessions", {"session_id": session_id})
    return SessionEventResponse(**event)


@app.get("/entries", response_model=list[PendingEntrySummaryResponse], tags=["entries"])
def pending_entries() -> list[PendingEntrySummaryResponse]:
    """List locally saved pending notebook-entry drafts."""

    store = SQLiteStore(settings=settings)
    return [PendingEntrySummaryResponse(**entry) for entry in store.list_pending_entries()]


@app.get("/entries/{entry_id}/markdown", response_model=ExportMarkdownResponse, tags=["entries"])
def pending_entry_markdown(entry_id: str) -> ExportMarkdownResponse:
    """Return one pending entry's Markdown for copy/export workflows."""

    store = SQLiteStore(settings=settings)
    entry = store.get_pending_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Pending entry not found: {entry_id}")

    return ExportMarkdownResponse(
        filename=_safe_markdown_filename(str(entry.get("title") or "")),
        content_type="text/markdown",
        content=f"{entry['markdown'].rstrip()}\n",
    )


@app.get("/entries/{entry_id}/download", tags=["entries"])
def download_pending_entry(entry_id: str) -> Response:
    """Download one pending entry as a Markdown file."""

    store = SQLiteStore(settings=settings)
    entry = store.get_pending_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Pending entry not found: {entry_id}")

    filename = _safe_markdown_filename(str(entry.get("title") or ""))
    return Response(
        content=f"{entry['markdown'].rstrip()}\n",
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/entries/{entry_id}", response_model=PendingEntryResponse, tags=["entries"])
def pending_entry_detail(entry_id: str) -> PendingEntryResponse:
    """Return one locally saved pending notebook-entry draft."""

    store = SQLiteStore(settings=settings)
    entry = store.get_pending_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Pending entry not found: {entry_id}")
    return PendingEntryResponse(**entry)


@app.delete("/entries/{entry_id}", tags=["entries"])
def delete_pending_entry(entry_id: str) -> dict[str, object]:
    """Delete one locally saved pending notebook-entry draft."""

    store = SQLiteStore(settings=settings)
    deleted = store.delete_pending_entry(entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Pending entry not found: {entry_id}")
    return {"deleted": True, "id": entry_id}


@app.post("/entries/export-markdown", response_model=ExportMarkdownResponse, tags=["entries"])
def export_markdown(request: ExportMarkdownRequest) -> ExportMarkdownResponse:
    """Return reviewed draft Markdown as local-download content metadata."""

    markdown = request.markdown.strip()
    if not markdown:
        raise HTTPException(status_code=400, detail="Markdown content must not be empty.")

    raw_filename = (request.filename or "researchos-entry.md").strip() or "researchos-entry.md"
    safe_filename = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in raw_filename)
    if not safe_filename.endswith(".md"):
        safe_filename = f"{safe_filename}.md"

    return ExportMarkdownResponse(
        filename=safe_filename,
        content_type="text/markdown",
        content=f"{markdown}\n",
    )


@app.post("/assistant/ask", response_model=AssistantResponse, tags=["ai"])
def assistant_ask(request: AssistantRequest) -> AssistantResponse:
    """Answer a scientific question with retrieved ResearchOS context."""

    question = _assistant_question(request)
    if not question:
        raise HTTPException(status_code=400, detail="Assistant question must not be empty.")

    answer = ask_research_assistant(question=question, settings=settings, use_ai=request.use_ai)
    return AssistantResponse(**answer.__dict__)


@app.post("/assistant/reason", response_model=ScientificReasoningResponse, tags=["ai"])
def assistant_reason(request: AssistantRequest) -> ScientificReasoningResponse:
    """Reason across experiments, statistics, literature, timelines, and assets."""

    question = _assistant_question(request)
    if not question:
        raise HTTPException(status_code=400, detail="Scientific reasoning question must not be empty.")

    answer = reason_scientifically(question=question, settings=settings, use_ai=request.use_ai)
    return ScientificReasoningResponse(**answer.__dict__)


@app.post("/assistant/knowledge", response_model=KnowledgeAssistantResponse, tags=["ai"])
def assistant_knowledge(request: AssistantRequest) -> KnowledgeAssistantResponse:
    """Answer a question using the Global Knowledge Graph as first-class evidence."""

    question = _assistant_question(request)
    if not question:
        raise HTTPException(status_code=400, detail="Knowledge Graph assistant question must not be empty.")

    answer = answer_with_knowledge_graph(question=question, settings=settings, use_ai=request.use_ai)
    return KnowledgeAssistantResponse(**answer.__dict__)


@app.post("/assistant/plan-experiment", response_model=ExperimentPlanResponse, tags=["ai"])
def assistant_plan_experiment(request: AssistantRequest) -> ExperimentPlanResponse:
    """Suggest a concrete follow-up experiment from ResearchOS evidence."""

    question = _assistant_question(request)
    if not question:
        raise HTTPException(status_code=400, detail="Experiment planning question must not be empty.")

    plan = plan_follow_up_experiment(question=question, settings=settings, use_ai=request.use_ai)
    return ExperimentPlanResponse(**plan.__dict__)


@app.post("/assistant/compare-literature", response_model=LiteratureComparisonResponse, tags=["ai"])
def assistant_compare_literature(request: AssistantRequest) -> LiteratureComparisonResponse:
    """Compare local lab experiments against ingested literature."""

    question = _assistant_question(request)
    if not question:
        raise HTTPException(status_code=400, detail="Comparison question must not be empty.")

    answer = compare_lab_with_literature(question=question, settings=settings, use_ai=request.use_ai)
    return LiteratureComparisonResponse(**answer.__dict__)


def _experiment_with_assets(
    store: SQLiteStore,
    experiment: dict[str, object],
) -> dict[str, object]:
    """Attach registered assets to an experiment API record."""

    return experiment | {
        "linked_assets": [
            _asset_with_link_info(store, asset)
            for asset in store.list_assets_for_experiment(experiment)
        ]
    }


def _asset_experiment_summary(experiment: dict[str, object]) -> dict[str, object]:
    """Return compact experiment metadata for asset link displays."""

    return {
        "id": experiment["id"],
        "experiment_id": experiment.get("experiment_id"),
        "title": experiment.get("title"),
        "date": experiment.get("date"),
        "source_provider": experiment.get("source_provider"),
    }


def _asset_with_link_info(
    store: SQLiteStore,
    asset: dict[str, object],
) -> dict[str, object]:
    """Attach resolved/unresolved experiment-link metadata to an asset."""

    experiment_reference = asset.get("experiment_id")
    if not experiment_reference:
        return asset | {"link_status": "unlinked", "linked_experiment": None}

    experiment = store.find_experiment_by_reference(str(experiment_reference))
    if experiment is None:
        return asset | {"link_status": "unresolved", "linked_experiment": None}

    return asset | {
        "link_status": "resolved",
        "linked_experiment": _asset_experiment_summary(experiment),
    }


def _is_microscopy_asset(asset: dict[str, object]) -> bool:
    """Return whether an asset is a microscopy/image record."""

    return str(asset.get("provider") or "") == "microscopy" or str(asset.get("asset_type") or "") in {
        "image",
        "microscopy",
    }


def _asset_markers(asset: dict[str, object]) -> list[str]:
    """Read marker names from image asset metadata."""

    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    raw_markers = metadata.get("markers") if isinstance(metadata, dict) else []
    if isinstance(raw_markers, list):
        return [str(marker) for marker in raw_markers if str(marker).strip()]
    if isinstance(raw_markers, str):
        return [marker.strip() for marker in raw_markers.split(",") if marker.strip()]
    return []


def _image_assets_for_marker(
    assets: list[dict[str, object]],
    marker: str,
) -> list[dict[str, object]]:
    """Return microscopy/image assets whose filename metadata includes a marker."""

    marker_key = marker.lower()
    return [
        asset
        for asset in assets
        if _is_microscopy_asset(asset)
        and any(image_marker.lower() == marker_key for image_marker in _asset_markers(asset))
    ]


def _image_assets_for_experiment_reference(
    store: SQLiteStore,
    experiment_reference: str,
) -> list[dict[str, object]]:
    """Return microscopy assets exactly linked to a human/internal experiment reference."""

    return [
        _asset_with_link_info(store, asset)
        for asset in store.list_assets(experiment_id=experiment_reference)
        if _is_microscopy_asset(asset)
    ]


def _resolve_experiment_reference(store: SQLiteStore, experiment_id: str) -> dict[str, object]:
    """Return an experiment by internal or human reference."""

    experiment = store.find_experiment_by_reference(experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail=f"Experiment not found: {experiment_id}")
    return experiment


def _lifecycle_payload(store: SQLiteStore, experiment: dict[str, object]) -> dict[str, object]:
    """Build lifecycle response payload with rules and deterministic next actions."""

    workflow = WorkflowEngine(store).workflow_for_experiment(experiment)
    return {
        "experiment_id": str(experiment["id"]),
        "current_stage": str(workflow["current_stage"]),
        "allowed_transitions": list(workflow["stage"].get("allowed_transitions", [])),
        "completion_criteria": list(workflow["stage"].get("completion_criteria", [])),
        "recommended_next_actions": list(workflow["recommended_next_actions"]),
        "remaining_stages": list(workflow["remaining_stages"]),
        "history": list(workflow["history"]),
        "all_stages": [stage["name"] for stage in workflow["definition"].get("stages", []) if isinstance(stage, dict)],
    }


def _timeline_timestamp(*values: object) -> str:
    """Return the first useful timestamp as a readable ISO-like value."""

    for value in values:
        normalized = _normalize_timeline_timestamp(value)
        if normalized:
            return normalized
    return "unknown"


def _normalize_timeline_timestamp(value: object) -> str | None:
    """Normalize Unix, SQLite, and date-only timestamps for API output."""

    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.lower() in {"unknown", "none", "null"}:
        return None

    if re.fullmatch(r"\d{10,13}", raw):
        timestamp = int(raw)
        if len(raw) == 13:
            timestamp = timestamp // 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")

    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw, pattern)
        except ValueError:
            continue
        if pattern == "%Y-%m-%d":
            return parsed.date().isoformat()
        return parsed.isoformat(timespec="seconds")

    return raw.replace(" ", "T", 1) if re.match(r"^\d{4}-\d{2}-\d{2} ", raw) else raw


def _timeline_sort_key(event: dict[str, object]) -> str:
    """Sort unknown timestamps last while keeping stable text ordering."""

    timestamp = str(event.get("timestamp") or "")
    if timestamp == "unknown":
        return "9999-99-99 99:99:99"
    return timestamp


def _experiment_timeline(
    store: SQLiteStore,
    experiment: dict[str, object],
) -> dict[str, object]:
    """Build a unified local timeline for one experiment."""

    events: list[dict[str, object]] = []
    experiment_references = _experiment_reference_aliases(experiment)

    events.append(
        {
            "timestamp": _timeline_timestamp(experiment.get("date"), experiment.get("extracted_at")),
            "event_type": "extracted_experiment",
            "title": str(experiment.get("title") or "Extracted experiment"),
            "description": (
                f"Structured experiment extracted from {experiment.get('source_provider') or 'unknown'}."
            ),
            "source": str(experiment.get("source_provider") or "researchos"),
            "linked_asset_ids": [],
            "linked_document_ids": [str(experiment.get("source_document_id"))],
        }
    )

    source_document_id = str(experiment.get("source_document_id") or "")
    if source_document_id:
        document = store.get_document(source_document_id)
        if document is not None:
            provider = str(document.get("provider") or "")
            event_type = "literature_reference" if provider == "literature" else "notebook_entry"
            events.append(
                {
                    "timestamp": _timeline_timestamp(
                        document.get("updated_at"),
                        document.get("created_at"),
                        document.get("ingested_at"),
                    ),
                    "event_type": event_type,
                    "title": str(document.get("title") or "Source document"),
                    "description": str(document.get("source_path") or document.get("source_url") or "Source document indexed in ResearchOS."),
                    "source": provider or "document",
                    "linked_asset_ids": [],
                    "linked_document_ids": [source_document_id],
                }
            )

    for entry in store.list_pending_entries():
        entry_experiment_id = str(entry.get("experiment_id") or "")
        if entry_experiment_id not in experiment_references:
            continue
        events.append(
            {
                "timestamp": _timeline_timestamp(entry.get("updated_at"), entry.get("created_at")),
                "event_type": "pending_entry",
                "title": str(entry.get("title") or "Pending notebook entry"),
                "description": f"Local ResearchOS draft entry with status {entry.get('status') or 'draft'}.",
                "source": "pending_entries",
                "linked_asset_ids": [],
                "linked_document_ids": [],
            }
        )

    for lifecycle_event in store.experiment_lifecycle_history(str(experiment["id"])):
        from_stage = lifecycle_event.get("from_stage")
        to_stage = lifecycle_event.get("to_stage")
        events.append(
            {
                "timestamp": _timeline_timestamp(lifecycle_event.get("created_at")),
                "event_type": "lifecycle_transition",
                "title": f"Lifecycle: {to_stage}",
                "description": (
                    f"Stage changed from {from_stage or 'none'} to {to_stage}."
                    + (f" Reason: {lifecycle_event.get('reason')}" if lifecycle_event.get("reason") else "")
                ),
                "source": str(lifecycle_event.get("actor") or "ResearchOS"),
                "linked_asset_ids": [],
                "linked_document_ids": [],
            }
        )

    workflow_id = experiment_workflow_id(str(experiment["id"]))
    for workflow_event in store.workflow_history(workflow_id):
        from_stage = workflow_event.get("from_stage")
        to_stage = workflow_event.get("to_stage")
        events.append(
            {
                "timestamp": _timeline_timestamp(workflow_event.get("created_at")),
                "event_type": "workflow_transition",
                "title": f"Workflow: {to_stage}",
                "description": (
                    f"Workflow stage changed from {from_stage or 'none'} to {to_stage}."
                    + (f" Reason: {workflow_event.get('reason')}" if workflow_event.get("reason") else "")
                ),
                "source": str(workflow_event.get("actor") or "ResearchOS"),
                "linked_asset_ids": [],
                "linked_document_ids": [],
            }
        )

    for asset in store.list_assets_for_experiment(experiment):
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        assert isinstance(metadata, dict)
        statistics = metadata.get("statistics") if isinstance(metadata.get("statistics"), dict) else None
        asset_type = str(asset.get("asset_type") or "other")
        event_type = _asset_timeline_event_type(asset, statistics is not None)
        description = _asset_timeline_description(asset, statistics)
        events.append(
            {
                "timestamp": _timeline_timestamp(asset.get("updated_at"), asset.get("created_at")),
                "event_type": event_type,
                "title": str(asset.get("title") or asset.get("filename") or "Research asset"),
                "description": description,
                "source": str(asset.get("provider") or asset_type),
                "linked_asset_ids": [str(asset.get("asset_id"))],
                "linked_document_ids": [],
            }
        )

        ai_summary = metadata.get("ai_summary") or metadata.get("ai_synthesis")
        if ai_summary:
            events.append(
                {
                    "timestamp": _timeline_timestamp(asset.get("updated_at"), asset.get("created_at")),
                    "event_type": "ai_summary",
                    "title": f"AI summary for {asset.get('title') or asset.get('filename')}",
                    "description": str(ai_summary),
                    "source": "asset_metadata",
                    "linked_asset_ids": [str(asset.get("asset_id"))],
                    "linked_document_ids": [],
                }
            )

    events.sort(key=_timeline_sort_key)
    return {
        "experiment_id": experiment["id"],
        "human_experiment_id": experiment.get("experiment_id"),
        "title": experiment.get("title") or "Experiment timeline",
        "events": events,
    }


def _virtual_experiment_timeline(
    store: SQLiteStore,
    experiment_reference: str,
) -> dict[str, object]:
    """Build a timeline for a human experiment ID that only has linked assets."""

    events = []
    for asset in store.list_assets(experiment_id=experiment_reference):
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        statistics = metadata.get("statistics") if isinstance(metadata.get("statistics"), dict) else None
        asset_type = str(asset.get("asset_type") or "other")
        events.append(
            {
                "timestamp": _timeline_timestamp(asset.get("updated_at"), asset.get("created_at")),
                "event_type": _asset_timeline_event_type(asset, statistics is not None),
                "title": str(asset.get("title") or asset.get("filename") or "Research asset"),
                "description": _asset_timeline_description(asset, statistics),
                "source": str(asset.get("provider") or asset_type),
                "linked_asset_ids": [str(asset.get("asset_id"))],
                "linked_document_ids": [],
            }
        )

    events.sort(key=_timeline_sort_key)
    return {
        "experiment_id": experiment_reference,
        "human_experiment_id": experiment_reference,
        "title": f"Timeline for {experiment_reference}",
        "events": events,
    }


def _asset_timeline_event_type(asset: dict[str, object], has_statistics: bool) -> str:
    """Map asset metadata to a timeline event type."""

    if has_statistics:
        return "statistics_result"
    asset_type = str(asset.get("asset_type") or "other")
    if asset_type in {"image", "microscopy"}:
        return "image_asset"
    if asset_type == "pdf":
        return "literature_reference" if asset.get("provider") == "literature" else "pdf_asset"
    if asset_type == "literature":
        return "literature_reference"
    if asset_type == "graphpad":
        return "graphpad_analysis"
    return f"{asset_type}_asset"


def _asset_timeline_description(
    asset: dict[str, object],
    statistics: object,
) -> str:
    """Build concise timeline text for a linked asset."""

    if isinstance(statistics, dict):
        variables = ", ".join(str(value) for value in statistics.get("variables", []) if value)
        groups = ", ".join(str(value) for value in statistics.get("group_names", []) if value)
        p_values = ", ".join(str(value) for value in statistics.get("p_values", []) if value is not None)
        tests = ", ".join(str(value) for value in statistics.get("statistical_tests", []) if value)
        parts = []
        if variables:
            parts.append(f"variables {variables}")
        if groups:
            parts.append(f"groups {groups}")
        if p_values:
            parts.append(f"p-values {p_values}")
        if tests:
            parts.append(f"test {tests}")
        return f"Parsed GraphPad CSV statistics: {'; '.join(parts)}." if parts else "Parsed GraphPad CSV statistics."

    if _is_microscopy_asset(asset):
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        markers = ", ".join(_asset_markers(asset))
        timepoint = str(metadata.get("timepoint") or "") if isinstance(metadata, dict) else ""
        details = [
            f"filename {asset.get('filename') or ''}",
            f"provider {asset.get('provider') or 'microscopy'}",
            f"path {asset.get('path') or ''}",
        ]
        if timepoint:
            details.insert(1, f"timepoint {timepoint}")
        if markers:
            details.insert(2 if timepoint else 1, f"markers {markers}")
        return f"Microscopy/image asset: {'; '.join(details)}."

    return (
        f"{asset.get('asset_type') or 'Asset'} file {asset.get('filename') or ''} "
        f"registered from {asset.get('provider') or 'local'}."
    ).strip()


def _experiment_reference_aliases(experiment: dict[str, object]) -> set[str]:
    """Return internal and human experiment references visible in a record."""

    candidates = [
        str(experiment.get("id") or ""),
        str(experiment.get("experiment_id") or ""),
        str(experiment.get("title") or ""),
        str(experiment.get("notes") or ""),
        str(experiment.get("conclusions") or ""),
    ]
    aliases = {value for value in candidates if value and not value.startswith("None")}
    haystack = " ".join(candidates)
    for match in re.finditer(r"(?:^|[^A-Za-z0-9])NK[_-]?Expt[_-]?(\d+)(?=$|[^A-Za-z0-9])", haystack, flags=re.IGNORECASE):
        aliases.add(f"NK_Expt_{match.group(1)}")
    for match in re.finditer(r"(?:^|[^A-Za-z0-9])EXP[_-]?(\d+)(?=$|[^A-Za-z0-9])", haystack, flags=re.IGNORECASE):
        aliases.add(f"EXP_{match.group(1)}")
    return aliases


@app.get("/providers/graphpad/status", response_model=GraphPadStatusResponse, tags=["providers"])
def graphpad_provider_status() -> GraphPadStatusResponse:
    """Return local GraphPad provider configuration and asset count."""

    return GraphPadStatusResponse(**graphpad_status(settings=settings))


@app.post("/providers/graphpad/scan", response_model=GraphPadScanResponse, tags=["providers"])
def graphpad_provider_scan() -> GraphPadScanResponse:
    """Scan configured GraphPad folders and register discovered files as assets."""

    store = SQLiteStore(settings=settings)
    result = scan_graphpad_assets(settings=settings)
    for asset in result.registered_assets:
        _publish_event(EventType.ASSET_REGISTERED, "graphpad", {"asset_id": asset.get("asset_id"), "provider": "graphpad"})
        _publish_event(EventType.GRAPHPAD_PARSED, "graphpad", {"asset_id": asset.get("asset_id"), "filename": asset.get("filename")})
        if isinstance(asset.get("metadata"), dict) and asset["metadata"].get("statistics"):
            _publish_event(EventType.STATISTICS_GENERATED, "graphpad", {"asset_id": asset.get("asset_id")})
    if result.assets_registered or result.assets_skipped:
        _publish_event(
            EventType.PROVIDER_SYNCED,
            "graphpad",
            {"provider": "graphpad", "assets_registered": result.assets_registered, "assets_skipped": result.assets_skipped},
        )
    return GraphPadScanResponse(
        provider=result.provider,
        folders=result.folders,
        supported_extensions=result.supported_extensions,
        files_found=result.files_found,
        assets_registered=result.assets_registered,
        assets_skipped=result.assets_skipped,
        registered_assets=[
            AssetResponse(**_asset_with_link_info(store, asset))
            for asset in result.registered_assets
        ],
        skipped_assets=[
            AssetResponse(**_asset_with_link_info(store, asset))
            for asset in result.skipped_assets
        ],
    )


@app.get(
    "/providers/graphpad/assets/{asset_id}/summary",
    response_model=GraphPadStatisticsSummaryResponse,
    tags=["providers"],
)
def graphpad_asset_summary(asset_id: str) -> GraphPadStatisticsSummaryResponse:
    """Return parsed statistics summary for one GraphPad CSV asset."""

    summary = graphpad_asset_statistics_summary(asset_id=asset_id, settings=settings)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"GraphPad asset not found: {asset_id}")
    return GraphPadStatisticsSummaryResponse(**summary)


@app.get(
    "/statistics/{asset_id}/compact-summary",
    response_model=CompactQuantitativeSummaryResponse,
    tags=["statistics"],
)
def statistics_compact_summary(asset_id: str) -> CompactQuantitativeSummaryResponse:
    """Return a concise quantitative summary for one parsed statistics asset."""

    summary = compact_graphpad_statistics_summary(asset_id=asset_id, settings=settings)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Statistics asset not found: {asset_id}")
    return CompactQuantitativeSummaryResponse(**summary)


@app.get(
    "/statistics/{asset_id}/interpretation",
    response_model=StatisticsInterpretationResponse,
    tags=["statistics"],
)
def statistics_interpretation(asset_id: str) -> StatisticsInterpretationResponse:
    """Return standardized scientific interpretation for one quantitative asset."""

    interpretation = interpret_statistics_asset(asset_id=asset_id, settings=settings)
    if interpretation is None:
        raise HTTPException(status_code=404, detail=f"Statistics asset not found: {asset_id}")
    return StatisticsInterpretationResponse(**interpretation)


@app.get("/statistics", response_model=list[AssetResponse], tags=["statistics"])
def statistics() -> list[AssetResponse]:
    """Return assets containing extracted statistics metadata."""

    store = SQLiteStore(settings=settings)
    return [
        AssetResponse(**_asset_with_link_info(store, asset))
        for asset in graphpad_statistics_assets(settings=settings)
    ]


@app.get("/providers/images/status", response_model=ImageProviderStatusResponse, tags=["providers"])
def images_provider_status() -> ImageProviderStatusResponse:
    """Return microscopy/image provider configuration and asset count."""

    return ImageProviderStatusResponse(**microscopy_status(settings=settings))


@app.post("/providers/images/scan", response_model=ImageProviderScanResponse, tags=["providers"])
def images_provider_scan() -> ImageProviderScanResponse:
    """Scan configured image folders and register discovered files as assets."""

    store = SQLiteStore(settings=settings)
    result = scan_microscopy_assets(settings=settings)
    for asset in result.registered_assets:
        _publish_event(EventType.ASSET_REGISTERED, "microscopy", {"asset_id": asset.get("asset_id"), "provider": "microscopy"})
        _publish_event(EventType.IMAGE_IMPORTED, "microscopy", {"asset_id": asset.get("asset_id"), "filename": asset.get("filename")})
    if result.assets_registered or result.assets_skipped:
        _publish_event(
            EventType.PROVIDER_SYNCED,
            "microscopy",
            {"provider": "microscopy", "assets_registered": result.assets_registered, "assets_skipped": result.assets_skipped},
        )
    return ImageProviderScanResponse(
        provider=result.provider,
        folders=result.folders,
        supported_extensions=result.supported_extensions,
        files_found=result.files_found,
        assets_registered=result.assets_registered,
        assets_skipped=result.assets_skipped,
        registered_assets=[
            AssetResponse(**_asset_with_link_info(store, asset))
            for asset in result.registered_assets
        ],
        skipped_assets=[
            AssetResponse(**_asset_with_link_info(store, asset))
            for asset in result.skipped_assets
        ],
    )


@app.get("/images", response_model=list[AssetResponse], tags=["images"])
def images() -> list[AssetResponse]:
    """Return registered microscopy/image assets."""

    store = SQLiteStore(settings=settings)
    return [
        AssetResponse(**_asset_with_link_info(store, asset))
        for asset in microscopy_assets(settings=settings)
    ]


@app.get("/images/by-marker/{marker}", response_model=list[AssetResponse], tags=["images"])
def images_by_marker(marker: str) -> list[AssetResponse]:
    """Return registered microscopy/image assets that mention a marker."""

    store = SQLiteStore(settings=settings)
    assets = [
        _asset_with_link_info(store, asset)
        for asset in microscopy_assets(settings=settings)
    ]
    return [AssetResponse(**asset) for asset in _image_assets_for_marker(assets, marker)]


@app.get("/providers/spreadsheets/status", response_model=SpreadsheetProviderStatusResponse, tags=["providers"])
def spreadsheets_provider_status() -> SpreadsheetProviderStatusResponse:
    """Return generic spreadsheet provider configuration and asset count."""

    return SpreadsheetProviderStatusResponse(**spreadsheet_status(settings=settings))


@app.post("/providers/spreadsheets/scan", response_model=SpreadsheetProviderScanResponse, tags=["providers"])
def spreadsheets_provider_scan() -> SpreadsheetProviderScanResponse:
    """Scan configured spreadsheet folders and register quantitative assets."""

    store = SQLiteStore(settings=settings)
    result = scan_spreadsheet_assets(settings=settings)
    for asset in result.registered_assets:
        _publish_event(EventType.ASSET_REGISTERED, "spreadsheet", {"asset_id": asset.get("asset_id"), "provider": "spreadsheet"})
        _publish_event(EventType.SPREADSHEET_PARSED, "spreadsheet", {"asset_id": asset.get("asset_id"), "filename": asset.get("filename")})
        if isinstance(asset.get("metadata"), dict) and asset["metadata"].get("statistics"):
            _publish_event(EventType.STATISTICS_GENERATED, "spreadsheet", {"asset_id": asset.get("asset_id")})
    if result.assets_registered or result.assets_skipped:
        _publish_event(
            EventType.PROVIDER_SYNCED,
            "spreadsheet",
            {"provider": "spreadsheet", "assets_registered": result.assets_registered, "assets_skipped": result.assets_skipped},
        )
    return SpreadsheetProviderScanResponse(
        provider=result.provider,
        folders=result.folders,
        supported_extensions=result.supported_extensions,
        files_found=result.files_found,
        assets_registered=result.assets_registered,
        assets_skipped=result.assets_skipped,
        registered_assets=[
            AssetResponse(**_asset_with_link_info(store, asset))
            for asset in result.registered_assets
        ],
        skipped_assets=[
            AssetResponse(**_asset_with_link_info(store, asset))
            for asset in result.skipped_assets
        ],
    )


@app.get("/spreadsheets", response_model=list[AssetResponse], tags=["spreadsheets"])
def spreadsheets() -> list[AssetResponse]:
    """Return registered generic spreadsheet assets."""

    store = SQLiteStore(settings=settings)
    return [
        AssetResponse(**_asset_with_link_info(store, asset))
        for asset in spreadsheet_assets(settings=settings)
    ]


@app.get("/spreadsheets/{asset_id}/summary", response_model=SpreadsheetSummaryResponse, tags=["spreadsheets"])
def spreadsheet_asset_summary(asset_id: str) -> SpreadsheetSummaryResponse:
    """Return parsed generic spreadsheet metadata and summaries."""

    summary = spreadsheet_summary(asset_id=asset_id, settings=settings)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Spreadsheet asset not found: {asset_id}")
    return SpreadsheetSummaryResponse(**summary)


@app.get("/spreadsheets/{asset_id}/compact-summary", response_model=CompactQuantitativeSummaryResponse, tags=["spreadsheets"])
def spreadsheet_asset_compact_summary(asset_id: str) -> CompactQuantitativeSummaryResponse:
    """Return a concise quantitative summary for one spreadsheet asset."""

    summary = compact_spreadsheet_summary(asset_id=asset_id, settings=settings)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Spreadsheet asset not found: {asset_id}")
    return CompactQuantitativeSummaryResponse(**summary)


@app.get("/spreadsheets/{asset_id}/download", tags=["spreadsheets"])
def download_spreadsheet_asset(asset_id: str) -> FileResponse:
    """Download one registered local spreadsheet file."""

    store = SQLiteStore(settings=settings)
    asset = store.get_asset(asset_id)
    if asset is None or asset.get("provider") != "spreadsheet":
        raise HTTPException(status_code=404, detail=f"Spreadsheet asset not found: {asset_id}")
    path = Path(str(asset.get("path") or ""))
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Spreadsheet file not found on disk: {asset_id}")
    return FileResponse(path=path, filename=str(asset.get("filename") or path.name))


@app.get("/spreadsheets/{asset_id}", response_model=AssetResponse, tags=["spreadsheets"])
def spreadsheet_asset_detail(asset_id: str) -> AssetResponse:
    """Return one registered spreadsheet asset."""

    store = SQLiteStore(settings=settings)
    asset = store.get_asset(asset_id)
    if asset is None or asset.get("provider") != "spreadsheet":
        raise HTTPException(status_code=404, detail=f"Spreadsheet asset not found: {asset_id}")
    return AssetResponse(**_asset_with_link_info(store, asset))


@app.get("/assets", response_model=list[AssetResponse], tags=["assets"])
def assets(
    asset_type: AssetType | None = Query(default=None),
    query: str | None = Query(default=None),
) -> list[AssetResponse]:
    """List registered research assets with optional type/search filters."""

    store = SQLiteStore(settings=settings)
    return [
        AssetResponse(**_asset_with_link_info(store, asset))
        for asset in store.list_assets(asset_type=asset_type, query=query)
    ]


@app.post("/assets/register", response_model=AssetResponse, tags=["assets"])
def register_asset(request: AssetRegisterRequest) -> AssetResponse:
    """Register a local research asset without parsing provider-specific content."""

    store = SQLiteStore(settings=settings)
    user = _current_user_payload()
    workspace = user.get("current_workspace") if isinstance(user.get("current_workspace"), dict) else {}
    asset = store.register_asset(
        asset_id=request.asset_id,
        asset_type=request.asset_type,
        experiment_id=request.experiment_id,
        title=request.title.strip(),
        filename=request.filename.strip(),
        provider=request.provider.strip() or "local",
        path=request.path.strip(),
        metadata=request.metadata,
        owner_user_id=str(user.get("user_id")),
        created_by=str(user.get("user_id")),
        workspace_id=str(workspace.get("workspace_id") or ""),
    )
    _publish_event(
        EventType.ASSET_REGISTERED,
        request.provider.strip() or "local",
        {"asset_id": asset.get("asset_id"), "asset_type": asset.get("asset_type"), "experiment_id": asset.get("experiment_id")},
    )
    return AssetResponse(**_asset_with_link_info(store, asset))


@app.post("/assets/link", response_model=AssetResponse, tags=["assets"])
def link_asset(request: AssetLinkRequest) -> AssetResponse:
    """Link a registered asset to an experiment, or unlink it with null."""

    store = SQLiteStore(settings=settings)
    asset = store.link_asset(request.asset_id, request.experiment_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Asset not found: {request.asset_id}")
    _publish_event(
        EventType.ASSET_LINKED,
        str(asset.get("provider") or "local"),
        {"asset_id": asset.get("asset_id"), "experiment_id": request.experiment_id},
    )
    return AssetResponse(**_asset_with_link_info(store, asset))


@app.get("/assets/{asset_id}/links", tags=["assets"])
def asset_links(asset_id: str) -> dict[str, object]:
    """Return link resolution details for one registered asset."""

    store = SQLiteStore(settings=settings)
    asset = store.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")
    enriched = _asset_with_link_info(store, asset)
    return {
        "asset_id": enriched["asset_id"],
        "experiment_id": enriched.get("experiment_id"),
        "link_status": enriched["link_status"],
        "linked_experiment": enriched.get("linked_experiment"),
    }


@app.get("/assets/{asset_id}", response_model=AssetResponse, tags=["assets"])
def asset_detail(asset_id: str) -> AssetResponse:
    """Return one registered research asset."""

    store = SQLiteStore(settings=settings)
    asset = store.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")
    return AssetResponse(**_asset_with_link_info(store, asset))


@app.delete("/assets/{asset_id}", tags=["assets"])
def delete_asset(asset_id: str) -> dict[str, object]:
    """Delete a local asset registration without deleting the underlying file."""

    store = SQLiteStore(settings=settings)
    deleted = store.delete_asset(asset_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")
    return {"deleted": True, "asset_id": asset_id}


@app.get("/experiments", response_model=list[ExperimentResponse], tags=["experiments"])
def experiments() -> list[ExperimentResponse]:
    """List structured experiments extracted from research documents."""

    store = SQLiteStore(settings=settings)
    return [
        ExperimentResponse(**_experiment_with_assets(store, experiment))
        for experiment in store.list_experiments()
    ]


@app.post("/experiments/compare", response_model=ExperimentCompareResponse, tags=["experiments"])
def experiment_compare(request: ExperimentCompareRequest) -> ExperimentCompareResponse:
    """Compare selected experiments using structured extracted fields."""

    requested_ids = [experiment_id.strip() for experiment_id in request.experiment_ids if experiment_id.strip()]
    if len(requested_ids) < 2:
        raise HTTPException(status_code=400, detail="Select at least two experiments to compare.")
    if len(set(requested_ids)) != len(requested_ids):
        raise HTTPException(status_code=400, detail="Experiment IDs must be unique.")

    store = SQLiteStore(settings=settings)
    selected_experiments = []
    missing_ids = []
    for experiment_id in requested_ids:
        experiment = store.get_experiment(experiment_id)
        if experiment is None:
            missing_ids.append(experiment_id)
        else:
            selected_experiments.append(_experiment_with_assets(store, experiment))

    if missing_ids:
        raise HTTPException(status_code=404, detail=f"Experiment not found: {', '.join(missing_ids)}")

    comparison = compare_experiments(
        selected_experiments,
        settings=settings,
        use_ai=request.use_ai,
    )
    return ExperimentCompareResponse(**comparison.__dict__)


@app.get(
    "/experiments/{experiment_id}/timeline",
    response_model=ExperimentTimelineResponse,
    tags=["experiments"],
)
def experiment_timeline(experiment_id: str) -> ExperimentTimelineResponse:
    """Return a unified chronological timeline for one experiment."""

    store = SQLiteStore(settings=settings)
    experiment = store.find_experiment_by_reference(experiment_id)
    if experiment is None:
        assets = store.list_assets(experiment_id=experiment_id)
        if not assets:
            raise HTTPException(status_code=404, detail=f"Experiment not found: {experiment_id}")
        return ExperimentTimelineResponse(**_virtual_experiment_timeline(store, experiment_id))
    return ExperimentTimelineResponse(**_experiment_timeline(store, experiment))


@app.get("/experiments/{experiment_id}/workspace", tags=["experiments"])
def experiment_workspace(experiment_id: str, use_ai: bool = Query(True)) -> dict[str, object]:
    """Return the unified workspace for one experiment."""

    store = SQLiteStore(settings=settings)
    experiment = store.find_experiment_by_reference(experiment_id)
    if experiment is None:
        linked_assets = store.list_assets(experiment_id=experiment_id)
        if not linked_assets:
            raise HTTPException(status_code=404, detail=f"Experiment not found: {experiment_id}")
        timeline = _virtual_experiment_timeline(store, experiment_id)
    else:
        timeline = _experiment_timeline(store, experiment)

    workspace = build_experiment_workspace(
        experiment_id=experiment_id,
        timeline=timeline,
        settings=settings,
        use_ai=use_ai,
        knowledge_graph=knowledge_graph_service,
    )
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Experiment workspace not found: {experiment_id}")
    return workspace


@app.get("/experiments/{experiment_id}/lifecycle", response_model=ExperimentLifecycleResponse, tags=["experiments"])
def experiment_lifecycle(experiment_id: str) -> ExperimentLifecycleResponse:
    """Return lifecycle state, rules, and recommended next actions."""

    store = SQLiteStore(settings=settings)
    experiment = _resolve_experiment_reference(store, experiment_id)
    return ExperimentLifecycleResponse(**_lifecycle_payload(store, experiment))


@app.post("/experiments/{experiment_id}/transition", response_model=ExperimentLifecycleResponse, tags=["experiments"])
def transition_experiment_lifecycle(
    experiment_id: str,
    request: ExperimentLifecycleTransitionRequest,
) -> ExperimentLifecycleResponse:
    """Transition an experiment workflow through the legacy lifecycle API."""

    store = SQLiteStore(settings=settings)
    experiment = _resolve_experiment_reference(store, experiment_id)
    try:
        workflow = WorkflowEngine(store).workflow_for_experiment(experiment)
        transitioned = WorkflowEngine(store).transition(
            str(workflow["workflow_id"]),
            request.to_stage,
            reason=request.reason,
            actor=request.actor or "ResearchOS",
            metadata=dict(request.metadata),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _publish_event(
        EventType.WORKFLOW_TRANSITIONED,
        "experiment_lifecycle",
        {"experiment_id": experiment.get("id"), "workflow_id": transitioned.get("workflow_id"), "to_stage": transitioned.get("current_stage")},
    )
    return ExperimentLifecycleResponse(**_lifecycle_payload(store, experiment))


@app.get("/experiments/{experiment_id}/images", response_model=list[AssetResponse], tags=["experiments"])
def experiment_images(experiment_id: str) -> list[AssetResponse]:
    """Return microscopy/image assets linked to an extracted or human experiment ID."""

    store = SQLiteStore(settings=settings)
    experiment = store.find_experiment_by_reference(experiment_id)
    if experiment is None:
        assets = _image_assets_for_experiment_reference(store, experiment_id)
    else:
        assets = [
            _asset_with_link_info(store, asset)
            for asset in store.list_assets_for_experiment(experiment)
            if _is_microscopy_asset(asset)
        ]
    return [AssetResponse(**asset) for asset in assets]


@app.get("/experiments/{experiment_id}", response_model=ExperimentResponse, tags=["experiments"])
def experiment_detail(experiment_id: str) -> ExperimentResponse:
    """Return one structured experiment."""

    store = SQLiteStore(settings=settings)
    experiment = store.get_experiment(experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail=f"Experiment not found: {experiment_id}")

    return ExperimentResponse(**_experiment_with_assets(store, experiment))


@app.get("/ontology", tags=["ontology"])
def ontology() -> dict[str, list[OntologyEntityResponse]]:
    """Return all linked retinal organoid ontology entities."""

    return {
        entity_type: [OntologyEntityResponse(**entity) for entity in entities]
        for entity_type, entities in _ontology().items()
    }


@app.get("/ontology/{entity_type}", response_model=list[OntologyEntityResponse], tags=["ontology"])
def ontology_entities(entity_type: str) -> list[OntologyEntityResponse]:
    """Return ontology entities for one entity type."""

    return _ontology_entities(entity_type)


@app.get(
    "/ontology/{entity_type}/{entity_name:path}",
    response_model=OntologyEntityResponse,
    tags=["ontology"],
)
def ontology_entity(entity_type: str, entity_name: str) -> OntologyEntityResponse:
    """Return one linked ontology entity."""

    return _ontology_entity(entity_type, entity_name)


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

    if extracted_count:
        _publish_event(
            EventType.EXPERIMENT_EXTRACTED,
            "experiment_extraction",
            {
                "document_id": request.document_id,
                "documents_scanned": len(documents_to_scan),
                "experiments_extracted": extracted_count,
            },
        )
    return ExtractResponse(
        documents_scanned=len(documents_to_scan),
        experiments_extracted=extracted_count,
    )
