"""FastAPI entrypoint for the ResearchOS backend."""

import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.agents.manager import create_default_agent_manager
from app.ai_providers import AIProviderError, get_ai_provider
from app.authorization import AuthorizationService
from app.config import get_settings
from app.dashboard_service import DashboardService
from app.entry_drafting import available_entry_templates, draft_entry_from_notes
from app.evidence_engine import EvidenceEngine
from app.events.automation_engine import AutomationEngine
from app.events.event_bus import get_event_bus
from app.events.event_models import EventType, ResearchOSEvent
from app.experiment_comparison import compare_experiments
from app.experiment_design_copilot import ExperimentCopilotError, ExperimentDesignCopilot
from app.experiment_design_planner import (
    BUILTIN_EXPERIMENT_DESIGN_TEMPLATES,
    DESIGN_STATUSES,
    DEFAULT_DESIGN_IMPORT_TEMPLATES,
    EVENT_TYPES,
    all_reminders,
    build_design_timeline,
    check_design_balance,
    copilot_design_checks,
    design_calendar,
    design_to_csv,
    design_to_ics,
    due_events,
    full_factorial,
    import_design_rows,
    parse_design_csv,
    preview_design_import,
    reminders_to_ics,
    truthy_design_value,
)
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
from app.experiment_wizard import ExperimentWizardPayload, ExperimentWizardService
from app.extensions import create_default_extension_manager
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
from app.general_experiments import (
    ExperimentAuthorizationError,
    ExperimentConflictError,
    ExperimentValidationError,
    GeneralExperimentService,
    SamplePlanningService,
)
from app.ingestion import ingest_documents, ingest_literature, ingest_markdown_folder
from app.inventory import (
    DEFAULT_PURCHASE_IMPORT_TEMPLATES,
    INVENTORY_CSV_FIELDS,
    ORACLE_PURCHASING_PROVIDER,
    PURCHASE_CSV_FIELDS,
    PURCHASE_REQUEST_CSV_FIELDS,
    PURCHASE_REQUEST_STATUSES,
    RECEIVING_CSV_FIELDS,
    apply_purchase_mapping,
    build_reagent_methods_text,
    inventory_item_status,
    inventory_label_data,
    inventory_status_summary,
    methods_citation,
    normalize_purchase_csv_row,
    parse_csv_text,
    purchase_summary,
    purchase_import_preview,
    reagent_methods_entry,
    records_to_csv,
)
from app.lab_chat import ChatAuthorizationError, ChatValidationError, LabChatService
from app.knowledge_graph_assistant import answer_with_knowledge_graph
from app.knowledge_graph import build_knowledge_graph_entity, build_knowledge_graph_stats
from app.lab_workspaces import ActiveWorkspaceService, bootstrap_default_workspace, current_workspace, workspace_with_membership
from app.lab_intelligence import LaboratoryIntelligenceService
from app.literature_comparison import compare_lab_with_literature
from app.logging import configure_logging
from app.microscopy_provider import microscopy_assets, microscopy_status, scan_microscopy_assets
from app.onenote_provider import list_notebooks, list_pages, list_sections, sync_onenote_pages
from app.overnight_intelligence import OvernightIntelligenceService
from app.permissions import permission_summary
from app.plate_layout_planner import generate_plate_layout, plate_layout_to_csv
from app.protocol_hub import ProtocolHubService, ProtocolHubValidationError
from app.protocol_intelligence import ProtocolService
from app.quantification_workspace import QuantificationWorkspaceService
from app.research_objects import ResearchObjectService
from app.retinal_ontology import build_retinal_ontology
from app.research_assistant import ask_research_assistant
from app.resources import RESOURCE_TYPES, normalize_resource_type
from app.scientific_reasoning import reason_scientifically
from app.scientific_memory import ScientificMemoryService
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
from app.visual_experiment_builder import compile_visual_builder
from app.voice_assistant import draft_voice_command, session_event_from_voice_command, supported_speech_providers, voice_markdown_entry
from app.workflow_engine import WorkflowEngine, experiment_workflow_id

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
knowledge_graph_service = KnowledgeGraphService(settings=settings)
dashboard_service = DashboardService(settings=settings, knowledge_graph=knowledge_graph_service)
lab_intelligence_service = LaboratoryIntelligenceService(settings=settings, knowledge_graph=knowledge_graph_service)
overnight_intelligence_service = OvernightIntelligenceService(settings=settings, knowledge_graph=knowledge_graph_service)
protocol_service = ProtocolService(settings=settings)
quantification_workspace_service = QuantificationWorkspaceService(settings=settings, knowledge_graph=knowledge_graph_service)
universal_search_service = UniversalSearchService(settings=settings, knowledge_graph=knowledge_graph_service)
event_bus = get_event_bus()
automation_engine = AutomationEngine(
    event_bus=event_bus,
    refreshables={
        "knowledge_graph": knowledge_graph_service,
        "search_index": universal_search_service,
        "dashboard": dashboard_service,
        "lab_intelligence": lab_intelligence_service,
        "overnight_intelligence": overnight_intelligence_service,
        "quantification_workspace": quantification_workspace_service,
    },
)
automation_engine.start()
agent_manager = create_default_agent_manager(
    event_bus=event_bus,
    refreshables={"knowledge_graph": knowledge_graph_service},
)
agent_manager.start()
extension_manager = create_default_extension_manager()

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


def _current_workspace_id(requested_workspace_id: str | None = None) -> str | None:
    """Resolve requested workspace scope or the active/default workspace."""

    if requested_workspace_id:
        return requested_workspace_id
    store = SQLiteStore(settings=settings)
    workspace = ActiveWorkspaceService(settings, store).get_current_workspace()
    workspace_id = workspace.get("workspace_id")
    return str(workspace_id) if workspace_id else None


def _record_matches_workspace(record: dict[str, object], workspace_id: str | None) -> bool:
    """Keep matching and legacy unscoped rows during workspace scaffolding."""

    if not workspace_id:
        return True
    record_workspace_id = record.get("workspace_id")
    return record_workspace_id in (None, "", workspace_id)


def _require_admin() -> dict[str, object]:
    """Return current user or raise if admin access is unavailable."""

    user = _current_user_payload()
    permissions = user.get("permissions") if isinstance(user.get("permissions"), dict) else {}
    if not permissions.get("can_admin"):
        raise HTTPException(status_code=403, detail="Admin role required.")
    return user


def _authorization_service() -> AuthorizationService:
    return AuthorizationService(settings=settings)


def _chat_service() -> LabChatService:
    return LabChatService(settings=settings)


def _general_experiment_service() -> GeneralExperimentService:
    return GeneralExperimentService(settings=settings)


def _protocol_hub_service() -> ProtocolHubService:
    return ProtocolHubService(settings=settings)


def _research_object_service() -> ResearchObjectService:
    return ResearchObjectService(settings=settings)


def _experiment_design_copilot() -> ExperimentDesignCopilot:
    return ExperimentDesignCopilot(settings=settings)


def _request_user_id(request: Request) -> str:
    """Resolve the current demo/dev user from server-side context.

    Production auth is still future work; this development-only header lets
    tests and demos exercise backend authorization without query parameters.
    """

    return _authorization_service().current_user_id(dict(request.headers))


class HealthResponse(BaseModel):
    """Response model for the health check endpoint."""

    status: Literal["ok"]
    project: Literal["ResearchOS"]


class ShareNotebookRequest(BaseModel):
    principal_type: Literal["user", "group", "role"]
    principal_id: str
    access_level: Literal["view", "comment", "edit", "manage"]
    expires_at: str | None = None


class UpdateNotebookPermissionRequest(BaseModel):
    access_level: Literal["view", "comment", "edit", "manage"]


class CreateGroupRequest(BaseModel):
    lab_id: str = "lab:demo"
    name: str
    description: str | None = None


class AddGroupMemberRequest(BaseModel):
    user_id: str


class CreateConversationRequest(BaseModel):
    lab_id: str = "lab:demo"
    conversation_type: Literal["lab_channel", "project_channel", "group_chat", "direct_message"]
    name: str
    description: str | None = None
    project_id: str | None = None
    member_user_ids: list[str] = Field(default_factory=list)
    membership_policy: Literal["members_manage", "moderators_manage", "creator_manages"] = "members_manage"


class UpdateConversationRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class AddConversationMemberRequest(BaseModel):
    user_id: str
    member_role: Literal["owner", "moderator", "member"] = "member"


class UpdateConversationMemberRoleRequest(BaseModel):
    member_role: Literal["owner", "moderator", "member"]


class SendMessageRequest(BaseModel):
    body: str = ""
    reply_to_message_id: str | None = None
    attachments: list[dict[str, object]] = Field(default_factory=list)


class UpdateMessageRequest(BaseModel):
    body: str


class ObjectReferenceCreateRequest(BaseModel):
    source_object_id: str
    source_object_type: str
    target_object_id: str
    reference_text: str | None = None
    context: str | None = None
    lab_id: str = "lab:demo"


class ReferenceResolveRequest(BaseModel):
    text: str
    lab_id: str = "lab:demo"


class GeneralExperimentCreateRequest(BaseModel):
    lab_id: str = "lab:demo"
    experiment_id: str | None = None
    title: str
    short_description: str | None = None
    status: Literal["draft", "planned", "active", "paused", "completed", "archived"] = "draft"
    biological_system: str | None = None
    sample_unit_type: str = "sample"
    start_date: str | None = None
    expected_end_day: int | None = None


class NotebookFirstExperimentCreateRequest(BaseModel):
    lab_id: str = "lab:demo"
    experiment_id: str | None = None
    title: str | None = None
    initial_note: str | None = None


class GeneralExperimentFromProtocolRequest(BaseModel):
    lab_id: str = "lab:demo"
    experiment_id: str | None = None
    title: str
    protocol_id: str
    protocol_version_id: str


class GeneralCohortRequest(BaseModel):
    name: str
    description: str | None = None
    start_day: int | None = None
    start_date: str | None = None
    parent_cohort_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class GeneralConditionRequest(BaseModel):
    cohort_id: str | None = None
    name: str
    description: str | None = None
    condition_type: Literal["untreated", "vehicle_control", "treatment", "positive_control", "negative_control", "reference", "custom"] = "custom"
    replicate_count: int | None = None
    sample_count_per_replicate: int | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class GeneralInterventionRequest(BaseModel):
    cohort_id: str | None = None
    condition_id: str | None = None
    name: str
    intervention_type: Literal["compound", "media_change", "transfection", "infection", "stimulation", "inhibition", "surgery", "imaging", "collection", "assay", "custom"] = "custom"
    resource_id: str | None = None
    concentration_value: float | None = None
    concentration_unit: str | None = None
    dilution: str | None = None
    dose_value: float | None = None
    dose_unit: str | None = None
    duration_value: float | None = None
    duration_unit: str | None = None
    route: str | None = None
    notes: str | None = None


class GeneralEventRequest(BaseModel):
    cohort_id: str | None = None
    condition_id: str | None = None
    protocol_event_id: str | None = None
    event_type: Literal["protocol_step", "treatment", "media_change", "collection", "imaging", "assay", "observation", "milestone", "endpoint", "reminder", "custom"] = "custom"
    title: str
    description: str | None = None
    day: int | None = None
    date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    applies_to_all_conditions: bool = False
    destructive: bool | None = None
    source: Literal["manual", "protocol", "imported", "generated", "ai_proposed", "protocol_override"] = "manual"
    metadata: dict[str, object] = Field(default_factory=dict)


class GeneralProtocolAttachRequest(BaseModel):
    protocol_id: str
    protocol_version_id: str
    relationship: Literal["primary", "supporting", "assay", "imaging", "custom"] = "primary"
    inherit_events: bool = True
    insert_summary_note: bool = False


class GeneralExperimentUpdateRequest(BaseModel):
    title: str | None = None


class NotebookSaveRequest(BaseModel):
    current_version: int
    content: str
    document_format: Literal["rich_text_json", "markdown", "html"] = "markdown"
    title: str | None = None


class NotebookAttachmentRequest(BaseModel):
    attachment_type: Literal["image", "file", "spreadsheet", "pdf", "url", "researchos_resource"]
    resource_id: str | None = None
    storage_reference: str | None = None
    display_name: str
    mime_type: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class ExtractionDraftRequest(BaseModel):
    experiment_id: str | None = None
    source_type: Literal["typed_text", "voice_transcript", "document", "protocol_plus_text"] = "typed_text"
    source_text: str
    proposed_protocol_id: str | None = None
    proposed_protocol_version_id: str | None = None


class SamplePlanningPreviewRequest(BaseModel):
    assumptions: dict[str, object] = Field(default_factory=dict)


class ExperimentCopilotDraftRequest(BaseModel):
    narrative: str
    source_type: Literal["typed_text", "voice_transcript", "protocol_notes", "meeting_notes", "planning_notes"] = "typed_text"
    lab_id: str = "lab:demo"


class ExperimentCopilotClarifyRequest(BaseModel):
    answers: dict[str, object] = Field(default_factory=dict)


class ExperimentCopilotApproveRequest(BaseModel):
    title: str | None = None
    experiment_id: str | None = None


class ProtocolHubCreateRequest(BaseModel):
    lab_id: str = "lab:demo"
    title: str
    short_name: str | None = None
    description: str | None = None
    category: str | None = None
    biological_system: str | None = None
    sample_unit: str | None = None
    version_number: str = "1.0"
    summary_of_changes: str | None = None
    content: str = ""
    events: list[dict[str, object]] = Field(default_factory=list)
    materials: list[dict[str, object]] = Field(default_factory=list)
    media: list[dict[str, object]] = Field(default_factory=list)
    expected_results: list[dict[str, object]] = Field(default_factory=list)
    troubleshooting: list[dict[str, object]] = Field(default_factory=list)


class ProtocolHubVersionRequest(BaseModel):
    version_number: str
    summary_of_changes: str = ""
    content: str = ""
    events: list[dict[str, object]] = Field(default_factory=list)


class ProtocolHubBlankRequest(BaseModel):
    lab_id: str = "lab:demo"
    title: str
    category: str | None = None
    biological_system: str | None = None
    sample_unit: str | None = None
    version_number: str = "draft-1"
    content: str | None = None


class ProtocolHubImportRequest(BaseModel):
    lab_id: str = "lab:demo"
    source_type: Literal["pdf", "docx", "markdown", "txt", "image", "pasted_text", "voice", "manual", "template"] = "txt"
    original_filename: str | None = None
    storage_reference: str | None = None
    mime_type: str | None = None


class ProtocolHubTextDraftRequest(BaseModel):
    lab_id: str = "lab:demo"
    source_text: str
    origin: Literal["document", "pasted_text", "voice", "manual", "template"] = "pasted_text"
    proposed_title: str | None = None
    proposed_category: str | None = None
    source_citation: str | None = None
    import_id: str | None = None


class ProtocolHubDraftUpdateRequest(BaseModel):
    proposed_title: str | None = None
    proposed_category: str | None = None
    proposed_biological_system: str | None = None
    proposed_sample_unit: str | None = None
    proposed_duration: str | None = None
    proposed_events: list[dict[str, object]] | None = None
    proposed_materials: list[dict[str, object]] | None = None
    proposed_media: list[dict[str, object]] | None = None
    proposed_equipment: list[dict[str, object]] | None = None
    proposed_expected_results: list[dict[str, object]] | None = None
    proposed_qc: list[dict[str, object]] | None = None
    proposed_troubleshooting: list[dict[str, object]] | None = None
    proposed_references: list[dict[str, object]] | None = None
    ambiguities: list[object] | None = None
    warnings: list[object] | None = None
    confidence_by_field: dict[str, object] | None = None
    extraction_evidence: dict[str, object] | None = None
    status: Literal["draft", "awaiting_review", "approved", "rejected"] | None = None


class ProtocolHubDraftApproveRequest(BaseModel):
    version_label: str
    confirmed: bool = False
    target_protocol_id: str | None = None


class ProtocolNotebookSaveRequest(BaseModel):
    current_version: int
    content: str


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


class AuthReadinessResponse(BaseModel):
    """ResearchOS app-login readiness for lab-server/mobile deployment."""

    auth_mode: str
    require_login: bool
    auth_enforcement_enabled: bool
    dev_user_enabled: bool
    microsoft_client_configured: bool
    tenant_configured: bool
    redirect_uri: str
    user_table_ready: bool
    workspace_table_ready: bool
    microsoft_login_ready: bool
    onenote_sync_auth_separate: bool
    warnings: list[str] = Field(default_factory=list)


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


class LabIntelligenceStateRequest(BaseModel):
    """Persist one UI-state change for a Laboratory Intelligence item."""

    dismissed: bool | None = None
    pinned: bool | None = None


class WorkspaceResponse(BaseModel):
    """Lab workspace response."""

    workspace_id: str
    name: str
    institution: str | None = None
    description: str | None = None
    created_at: str | None = None
    owner_user_id: str | None = None
    created_by: str | None = None
    default_role: str = "researcher"
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


class CreateWorkspaceRequest(BaseModel):
    """Create a new lab workspace."""

    workspace_id: str | None = None
    name: str
    description: str = ""
    institution: str | None = None
    default_role: Literal["admin", "researcher", "viewer"] = "researcher"
    settings: dict[str, object] = Field(default_factory=dict)


class AddWorkspaceMemberRequest(BaseModel):
    """Add or update a user membership in a workspace."""

    user_id: str
    role: Literal["admin", "researcher", "viewer"] = "researcher"


class SetCurrentWorkspaceRequest(BaseModel):
    """Select the active workspace for the current user."""

    workspace_id: str


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


class EvidenceQueryRequest(BaseModel):
    """Natural-language query for cross-provider scientific evidence."""

    question: str


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
    "collection",
    "imaging",
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


class MobileSessionNoteRequest(BaseModel):
    """Mobile bench note appended to an active session."""

    note_type: Literal["manual_note", "voice_transcript", "observation", "treatment", "media_change"] = "manual_note"
    text: str


class MobileObservationRequest(BaseModel):
    """One-tap observation captured in Bench Mode."""

    text: str


class MobileTreatmentRequest(BaseModel):
    """Minimal treatment record captured in Bench Mode."""

    compound: str | None = None
    dose: str | None = None
    units: str | None = None
    time: str | None = None
    notes: str | None = None


class MobileMediaChangeRequest(BaseModel):
    """Minimal media-change record captured in Bench Mode."""

    media_type: str | None = None
    notes: str | None = None


class MobileVoiceNoteRequest(BaseModel):
    """Voice-note placeholder or future speech transcript captured in Bench Mode."""

    transcript: str | None = None
    placeholder: bool = True


class MobileAttachPlaceholderRequest(BaseModel):
    """Placeholder record for future camera/file/provider attachment flows."""

    attachment_type: Literal["image", "file", "graphpad", "sequencing", "other"] = "file"
    title: str | None = None
    notes: str | None = None


class VoiceDraftRequest(BaseModel):
    """Review-only voice command draft request.

    This request must not modify storage. It exists so users can review the
    transcript and parsed command before anything is committed.
    """

    transcript: str | None = None
    audio_reference: str | None = None
    session_id: str | None = None
    experiment_id: str | None = None


class VoiceConfirmRequest(BaseModel):
    """Confirmed voice command that may be committed to ResearchOS."""

    voice_session_id: str | None = None
    command_type: Literal[
        "start_experiment",
        "start_session",
        "end_session",
        "observation",
        "treatment",
        "media_change",
        "collection",
        "imaging",
        "custom_note",
    ]
    transcript: str
    parsed_fields: dict[str, object] = Field(default_factory=dict)
    session_id: str | None = None
    experiment_id: str | None = None
    create_notebook_draft: bool = True


class WizardTreatmentRequest(BaseModel):
    """One planned treatment row from the New Experiment Wizard."""

    compound: str | None = None
    concentration: str | None = None
    timepoint: str | None = None
    notes: str | None = None


class WizardMilestoneRequest(BaseModel):
    """One planned experiment milestone from the New Experiment Wizard."""

    label: str
    detail: str | None = None
    date: str | None = None


class NewExperimentWizardRequest(BaseModel):
    """Guided creation request for a planned experiment."""

    title: str
    experiment_id: str
    project: str | None = None
    workspace: str | None = None
    principal_investigator: str | None = None
    researcher: str | None = None
    date: str | None = None
    notes: str | None = None
    protocol_mode: Literal["select_existing", "create_new"] = "select_existing"
    protocol_id: str | None = None
    protocol_title: str | None = None
    protocol_notes: str | None = None
    cell_line: str | None = None
    organoid_batch: str | None = None
    treatments: list[WizardTreatmentRequest] = Field(default_factory=list)
    compounds: list[str] = Field(default_factory=list)
    concentrations: list[str] = Field(default_factory=list)
    timepoints: list[str] = Field(default_factory=list)
    replicates: str | None = None
    controls: list[str] = Field(default_factory=list)
    readouts: list[str] = Field(default_factory=list)
    markers: list[str] = Field(default_factory=list)
    microscopy: bool = False
    graphpad: bool = False
    rnaseq: bool = False
    flow_cytometry: bool = False
    other_readouts: str | None = None
    milestones: list[WizardMilestoneRequest] = Field(default_factory=list)
    create_notebook_draft: bool = True
    start_session: bool = False


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


ResourceType = Literal[
    "compound",
    "antibody",
    "marker",
    "gene",
    "protein",
    "cell_line",
    "organoid_line",
    "media",
    "growth_factor",
    "small_molecule",
    "reagent",
    "primer",
    "vector",
    "plasmid",
    "consumable",
    "equipment",
    "other",
]


class ResourceRequest(BaseModel):
    """Create or update a reusable ResearchOS resource."""

    resource_type: ResourceType = "other"
    name: str
    aliases: list[str] = Field(default_factory=list)
    vendor: str | None = None
    catalog_number: str | None = None
    lot_number: str | None = None
    rrid: str | None = None
    storage_location: str | None = None
    concentration: str | None = None
    units: str | None = None
    expiration: str | None = None
    notes: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class ResourceResponse(ResourceRequest):
    """ResearchOS resource record with usage history."""

    resource_id: str
    usages: list[dict[str, object]] = Field(default_factory=list)
    owner_user_id: str | None = None
    created_by: str | None = None
    workspace_id: str | None = None
    created_at: str
    updated_at: str


class InventoryItemRequest(BaseModel):
    """Create or update a local inventory item."""

    name: str
    category: str | None = None
    vendor: str | None = None
    catalog_number: str | None = None
    lot_number: str | None = None
    rrid: str | None = None
    price: float | None = None
    unit: str | None = None
    storage_location: str | None = None
    quantity: float | None = None
    reorder_threshold: float | None = None
    expiration_date: str | None = None
    barcode: str | None = None
    qr_code: str | None = None
    internal_label: str | None = None
    freezer_box: str | None = None
    freezer_position: str | None = None
    shelf: str | None = None
    room: str | None = None
    notes: str | None = None
    linked_resource_id: str | None = None


class InventoryItemResponse(InventoryItemRequest):
    """Stored inventory item."""

    item_id: str
    owner_user_id: str | None = None
    created_by: str | None = None
    workspace_id: str | None = None
    created_at: str
    updated_at: str


class InventoryUsageRequest(BaseModel):
    """Record inventory/reagent use in an experiment or session."""

    inventory_item_id: str | None = None
    experiment_id: str | None = None
    session_id: str | None = None
    protocol_id: str | None = None
    amount_used: float | None = None
    units: str | None = None
    date_used: str | None = None
    used_by: str | None = None
    purpose: str | None = None
    notes: str | None = None
    decrement_quantity: bool = False


class InventoryCodeAssignmentRequest(BaseModel):
    """Assign barcode/QR/internal label data to an inventory item."""

    barcode: str | None = None
    qr_code: str | None = None
    internal_label: str | None = None
    freezer_box: str | None = None
    freezer_position: str | None = None
    shelf: str | None = None
    room: str | None = None


class InventoryUsageResponse(InventoryUsageRequest):
    """Stored inventory usage record."""

    usage_id: str
    inventory_item_id: str
    experiment_id: str
    inventory_item_name: str | None = None
    vendor: str | None = None
    catalog_number: str | None = None
    lot_number: str | None = None
    rrid: str | None = None
    workspace_id: str | None = None
    created_at: str
    updated_at: str


class PurchaseRecordRequest(BaseModel):
    """Create or update a purchasing record."""

    item_name: str
    vendor: str | None = None
    catalog_number: str | None = None
    purchase_date: str | None = None
    cost: float | None = None
    quantity: float | None = None
    grant_or_funding_source: str | None = None
    purchaser: str | None = None
    oracle_po_number: str | None = None
    invoice_number: str | None = None
    status: str | None = "planned"
    notes: str | None = None


class PurchaseRecordResponse(PurchaseRecordRequest):
    """Stored purchase record."""

    purchase_id: str
    owner_user_id: str | None = None
    created_by: str | None = None
    workspace_id: str | None = None
    created_at: str
    updated_at: str


class PurchaseRequestRequest(BaseModel):
    """Create or update a lab purchase request before Oracle ordering."""

    item_name: str
    vendor: str | None = None
    catalog_number: str | None = None
    quantity_requested: float | None = None
    estimated_cost: float | None = None
    grant_or_funding_source: str | None = None
    requested_by: str | None = None
    request_date: str | None = None
    status: str = "draft"
    notes: str | None = None
    linked_inventory_item_id: str | None = None


class PurchaseRequestResponse(PurchaseRequestRequest):
    """Stored lab purchase request."""

    request_id: str
    owner_user_id: str | None = None
    created_by: str | None = None
    workspace_id: str | None = None
    created_at: str
    updated_at: str


class PurchaseRequestReceiveRequest(BaseModel):
    """Mark a request received and optionally add the quantity to inventory."""

    update_inventory_quantity: bool = False
    create_receiving_record: bool = False


class ReceivingRecordRequest(BaseModel):
    """Receive an ordered item before adding it to inventory."""

    purchase_request_id: str | None = None
    purchase_record_id: str | None = None
    inventory_item_id: str | None = None
    item_name: str
    vendor: str | None = None
    catalog_number: str | None = None
    lot_number: str | None = None
    quantity_received: float | None = None
    units: str | None = None
    received_by: str | None = None
    received_date: str | None = None
    expiration_date: str | None = None
    storage_location: str | None = None
    barcode_or_label: str | None = None
    notes: str | None = None


class ReceivingRecordResponse(ReceivingRecordRequest):
    """Stored receiving/intake record."""

    receiving_id: str
    owner_user_id: str | None = None
    created_by: str | None = None
    workspace_id: str | None = None
    created_at: str
    updated_at: str


class ReceivingInventoryIntakeRequest(BaseModel):
    """Convert a receiving record into inventory."""

    update_existing: bool = True


class ExperimentDesignRequest(BaseModel):
    """Create or update a provider-agnostic experiment design."""

    title: str
    experiment_type: str | None = None
    cell_line_or_model: str | None = None
    reporters: list[str] = Field(default_factory=list)
    description: str | None = None
    start_date: str | None = None
    created_by: str | None = None
    linked_experiment_id: str | None = None
    status: str = "draft"


class ExperimentDesignResponse(ExperimentDesignRequest):
    """Stored experiment design with child records."""

    design_id: str
    conditions: list[dict[str, object]] = Field(default_factory=list)
    events: list[dict[str, object]] = Field(default_factory=list)
    owner_user_id: str | None = None
    workspace_id: str | None = None
    created_at: str
    updated_at: str


class DesignConditionRequest(BaseModel):
    """One planned experimental condition."""

    condition_name: str
    treatment: str | None = None
    dose: str | None = None
    units: str | None = None
    start_day: str | None = None
    end_day: str | None = None
    notes: str | None = None
    replicate_count: int | None = None
    sample_count: int | None = None


class DesignEventRequest(BaseModel):
    """One event in a planned experiment timeline."""

    condition_id: str | None = None
    day: str
    event_type: str = "custom"
    title: str
    description: str | None = None
    required: bool = True
    alert_enabled: bool = False
    alert_offset_days: int = 0
    reminder_enabled: bool | None = None
    reminder_offset_days: int | None = None
    reminder_status: str = "pending"
    due_date: str | None = None
    completed: bool = False
    completed_at: str | None = None
    dismissed_at: str | None = None


class DesignImportRequest(BaseModel):
    """CSV import payload for experiment designs."""

    csv_text: str
    title: str | None = None
    experiment_type: str | None = None
    cell_line_or_model: str | None = None
    confirm_overwrite: bool = False


class DesignMappedCsvImportRequest(DesignImportRequest):
    """CSV import payload with explicit field-to-column mapping."""

    mapping: dict[str, str]


class DesignImportTemplateRequest(BaseModel):
    """Saved experiment design import mapping template."""

    name: str
    mapping: dict[str, str]
    provider: str = "experiment_designs"


class DesignImportTemplateResponse(DesignImportTemplateRequest):
    """Stored experiment design import mapping template."""

    template_id: str
    is_default: bool = False
    owner_user_id: str | None = None
    created_by: str | None = None
    workspace_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ExperimentDesignTemplateRequest(BaseModel):
    """Reusable experiment design template."""

    name: str
    description: str | None = None
    experiment_type: str | None = None
    default_cell_line_or_model: str | None = None
    default_reporters: list[str] = Field(default_factory=list)
    default_conditions: list[dict[str, object]] = Field(default_factory=list)
    default_events: list[dict[str, object]] = Field(default_factory=list)
    default_reminders: list[dict[str, object]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_by: str | None = None


class ExperimentDesignTemplateResponse(ExperimentDesignTemplateRequest):
    """Stored experiment design template."""

    template_id: str
    is_builtin: bool = False
    owner_user_id: str | None = None
    workspace_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class TemplateCreateDesignRequest(BaseModel):
    """Overrides when creating a concrete design from a template."""

    title: str | None = None
    start_date: str | None = None
    cell_line_or_model: str | None = None
    reporters: list[str] | None = None
    status: str = "draft"


class SaveDesignAsTemplateRequest(BaseModel):
    """Optional payload for saving a concrete design as a template."""

    name: str | None = None


class WellAssignmentRequest(BaseModel):
    """One well/tube/sample assignment in a layout."""

    well_id: str | None = None
    row: str | None = None
    column: int | None = None
    position: str | None = None
    condition: str | None = None
    replicate: int | None = None
    sample_id: str | None = None
    treatment: str | None = None
    dose: str | None = None
    units: str | None = None
    day: str | None = None
    notes: str | None = None


class PlateLayoutRequest(BaseModel):
    """Create or update a plate/rack/sample layout."""

    design_id: str
    title: str
    format: str = "96-well"
    rows: int
    columns: int
    wells: list[WellAssignmentRequest] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_by: str | None = None


class PlateLayoutResponse(BaseModel):
    """Stored plate/rack/sample layout."""

    layout_id: str
    design_id: str
    title: str
    format: str
    rows: int
    columns: int
    wells: list[dict[str, object]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_by: str | None = None
    owner_user_id: str | None = None
    workspace_id: str | None = None
    created_at: str
    updated_at: str


class GeneratePlateLayoutRequest(BaseModel):
    """Generate a layout from an experiment design."""

    title: str | None = None
    format: str = "96-well"
    rows: int | None = None
    columns: int | None = None
    randomized: bool = False
    grouped_by_condition: bool = True
    balanced: bool = False


class VisualNodeRequest(BaseModel):
    """One visual experiment builder node."""

    node_id: str
    type: str
    label: str
    properties: dict[str, object] = Field(default_factory=dict)
    x: float = 0
    y: float = 0


class VisualConnectionRequest(BaseModel):
    """One visual experiment builder connection."""

    source: str
    target: str
    relationship: str = "connects"


class VisualExperimentBuilderRequest(BaseModel):
    """Saved visual experiment builder canvas."""

    title: str
    description: str | None = None
    nodes: list[VisualNodeRequest] = Field(default_factory=list)
    connections: list[VisualConnectionRequest] = Field(default_factory=list)
    generated_design_id: str | None = None
    generated_plate_layout_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    created_by: str | None = None


class VisualExperimentBuilderResponse(BaseModel):
    """Stored visual experiment builder canvas."""

    builder_id: str
    title: str
    description: str | None = None
    nodes: list[dict[str, object]] = Field(default_factory=list)
    connections: list[dict[str, object]] = Field(default_factory=list)
    generated_design_id: str | None = None
    generated_plate_layout_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    created_by: str | None = None
    owner_user_id: str | None = None
    workspace_id: str | None = None
    created_at: str
    updated_at: str


class VisualBuilderGenerateRequest(BaseModel):
    """Options for compiling a visual builder into ResearchOS artifacts."""

    title: str | None = None
    start_date: str | None = None
    status: str = "draft"
    generate_plate_layout: bool = False
    plate_format: str = "96-well"
    randomized_layout: bool = False
    balanced_layout: bool = True


class FullFactorialRequest(BaseModel):
    """Simple full-factorial DoE request."""

    factors: dict[str, list[str]]


class BalanceCheckRequest(BaseModel):
    """Check a proposed condition table for simple balance issues."""

    conditions: list[DesignConditionRequest]


class PurchaseCsvImportRequest(BaseModel):
    """CSV import payload for Oracle/exported purchasing reports."""

    csv_text: str
    provider: str = "oracle_purchasing"


class PurchaseMappedCsvImportRequest(BaseModel):
    """CSV import payload with explicit field-to-column mapping."""

    csv_text: str
    mapping: dict[str, str]
    provider: str = "oracle_purchasing"


class PurchaseImportPreviewRequest(BaseModel):
    """CSV preview payload before importing purchasing records."""

    csv_text: str


class PurchaseImportTemplateRequest(BaseModel):
    """Saved purchasing import mapping template."""

    name: str
    mapping: dict[str, str]
    provider: str = "oracle_purchasing"


class PurchaseImportTemplateResponse(PurchaseImportTemplateRequest):
    """Stored purchasing import mapping template."""

    template_id: str
    is_default: bool = False
    owner_user_id: str | None = None
    created_by: str | None = None
    workspace_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ReagentMethodsRequest(BaseModel):
    """Request body for building methods-ready reagent text."""

    inventory_item_ids: list[str]
    style: Literal["paper", "grant", "protocol"] = "paper"
    include_lot_numbers: bool = True
    include_storage_locations: bool = False


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


class MemorySimilarRequest(BaseModel):
    """Request body for scientific memory similarity."""

    experiment_id: str
    limit: int = Field(default=5, ge=1, le=25)


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


class ProductionReadinessResponse(BaseModel):
    """Production safety readiness summary."""

    app_env: str
    data_classification: str
    auth_ready: bool
    https_ready: bool
    workspace_isolation_ready: bool
    backup_ready: bool
    audit_log_ready: bool
    onenote_read_ready: bool
    onenote_write_disabled: bool
    ai_provider_configured: bool
    warnings: list[str]
    recommended_next_steps: list[str]


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


def _wizard_payload(request: NewExperimentWizardRequest) -> ExperimentWizardPayload:
    """Convert the API request into the wizard service payload."""

    return ExperimentWizardPayload(
        title=request.title.strip(),
        experiment_id=request.experiment_id.strip(),
        project=request.project,
        workspace=request.workspace,
        principal_investigator=request.principal_investigator,
        researcher=request.researcher,
        date=request.date,
        notes=request.notes,
        protocol_mode=request.protocol_mode,
        protocol_id=request.protocol_id,
        protocol_title=request.protocol_title,
        protocol_notes=request.protocol_notes,
        cell_line=request.cell_line,
        organoid_batch=request.organoid_batch,
        treatments=[item.model_dump() for item in request.treatments],
        compounds=request.compounds,
        concentrations=request.concentrations,
        timepoints=request.timepoints,
        replicates=request.replicates,
        controls=request.controls,
        readouts=request.readouts,
        markers=request.markers,
        microscopy=request.microscopy,
        graphpad=request.graphpad,
        rnaseq=request.rnaseq,
        flow_cytometry=request.flow_cytometry,
        other_readouts=request.other_readouts,
        milestones=[item.model_dump() for item in request.milestones],
        create_notebook_draft=request.create_notebook_draft,
        start_session=request.start_session,
    )


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
def global_knowledge_graph(workspace_id: str | None = Query(default=None)) -> dict[str, object]:
    """Return global provider-agnostic knowledge graph statistics."""

    resolved_workspace_id = _current_workspace_id(workspace_id)
    scoped_service = KnowledgeGraphService(settings=settings, workspace_id=resolved_workspace_id)
    summary = scoped_service.summary()
    return {
        **summary,
        "workspace_id": resolved_workspace_id,
        "workspace_scoping": "metadata_only",
    }


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


@app.get("/objects", tags=["objects"])
def research_objects(
    request: Request,
    lab_id: str = Query("lab:demo"),
    object_type: str | None = Query(default=None),
    limit: int = Query(250, ge=1, le=1000),
) -> list[dict[str, object]]:
    """Return visible universal ResearchOS objects."""

    return _research_object_service().list_objects(
        _request_user_id(request),
        lab_id=lab_id,
        object_type=object_type,
        limit=limit,
    )


@app.get("/objects/search", tags=["objects"])
def research_object_search(
    request: Request,
    q: str = Query(..., min_length=1),
    lab_id: str = Query("lab:demo"),
    limit: int = Query(12, ge=1, le=50),
) -> list[dict[str, object]]:
    """Fuzzy-search visible ResearchOS objects for autocomplete/reference insertion."""

    return _research_object_service().search(_request_user_id(request), q, lab_id=lab_id, limit=limit)


@app.get("/objects/autocomplete", tags=["objects"])
def research_object_autocomplete(
    request: Request,
    q: str = Query(...),
    lab_id: str = Query("lab:demo"),
    limit: int = Query(8, ge=1, le=25),
) -> list[dict[str, object]]:
    """Return display-ready autocomplete candidates for @ and [[ ]] references."""

    return _research_object_service().autocomplete(_request_user_id(request), q, lab_id=lab_id, limit=limit)


@app.get("/objects/resolve", tags=["objects"])
def resolve_research_object_reference(
    request: Request,
    ref: str = Query(...),
    lab_id: str = Query("lab:demo"),
) -> dict[str, object]:
    """Resolve a user-facing reference token to a visible ResearchObject."""

    return _research_object_service().resolve_reference(_request_user_id(request), ref, lab_id=lab_id)


@app.post("/references/resolve", tags=["objects"])
def resolve_research_object_references(request_body: ReferenceResolveRequest, request: Request) -> list[dict[str, object]]:
    """Extract and resolve all @ and [[ ]] references in a text block."""

    return _research_object_service().extract_references_from_text(
        _request_user_id(request),
        request_body.text,
        lab_id=request_body.lab_id,
    )


@app.post("/references", tags=["objects"])
def create_research_object_reference(request_body: ObjectReferenceCreateRequest, request: Request) -> dict[str, object]:
    """Persist an explicit source-object to target-object reference."""

    try:
        return _research_object_service().create_reference(
            user_id=_request_user_id(request),
            source_object_id=request_body.source_object_id,
            source_object_type=request_body.source_object_type,
            target_object_id=request_body.target_object_id,
            reference_text=request_body.reference_text,
            context=request_body.context,
            lab_id=request_body.lab_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/objects/{object_id:path}/hover-card", tags=["objects"])
def research_object_hover_card(object_id: str, request: Request, lab_id: str = Query("lab:demo")) -> dict[str, object]:
    """Return a compact preview card for hover/long-press object references."""

    card = _research_object_service().hover_card(_request_user_id(request), object_id, lab_id=lab_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Object not found.")
    return card


@app.get("/objects/{object_id:path}/backlinks", tags=["objects"])
def research_object_backlinks(object_id: str, request: Request, lab_id: str = Query("lab:demo")) -> list[dict[str, object]]:
    """Return visible objects that explicitly or implicitly reference this object."""

    return _research_object_service().backlinks(_request_user_id(request), object_id, lab_id=lab_id)


@app.get("/objects/{object_id:path}/references", tags=["objects"])
def research_object_references(object_id: str, request: Request, lab_id: str = Query("lab:demo")) -> list[dict[str, object]]:
    """Return visible outgoing object references from this source object."""

    return _research_object_service().references_from(_request_user_id(request), object_id, lab_id=lab_id)


@app.get("/objects/{object_id:path}", tags=["objects"])
def research_object_detail(object_id: str, request: Request, lab_id: str = Query("lab:demo")) -> dict[str, object]:
    """Return a visible object detail/preview payload."""

    obj = _research_object_service().get_object(_request_user_id(request), object_id, lab_id=lab_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found.")
    return obj


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


@app.get("/extensions", tags=["extensions"])
def extensions() -> dict[str, object]:
    """Return installed ResearchOS extensions and marketplace placeholder."""

    return extension_manager.status()


@app.get("/extensions/{extension_id}", tags=["extensions"])
def extension_detail(extension_id: str) -> dict[str, object]:
    """Return one installed extension."""

    extension = extension_manager.registry.get(extension_id)
    if extension is None:
        raise HTTPException(status_code=404, detail=f"Extension not found: {extension_id}")
    return extension.as_dict()


@app.post("/extensions/{extension_id}/enable", tags=["extensions"])
def enable_extension(extension_id: str) -> dict[str, object]:
    """Enable one installed extension."""

    if not extension_manager.enable_extension(extension_id):
        raise HTTPException(status_code=404, detail=f"Extension not found: {extension_id}")
    return extension_manager.status()


@app.post("/extensions/{extension_id}/disable", tags=["extensions"])
def disable_extension(extension_id: str) -> dict[str, object]:
    """Disable one installed extension."""

    if not extension_manager.disable_extension(extension_id):
        raise HTTPException(status_code=404, detail=f"Extension not found: {extension_id}")
    return extension_manager.status()


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


def _production_readiness() -> dict[str, object]:
    """Summarize production safety gaps without enforcing restrictions."""

    auth = _auth_readiness()
    onenote = _onenote_readiness()
    deployment = _deployment_status()
    public_base_url = str(deployment.get("public_base_url") or "")
    redirect_uri = str(onenote.get("current_redirect_uri") or settings.microsoft_redirect_uri or "")
    https_ready = public_base_url.startswith("https://") and (
        not redirect_uri or redirect_uri.startswith("https://") or "localhost" in redirect_uri
    )
    auth_ready = bool(auth.get("auth_enforcement_enabled")) and bool(auth.get("microsoft_login_ready"))
    workspace_isolation_ready = False
    backup_ready = False
    audit_log_ready = False
    onenote_read_ready = bool(onenote.get("read_only_sync_ready"))
    onenote_write_disabled = bool(onenote.get("write_back_disabled", True))
    ai_provider_configured = settings.ai_provider.strip().lower() not in {"", "none"} and (
        bool(settings.ai_api_key.strip()) or bool(settings.ai_base_url.strip())
    )

    warnings: list[str] = []
    next_steps: list[str] = []
    if settings.environment != "production":
        warnings.append(f"Current APP_ENV is {settings.environment}; ResearchOS is running in preview/development mode.")
    if settings.data_classification != "demo":
        warnings.append(f"DATA_CLASSIFICATION is {settings.data_classification}; confirm lab policies before using real data.")
    if not auth_ready:
        warnings.append("Production login is not ready or not enforced.")
        next_steps.append("Enable Microsoft app login with REQUIRE_LOGIN=true after UCSD/lab approval.")
    if not https_ready:
        warnings.append("HTTPS is not configured for the public ResearchOS URL.")
        next_steps.append("Deploy behind HTTPS before lab-server, PWA, or mobile use.")
    if not workspace_isolation_ready:
        warnings.append("Workspace isolation is metadata-only; strict access control is not enforced.")
        next_steps.append("Enforce workspace membership checks before multi-lab deployment.")
    if not backup_ready:
        warnings.append("Automated database backup readiness is not implemented.")
        next_steps.append("Define SQLite backup/restore policy and test recovery.")
    if not audit_log_ready:
        warnings.append("Audit logging is not production-ready.")
        next_steps.append("Add audit logs for login, sync, data export, write-back, and admin actions.")
    if ai_provider_configured and settings.data_classification in {"research", "restricted"}:
        warnings.append("AI provider is configured; review data exposure policy for unpublished or restricted research data.")
        next_steps.append("Document whether AI calls are local-only or cloud-based for this workspace.")
    if not onenote_read_ready:
        warnings.append("OneNote read-only sync is not fully ready for this session.")
    if onenote_write_disabled:
        next_steps.append("Keep OneNote write-back disabled until separate UCSD IT approval and review-before-save controls exist.")

    return {
        "app_env": settings.environment,
        "data_classification": settings.data_classification,
        "auth_ready": auth_ready,
        "https_ready": https_ready,
        "workspace_isolation_ready": workspace_isolation_ready,
        "backup_ready": backup_ready,
        "audit_log_ready": audit_log_ready,
        "onenote_read_ready": onenote_read_ready,
        "onenote_write_disabled": onenote_write_disabled,
        "ai_provider_configured": ai_provider_configured,
        "warnings": warnings,
        "recommended_next_steps": next_steps,
    }


@app.get("/status/production-readiness", response_model=ProductionReadinessResponse, tags=["system"])
def production_readiness() -> ProductionReadinessResponse:
    """Return production safety readiness without enforcing restrictions."""

    return ProductionReadinessResponse(**_production_readiness())


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

    dashboard = dashboard_service.build(use_ai=use_ai)
    dashboard["laboratory_intelligence_feed"] = lab_intelligence_service.build_feed(limit=30)
    dashboard["morning_brief"] = overnight_intelligence_service.morning_brief(period="today", limit=8)
    return dashboard


@app.get("/whiteboard", tags=["whiteboard"])
def laboratory_whiteboard(workspace_id: str | None = Query(default=None)) -> dict[str, object]:
    """Return a TV-friendly situational awareness summary for the laboratory."""

    store = SQLiteStore(settings=settings)
    workspace_id = workspace_id if isinstance(workspace_id, str) else None
    resolved_workspace_id = _current_workspace_id(workspace_id)
    workspace = current_workspace(settings, store)
    experiments = store.list_experiments(workspace_id=resolved_workspace_id)
    sessions_list = store.list_sessions(workspace_id=resolved_workspace_id)
    active_sessions = [session for session in sessions_list if session.get("status") == "active"]
    designs = _designs_for_reminders(resolved_workspace_id)
    due_today = due_events(designs, days=0)
    upcoming = due_events(designs, days=7)
    inventory_summary = inventory_status_summary(store.list_inventory_items(workspace_id=resolved_workspace_id))
    purchase_requests = store.list_purchase_requests(workspace_id=resolved_workspace_id)
    papers = _whiteboard_recent_literature(store, resolved_workspace_id)
    feed = lab_intelligence_service.build_feed(limit=12, workspace_id=resolved_workspace_id)
    morning = overnight_intelligence_service.morning_brief(period="today", limit=8, workspace_id=resolved_workspace_id)
    timeline_events = _whiteboard_recent_timeline(store, experiments)

    treatment_events = _filter_design_events(upcoming, {"treatment", "media_change"})
    imaging_events = _filter_design_events(upcoming, {"imaging", "fixation", "staining"})
    collection_events = _filter_design_events(upcoming, {"collection", "sequencing"})
    active_experiments = [_whiteboard_experiment_card(store, experiment, active_sessions) for experiment in experiments[:10]]

    sections = [
        _whiteboard_section("active_experiments", "Active Experiments", active_experiments, "science"),
        _whiteboard_section("todays_tasks", "Today's Tasks", [_whiteboard_reminder_card(item) for item in due_today[:12]], "task"),
        _whiteboard_section("todays_imaging", "Today's Imaging", [_whiteboard_reminder_card(item) for item in imaging_events[:8]], "image"),
        _whiteboard_section("todays_collections", "Today's Collections", [_whiteboard_reminder_card(item) for item in collection_events[:8]], "collection"),
        _whiteboard_section("todays_treatments", "Today's Treatments", [_whiteboard_reminder_card(item) for item in treatment_events[:8]], "treatment"),
        _whiteboard_section("inventory_alerts", "Inventory Alerts", _whiteboard_inventory_cards(inventory_summary), "inventory"),
        _whiteboard_section("purchase_requests", "Purchase Requests", [_whiteboard_purchase_request_card(item) for item in purchase_requests[:8]], "purchase"),
        _whiteboard_section("recent_literature", "Recent Literature", [_whiteboard_literature_card(item) for item in papers[:6]], "literature"),
        _whiteboard_section("research_copilot", "Research Copilot", _whiteboard_copilot_cards(experiments, inventory_summary, due_today), "copilot"),
        _whiteboard_section("laboratory_intelligence", "Laboratory Intelligence", [_whiteboard_intelligence_card(item) for item in list(feed.get("items") or [])[:8] if isinstance(item, dict)], "intelligence"),
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": workspace,
        "display": {
            "layout": "whiteboard",
            "refresh_seconds": 60,
            "rotation_seconds": 20,
            "high_contrast": True,
            "dark_mode_ready": True,
            "tv_friendly": True,
        },
        "metrics": {
            "active_experiments": len(active_experiments),
            "active_sessions": len(active_sessions),
            "due_today": len(due_today),
            "upcoming": len(upcoming),
            "inventory_alerts": len(_whiteboard_inventory_cards(inventory_summary)),
            "purchase_requests": len(purchase_requests),
            "recent_literature": len(papers),
            "intelligence_items": feed.get("total_items", 0),
        },
        "sections": sections,
        "rotation": [
            {"id": "dashboard", "title": "Dashboard", "sections": ["active_experiments", "todays_tasks", "laboratory_intelligence"]},
            {"id": "timeline", "title": "Timeline", "events": timeline_events[:12]},
            {"id": "experiment_status", "title": "Experiment Status", "sections": ["active_experiments", "todays_imaging", "todays_treatments"]},
            {"id": "inventory", "title": "Inventory", "sections": ["inventory_alerts", "purchase_requests"]},
            {"id": "morning_brief", "title": "Morning Brief", "summary": morning.get("summary"), "items": _whiteboard_morning_items(morning)},
        ],
        "empty_state": "No active lab activity is available yet. Load demo data, start sessions, or activate experiment designs.",
    }


def _whiteboard_section(section_id: str, title: str, cards: list[dict[str, object]], icon: str) -> dict[str, object]:
    """Return a consistent display section for the laboratory whiteboard."""

    return {
        "id": section_id,
        "title": title,
        "icon": icon,
        "count": len(cards),
        "cards": cards,
        "empty_message": f"No {title.lower()} right now.",
    }


def _whiteboard_card(
    title: object,
    subtitle: object = "",
    *,
    status: object = "",
    priority: str = "normal",
    route: str | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    """Return one display-ready whiteboard card."""

    return {
        "title": str(title or "Untitled"),
        "subtitle": str(subtitle or ""),
        "status": str(status or ""),
        "priority": priority,
        "route": route,
        "metadata": metadata or {},
    }


def _whiteboard_experiment_card(
    store: SQLiteStore,
    experiment: dict[str, object],
    active_sessions: list[dict[str, object]],
) -> dict[str, object]:
    """Summarize one experiment for display."""

    workflow = WorkflowEngine(store).workflow_for_experiment(experiment)
    experiment_refs = _experiment_reference_aliases(experiment)
    has_active_session = any(str(session.get("experiment_id") or "") in experiment_refs for session in active_sessions)
    compounds = ", ".join(list(experiment.get("compounds") or [])[:3]) if isinstance(experiment.get("compounds"), list) else ""
    markers = ", ".join(list(experiment.get("markers") or [])[:3]) if isinstance(experiment.get("markers"), list) else ""
    return _whiteboard_card(
        experiment.get("experiment_id") or experiment.get("title") or experiment.get("id"),
        " / ".join(part for part in [compounds, markers] if part) or experiment.get("title") or "",
        status="Active session" if has_active_session else str(workflow.get("current_stage") or "Planning"),
        priority="high" if has_active_session else "normal",
        route=f"#/experiments/{experiment.get('id')}/workspace",
        metadata={"experiment_id": experiment.get("id"), "workflow_stage": workflow.get("current_stage")},
    )


def _whiteboard_reminder_card(event: dict[str, object]) -> dict[str, object]:
    """Summarize an experiment design reminder."""

    return _whiteboard_card(
        event.get("title") or event.get("event_type") or "Design event",
        " / ".join(str(part) for part in [event.get("design_title"), event.get("condition_name"), event.get("day")] if part),
        status=event.get("reminder_status") or event.get("status") or event.get("due_date") or "scheduled",
        priority="high" if event.get("reminder_status") in {"due", "overdue"} else "normal",
        route=f"#/design-planner",
        metadata={key: value for key, value in event.items() if key in {"design_id", "event_id", "event_type", "due_date", "day"}},
    )


def _filter_design_events(events: list[dict[str, object]], event_types: set[str]) -> list[dict[str, object]]:
    """Return reminders whose event type belongs on a specific whiteboard panel."""

    return [event for event in events if str(event.get("event_type") or "").lower() in event_types]


def _whiteboard_inventory_cards(summary: dict[str, object]) -> list[dict[str, object]]:
    """Return top inventory alerts."""

    cards: list[dict[str, object]] = []
    for key, label, priority in [
        ("reorder_needed", "Reorder needed", "high"),
        ("expired", "Expired", "critical"),
        ("expiring_soon", "Expiring soon", "high"),
        ("low_stock", "Low stock", "high"),
    ]:
        for item in list(summary.get(key) or [])[:4]:
            if isinstance(item, dict):
                cards.append(
                    _whiteboard_card(
                        item.get("name") or item.get("item_id"),
                        " / ".join(str(part) for part in [item.get("vendor"), item.get("storage_location")] if part),
                        status=label,
                        priority=priority,
                        route="#/inventory",
                        metadata={"item_id": item.get("item_id"), "quantity": item.get("quantity")},
                    )
                )
    return cards[:10]


def _whiteboard_purchase_request_card(request: dict[str, object]) -> dict[str, object]:
    """Summarize one purchase request."""

    return _whiteboard_card(
        request.get("item_name") or request.get("request_id"),
        " / ".join(str(part) for part in [request.get("vendor"), request.get("grant_or_funding_source")] if part),
        status=request.get("status") or "draft",
        priority="high" if request.get("status") in {"submitted", "approved"} else "normal",
        route="#/purchases",
        metadata={"request_id": request.get("request_id"), "estimated_cost": request.get("estimated_cost")},
    )


def _whiteboard_literature_card(paper: dict[str, object]) -> dict[str, object]:
    """Summarize one recent paper/literature record."""

    return _whiteboard_card(
        paper.get("title") or paper.get("document_id") or "Literature",
        " / ".join(str(part) for part in [paper.get("year"), paper.get("journal")] if part),
        status="Literature",
        priority="normal",
        route="#/literature",
        metadata={"paper_id": paper.get("paper_id") or paper.get("id"), "doi": paper.get("doi")},
    )


def _whiteboard_recent_literature(store: SQLiteStore, workspace_id: str | None) -> list[dict[str, object]]:
    """Return recent literature summaries from provider-agnostic documents."""

    papers: list[dict[str, object]] = []
    for document in store.list_documents(workspace_id=workspace_id):
        if document.get("provider") != "literature":
            continue
        detail = store.get_document(str(document["id"]))
        if detail is not None:
            papers.append(_paper_summary(detail))
    return papers[:12]


def _whiteboard_intelligence_card(item: dict[str, object]) -> dict[str, object]:
    """Summarize one Laboratory Intelligence feed item."""

    return _whiteboard_card(
        item.get("title") or item.get("item_type") or "Intelligence",
        item.get("summary") or "",
        status=item.get("priority") or item.get("item_type") or "",
        priority=str(item.get("priority") or "normal").lower(),
        route=item.get("route") if isinstance(item.get("route"), str) else "#/dashboard",
        metadata={"item_id": item.get("item_id"), "item_type": item.get("item_type")},
    )


def _whiteboard_copilot_cards(
    experiments: list[dict[str, object]],
    inventory_summary: dict[str, object],
    due_today: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Create deterministic Copilot cards from actual records only."""

    cards = [
        _whiteboard_card("Experiments indexed", f"{len(experiments)} experiments available for review.", status="Observed", priority="normal"),
    ]
    if due_today:
        cards.append(_whiteboard_card("Tasks due today", f"{len(due_today)} design reminders need attention.", status="Suggested action", priority="high"))
    reorder_count = int(inventory_summary.get("reorder_needed_count") or 0)
    if reorder_count:
        cards.append(_whiteboard_card("Inventory needs ordering", f"{reorder_count} inventory items are at or below reorder threshold.", status="Suggested action", priority="high"))
    return cards[:6]


def _whiteboard_recent_timeline(store: SQLiteStore, experiments: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return recent timeline cards across experiments."""

    events: list[dict[str, object]] = []
    for experiment in experiments[:8]:
        timeline = _experiment_timeline(store, experiment)
        for event in list(timeline.get("events") or [])[-5:]:
            if isinstance(event, dict):
                events.append(
                    _whiteboard_card(
                        event.get("title") or event.get("event_type"),
                        event.get("description") or "",
                        status=event.get("timestamp") or "",
                        priority="normal",
                        route=f"#/experiments/{experiment.get('id')}/workspace",
                        metadata={"event_type": event.get("event_type"), "experiment_id": experiment.get("id")},
                    )
                )
    return events[-20:]


def _whiteboard_morning_items(morning: dict[str, object]) -> list[dict[str, object]]:
    """Flatten morning brief sections into display cards."""

    cards: list[dict[str, object]] = []
    for key in ["new_experiments", "updated_experiments", "missing_analyses", "new_literature", "knowledge_graph_changes", "resource_alerts", "research_copilot_insights", "suggested_priorities"]:
        for item in list(morning.get(key) or [])[:4]:
            if isinstance(item, dict):
                cards.append(_whiteboard_card(item.get("title") or key.replace("_", " ").title(), item.get("summary") or item.get("description") or "", status=key.replace("_", " ").title()))
            else:
                cards.append(_whiteboard_card(key.replace("_", " ").title(), item, status="Morning Brief"))
    return cards[:12]


@app.get("/intelligence/feed", tags=["intelligence"])
def laboratory_intelligence_feed(
    item_type: str | None = Query(default=None),
    include_dismissed: bool = Query(default=False),
    pinned_first: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    workspace_id: str | None = Query(default=None),
) -> dict[str, object]:
    """Return the provenance-backed Laboratory Intelligence feed."""

    return lab_intelligence_service.build_feed(
        item_type=item_type,
        include_dismissed=include_dismissed,
        pinned_first=pinned_first,
        limit=limit,
        workspace_id=_current_workspace_id(workspace_id),
    )


@app.post("/intelligence/feed/{item_id}/state", tags=["intelligence"])
def set_laboratory_intelligence_item_state(item_id: str, request: LabIntelligenceStateRequest) -> dict[str, object]:
    """Persist pin/dismiss state for one Laboratory Intelligence item."""

    return lab_intelligence_service.set_item_state(item_id, dismissed=request.dismissed, pinned=request.pinned)


@app.post("/intelligence/feed/{item_id}/dismiss", tags=["intelligence"])
def dismiss_laboratory_intelligence_item(item_id: str) -> dict[str, object]:
    """Dismiss one Laboratory Intelligence feed item."""

    return lab_intelligence_service.set_item_state(item_id, dismissed=True)


@app.post("/intelligence/feed/{item_id}/pin", tags=["intelligence"])
def pin_laboratory_intelligence_item(item_id: str, request: LabIntelligenceStateRequest | None = Body(default=None)) -> dict[str, object]:
    """Pin or unpin one Laboratory Intelligence feed item."""

    pinned = True if request is None or request.pinned is None else request.pinned
    return lab_intelligence_service.set_item_state(item_id, pinned=pinned)


@app.get("/intelligence/morning", tags=["intelligence"])
def morning_intelligence_brief(
    period: Literal["today", "yesterday", "last_week"] = Query(default="today"),
    limit: int = Query(default=12, ge=1, le=100),
    workspace_id: str | None = Query(default=None),
) -> dict[str, object]:
    """Return a provenance-backed Morning Brief for recent lab changes."""

    return overnight_intelligence_service.morning_brief(
        period=period,
        limit=limit,
        workspace_id=_current_workspace_id(workspace_id),
    )


@app.get("/workflows", response_model=list[WorkflowResponse], tags=["workflows"])
def workflows(workspace_id: str | None = Query(default=None)) -> list[WorkflowResponse]:
    """Return ResearchOS workflows for extracted experiments."""

    store = SQLiteStore(settings=settings)
    resolved_workspace_id = _current_workspace_id(workspace_id)
    return [WorkflowResponse(**workflow) for workflow in WorkflowEngine(store).list_workflows(workspace_id=resolved_workspace_id)]


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


def _auth_readiness() -> dict[str, object]:
    """Return app-login readiness without changing enforcement behavior."""

    store = SQLiteStore(settings=settings)
    try:
        store.list_users()
        user_table_ready = True
    except Exception:
        user_table_ready = False
    try:
        store.list_workspaces()
        workspace_table_ready = True
    except Exception:
        workspace_table_ready = False

    configured_mode = auth_mode(settings)
    dev_user_enabled = configured_mode in {"dev", "disabled"} or not settings.require_login
    microsoft_client_configured = bool(settings.microsoft_client_id.strip())
    tenant_configured = bool(settings.microsoft_tenant_id.strip())
    microsoft_login_ready = (
        configured_mode == "microsoft"
        and settings.require_login
        and microsoft_client_configured
        and tenant_configured
        and user_table_ready
        and workspace_table_ready
    )
    warnings: list[str] = []
    if not settings.require_login:
        warnings.append("Login is not required; this is appropriate for local demo mode but not production lab-server deployment.")
    if configured_mode == "microsoft" and not microsoft_client_configured:
        warnings.append("AUTH_MODE is microsoft but MICROSOFT_CLIENT_ID is not configured.")
    if configured_mode == "microsoft" and settings.microsoft_tenant_id.lower() == "common":
        warnings.append("Microsoft tenant is set to common; UCSD/lab production should use an approved tenant-specific app.")
    if settings.microsoft_redirect_uri.startswith("http://") and "localhost" not in settings.microsoft_redirect_uri:
        warnings.append("Microsoft redirect URI is plain HTTP and not localhost; production/mobile deployments require HTTPS.")
    if settings.auth_enabled and not settings.require_login:
        warnings.append("AUTH_ENABLED is true but REQUIRE_LOGIN is false; login enforcement remains disabled.")

    return {
        "auth_mode": configured_mode,
        "require_login": settings.require_login,
        "auth_enforcement_enabled": settings.auth_enabled and settings.require_login,
        "dev_user_enabled": dev_user_enabled,
        "microsoft_client_configured": microsoft_client_configured,
        "tenant_configured": tenant_configured,
        "redirect_uri": settings.microsoft_redirect_uri,
        "user_table_ready": user_table_ready,
        "workspace_table_ready": workspace_table_ready,
        "microsoft_login_ready": microsoft_login_ready,
        "onenote_sync_auth_separate": True,
        "warnings": warnings,
    }


@app.get("/auth/readiness", response_model=AuthReadinessResponse, tags=["auth"])
def auth_readiness() -> AuthReadinessResponse:
    """Return ResearchOS app-login readiness for future Microsoft identity."""

    return AuthReadinessResponse(**_auth_readiness())


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


@app.get("/users/me/access", tags=["authorization"])
def my_access(request: Request, lab_id: str = Query("lab:demo")) -> dict[str, object]:
    """Return current user's lab role and granular permissions."""

    authz = _authorization_service()
    return authz.user_access(_request_user_id(request), lab_id)


@app.get("/labs/{lab_id}/members", tags=["authorization"])
def lab_members(lab_id: str, request: Request) -> list[dict[str, object]]:
    """Return lab members when caller may manage members or owns the lab."""

    authz = _authorization_service()
    user_id = _request_user_id(request)
    access = authz.user_access(user_id, lab_id)
    if "lab.members.manage" not in access["permissions"] and access["role"] != "owner":
        raise HTTPException(status_code=403, detail="Not allowed to view lab members.")
    return authz.list_members(lab_id)


@app.get("/notebooks", tags=["notebooks"])
def notebooks(request: Request, lab_id: str = Query("lab:demo")) -> list[dict[str, object]]:
    """List only notebooks visible to the current user."""

    authz = _authorization_service()
    return authz.list_visible_notebooks(_request_user_id(request), lab_id)


@app.get("/notebooks/{notebook_id}", tags=["notebooks"])
def notebook_detail(notebook_id: str, request: Request) -> dict[str, object]:
    """Return a notebook only when authorized."""

    authz = _authorization_service()
    notebook = authz.get_notebook(_request_user_id(request), notebook_id)
    if notebook is None:
        raise HTTPException(status_code=404, detail="Notebook not found.")
    return notebook


@app.get("/notebooks/{notebook_id}/entries", tags=["notebooks"])
def notebook_entries(notebook_id: str, request: Request) -> list[dict[str, object]]:
    """List entries using notebook-level authorization."""

    authz = _authorization_service()
    try:
        return authz.notebook_entries(_request_user_id(request), notebook_id)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Notebook not found.")


@app.get("/notebook-entries/{entry_id}", tags=["notebooks"])
def notebook_entry_detail(entry_id: str, request: Request) -> dict[str, object]:
    """Return entry details only if the parent notebook is visible."""

    authz = _authorization_service()
    try:
        entry = authz.entry_detail(_request_user_id(request), entry_id)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Entry not found.")
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found.")
    return entry


@app.post("/notebooks/{notebook_id}/share", tags=["notebooks"])
def share_notebook(notebook_id: str, request_body: ShareNotebookRequest, request: Request) -> dict[str, object]:
    """Share a notebook with a user, group, or role."""

    authz = _authorization_service()
    try:
        return authz.share_notebook(
            actor_user_id=_request_user_id(request),
            notebook_id=notebook_id,
            principal_type=request_body.principal_type,
            principal_id=request_body.principal_id,
            access_level=request_body.access_level,
            expires_at=request_body.expires_at,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@app.get("/notebooks/{notebook_id}/permissions", tags=["notebooks"])
def notebook_permissions(notebook_id: str, request: Request) -> list[dict[str, object]]:
    """List notebook sharing grants for notebook managers."""

    authz = _authorization_service()
    if not authz.can_user(_request_user_id(request), "manage", "notebook", notebook_id).allowed:
        raise HTTPException(status_code=403, detail="Not allowed to manage notebook sharing.")
    return authz.list_permissions(notebook_id)


@app.put("/notebooks/{notebook_id}/permissions/{permission_id}", tags=["notebooks"])
def update_notebook_permission(
    notebook_id: str,
    permission_id: str,
    request_body: UpdateNotebookPermissionRequest,
    request: Request,
) -> dict[str, object]:
    authz = _authorization_service()
    try:
        permission = authz.update_permission(_request_user_id(request), notebook_id, permission_id, request_body.access_level)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if permission is None:
        raise HTTPException(status_code=404, detail="Permission not found.")
    return permission


@app.delete("/notebooks/{notebook_id}/permissions/{permission_id}", tags=["notebooks"])
def delete_notebook_permission(notebook_id: str, permission_id: str, request: Request) -> dict[str, object]:
    authz = _authorization_service()
    try:
        deleted = authz.revoke_permission(_request_user_id(request), notebook_id, permission_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=404, detail="Permission not found.")
    return {"deleted": True}


@app.post("/groups", tags=["authorization"])
def create_group(request_body: CreateGroupRequest, request: Request) -> dict[str, object]:
    authz = _authorization_service()
    try:
        return authz.create_group(_request_user_id(request), request_body.lab_id, request_body.name, request_body.description)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@app.post("/groups/{group_id}/members", tags=["authorization"])
def add_group_member(group_id: str, request_body: AddGroupMemberRequest, request: Request) -> dict[str, object]:
    authz = _authorization_service()
    try:
        return authz.add_group_member(_request_user_id(request), group_id, request_body.user_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Group not found.")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@app.get("/labs/{lab_id}/audit", tags=["authorization"])
def audit_events(lab_id: str, request: Request) -> list[dict[str, object]]:
    authz = _authorization_service()
    try:
        return authz.audit_events(_request_user_id(request), lab_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


def _chat_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ChatAuthorizationError):
        return HTTPException(status_code=404, detail="Conversation not found.")
    if isinstance(exc, ChatValidationError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@app.get("/chat/conversations", tags=["chat"])
def chat_conversations(request: Request, lab_id: str = Query("lab:demo")) -> list[dict[str, object]]:
    """List conversations visible to the current user only."""

    return _chat_service().list_conversations(_request_user_id(request), lab_id)


@app.post("/chat/conversations", tags=["chat"])
def create_chat_conversation(request_body: CreateConversationRequest, request: Request) -> dict[str, object]:
    service = _chat_service()
    try:
        return service.create_conversation(
            actor_user_id=_request_user_id(request),
            lab_id=request_body.lab_id,
            conversation_type=request_body.conversation_type,
            name=request_body.name,
            description=request_body.description,
            project_id=request_body.project_id,
            member_user_ids=request_body.member_user_ids,
            membership_policy=request_body.membership_policy,
        )
    except (ChatAuthorizationError, ChatValidationError, PermissionError) as exc:
        raise _chat_http_error(exc)


@app.get("/chat/conversations/{conversation_id}", tags=["chat"])
def chat_conversation_detail(conversation_id: str, request: Request) -> dict[str, object]:
    conversation = _chat_service().get_conversation(_request_user_id(request), conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation


@app.put("/chat/conversations/{conversation_id}", tags=["chat"])
def update_chat_conversation(conversation_id: str, request_body: UpdateConversationRequest, request: Request) -> dict[str, object]:
    try:
        return _chat_service().update_conversation(_request_user_id(request), conversation_id, request_body.name, request_body.description)
    except (ChatAuthorizationError, ChatValidationError, PermissionError) as exc:
        raise _chat_http_error(exc)


@app.post("/chat/conversations/{conversation_id}/archive", tags=["chat"])
def archive_chat_conversation(conversation_id: str, request: Request) -> dict[str, object]:
    try:
        return _chat_service().archive_conversation(_request_user_id(request), conversation_id)
    except (ChatAuthorizationError, ChatValidationError, PermissionError) as exc:
        raise _chat_http_error(exc)


@app.get("/chat/conversations/{conversation_id}/members", tags=["chat"])
def chat_conversation_members(conversation_id: str, request: Request) -> list[dict[str, object]]:
    try:
        return _chat_service().list_members(_request_user_id(request), conversation_id)
    except (ChatAuthorizationError, ChatValidationError, PermissionError) as exc:
        raise _chat_http_error(exc)


@app.post("/chat/conversations/{conversation_id}/members", tags=["chat"])
def add_chat_conversation_member(conversation_id: str, request_body: AddConversationMemberRequest, request: Request) -> dict[str, object]:
    try:
        return _chat_service().add_member(_request_user_id(request), conversation_id, request_body.user_id, request_body.member_role)
    except (ChatAuthorizationError, ChatValidationError, PermissionError) as exc:
        raise _chat_http_error(exc)


@app.delete("/chat/conversations/{conversation_id}/members/{user_id}", tags=["chat"])
def remove_chat_conversation_member(conversation_id: str, user_id: str, request: Request) -> dict[str, object]:
    try:
        return _chat_service().remove_member(_request_user_id(request), conversation_id, user_id)
    except (ChatAuthorizationError, ChatValidationError, PermissionError) as exc:
        raise _chat_http_error(exc)


@app.post("/chat/conversations/{conversation_id}/leave", tags=["chat"])
def leave_chat_conversation(conversation_id: str, request: Request) -> dict[str, object]:
    try:
        return _chat_service().remove_member(_request_user_id(request), conversation_id, _request_user_id(request))
    except (ChatAuthorizationError, ChatValidationError, PermissionError) as exc:
        raise _chat_http_error(exc)


@app.put("/chat/conversations/{conversation_id}/members/{user_id}/role", tags=["chat"])
def update_chat_member_role(
    conversation_id: str,
    user_id: str,
    request_body: UpdateConversationMemberRoleRequest,
    request: Request,
) -> dict[str, object]:
    try:
        return _chat_service().set_member_role(_request_user_id(request), conversation_id, user_id, request_body.member_role)
    except (ChatAuthorizationError, ChatValidationError, PermissionError) as exc:
        raise _chat_http_error(exc)


@app.get("/chat/conversations/{conversation_id}/messages", tags=["chat"])
def chat_messages(
    conversation_id: str,
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None),
) -> dict[str, object]:
    try:
        return _chat_service().list_messages(_request_user_id(request), conversation_id, limit, cursor)
    except (ChatAuthorizationError, ChatValidationError, PermissionError) as exc:
        raise _chat_http_error(exc)


@app.post("/chat/conversations/{conversation_id}/messages", tags=["chat"])
def send_chat_message(conversation_id: str, request_body: SendMessageRequest, request: Request) -> dict[str, object]:
    try:
        user_id = _request_user_id(request)
        message = _chat_service().send_message(
            sender_user_id=user_id,
            conversation_id=conversation_id,
            body=request_body.body,
            reply_to_message_id=request_body.reply_to_message_id,
            attachments=list(request_body.attachments),
        )
        try:
            _research_object_service().sync_text_references(
                user_id=user_id,
                source_object_id=str(message["message_id"]),
                source_object_type="Chat Message",
                text=request_body.body,
            )
        except Exception:
            logger.debug("Chat object reference sync failed.", exc_info=True)
        return message
    except (ChatAuthorizationError, ChatValidationError, PermissionError) as exc:
        raise _chat_http_error(exc)


@app.put("/chat/messages/{message_id}", tags=["chat"])
def edit_chat_message(message_id: str, request_body: UpdateMessageRequest, request: Request) -> dict[str, object]:
    try:
        return _chat_service().edit_message(_request_user_id(request), message_id, request_body.body)
    except (ChatAuthorizationError, ChatValidationError, PermissionError) as exc:
        raise _chat_http_error(exc)


@app.delete("/chat/messages/{message_id}", tags=["chat"])
def delete_chat_message(message_id: str, request: Request) -> dict[str, object]:
    try:
        return _chat_service().delete_message(_request_user_id(request), message_id)
    except (ChatAuthorizationError, ChatValidationError, PermissionError) as exc:
        raise _chat_http_error(exc)


@app.post("/chat/messages/{message_id}/read", tags=["chat"])
def read_chat_message(message_id: str, request: Request) -> dict[str, object]:
    try:
        return _chat_service().mark_read(_request_user_id(request), message_id)
    except (ChatAuthorizationError, ChatValidationError, PermissionError) as exc:
        raise _chat_http_error(exc)


@app.get("/chat/unread", tags=["chat"])
def chat_unread(request: Request, lab_id: str = Query("lab:demo")) -> dict[str, object]:
    return _chat_service().unread_counts(_request_user_id(request), lab_id)


@app.get("/chat/search", tags=["chat"])
def chat_search(request: Request, q: str = Query(...), lab_id: str = Query("lab:demo")) -> dict[str, object]:
    return _chat_service().search(_request_user_id(request), q, lab_id)


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


@app.post("/workspaces", response_model=WorkspaceResponse, tags=["workspaces"])
def create_workspace(request: CreateWorkspaceRequest) -> WorkspaceResponse:
    """Create a lab workspace and add the current user as admin."""

    current = _require_admin()
    store = SQLiteStore(settings=settings)
    requested_id = request.workspace_id.strip() if request.workspace_id else ""
    workspace_id = requested_id or f"workspace:{uuid.uuid4().hex[:16]}"
    if store.get_workspace(workspace_id) is not None:
        raise HTTPException(status_code=409, detail=f"Workspace already exists: {workspace_id}")
    workspace = store.upsert_workspace(
        workspace_id=workspace_id,
        name=request.name.strip(),
        institution=request.institution.strip() if request.institution else None,
        description=request.description.strip() or None,
        owner_user_id=str(current["user_id"]),
        created_by=str(current["user_id"]),
        default_role=request.default_role,
        settings=dict(request.settings),
    )
    store.upsert_workspace_membership(workspace_id, str(current["user_id"]), "admin")
    return WorkspaceResponse(**workspace_with_membership(store, workspace, str(current["user_id"])))


@app.get("/workspaces/current", response_model=WorkspaceResponse, tags=["workspaces"])
def get_current_lab_workspace() -> WorkspaceResponse:
    """Return the active lab workspace for the current user."""

    store = SQLiteStore(settings=settings)
    workspace = ActiveWorkspaceService(settings, store).get_current_workspace()
    return WorkspaceResponse(**workspace)


@app.get("/workspaces/{workspace_id}/members", tags=["workspaces"])
def workspace_members(workspace_id: str) -> list[dict[str, object]]:
    """Return members of one lab workspace."""

    _require_admin()
    store = SQLiteStore(settings=settings)
    if store.get_workspace(workspace_id) is None:
        raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_id}")
    return store.list_workspace_memberships(workspace_id)


@app.post("/workspaces/{workspace_id}/members", tags=["workspaces"])
def add_workspace_member(workspace_id: str, request: AddWorkspaceMemberRequest) -> dict[str, object]:
    """Add or update a user's workspace membership."""

    _require_admin()
    store = SQLiteStore(settings=settings)
    if store.get_workspace(workspace_id) is None:
        raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_id}")
    if store.get_user(request.user_id) is None:
        raise HTTPException(status_code=404, detail=f"User not found: {request.user_id}")
    store.upsert_workspace_membership(workspace_id, request.user_id, request.role)
    member = store.workspace_member(workspace_id, request.user_id)
    assert member is not None
    return member


@app.post("/workspaces/current", response_model=WorkspaceResponse, tags=["workspaces"])
def set_current_lab_workspace(request: SetCurrentWorkspaceRequest) -> WorkspaceResponse:
    """Set the active lab workspace for the current user."""

    store = SQLiteStore(settings=settings)
    try:
        workspace = ActiveWorkspaceService(settings, store).set_current_workspace(request.workspace_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WorkspaceResponse(**workspace)


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
            name=request.name.strip() or "ResearchOS Demo Lab",
            institution=request.institution.strip() or None,
            description=request.description.strip() or None,
            owner_user_id=str(current["user_id"]),
            created_by=str(current["user_id"]),
            default_role=str(workspace.get("default_role") or "researcher"),
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
        workspace_id = _current_workspace_id()
        documents = sync_onenote_pages()
        result = ingest_documents(documents=documents, provider="onenote", workspace_id=workspace_id)
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
        result = ingest_markdown_folder(resolved_request.folder_path, workspace_id=_current_workspace_id())
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
        result = ingest_literature(workspace_id=_current_workspace_id())
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
    result = ingest_markdown_folder(sample_path, workspace_id=_current_workspace_id())
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
def documents(workspace_id: str | None = Query(default=None)) -> list[DocumentSummaryResponse]:
    """List locally ingested research documents."""

    store = SQLiteStore(settings=settings)
    resolved_workspace_id = _current_workspace_id(workspace_id)
    return [DocumentSummaryResponse(**document) for document in store.list_documents(workspace_id=resolved_workspace_id)]


@app.get("/documents/{document_id}", response_model=DocumentDetailResponse, tags=["documents"])
def document_detail(document_id: str) -> DocumentDetailResponse:
    """Return one locally ingested research document."""

    store = SQLiteStore(settings=settings)
    document = store.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")

    return DocumentDetailResponse(**document)


@app.get("/papers", response_model=list[PaperSummaryResponse], tags=["literature"])
def papers(workspace_id: str | None = Query(default=None)) -> list[PaperSummaryResponse]:
    """List locally ingested literature papers."""

    store = SQLiteStore(settings=settings)
    resolved_workspace_id = _current_workspace_id(workspace_id)
    paper_summaries = []
    for document in store.list_documents(workspace_id=resolved_workspace_id):
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
def sessions(workspace_id: str | None = Query(default=None)) -> list[SessionResponse]:
    """List live and completed experiment sessions."""

    store = SQLiteStore(settings=settings)
    resolved_workspace_id = _current_workspace_id(workspace_id)
    return [SessionResponse(**session) for session in store.list_sessions(workspace_id=resolved_workspace_id)]


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


@app.get("/voice/speech-providers", tags=["voice"])
def voice_speech_providers() -> dict[str, object]:
    """Return current and planned speech providers for the voice assistant."""

    return {
        "active_provider": "placeholder",
        "cloud_speech_required": False,
        "providers": supported_speech_providers(),
        "confirmation_required": True,
    }


@app.post("/voice/draft", tags=["voice"])
def voice_draft(request: VoiceDraftRequest) -> dict[str, object]:
    """Parse a transcript into a reviewable command without saving anything."""

    transcript = request.transcript.strip() if request.transcript else ""
    audio_reference = request.audio_reference.strip() if request.audio_reference else None
    if not transcript and not audio_reference:
        raise HTTPException(status_code=400, detail="Voice draft requires a transcript or audio reference placeholder.")
    return draft_voice_command(
        transcript=transcript,
        audio_reference=audio_reference,
        session_id=request.session_id,
        experiment_id=request.experiment_id,
    )


@app.post("/voice/confirm", tags=["voice"])
def voice_confirm(request: VoiceConfirmRequest) -> dict[str, object]:
    """Commit a confirmed voice command to session, timeline, draft, and workflow records."""

    transcript = request.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="Confirmed voice transcript must not be empty.")

    store = SQLiteStore(settings=settings)
    session_id = request.session_id.strip() if request.session_id else None
    experiment_id = request.experiment_id.strip() if request.experiment_id else None
    parsed_fields = dict(request.parsed_fields)
    if not experiment_id and isinstance(parsed_fields.get("experiment_id"), str):
        experiment_id = str(parsed_fields["experiment_id"]).strip() or None

    session_payload: dict[str, object] | None = None
    ended_session_payload: dict[str, object] | None = None
    event_payload: dict[str, object] | None = None
    draft_payload: dict[str, object] | None = None
    workflow_payload: dict[str, object] | None = None

    if request.command_type in {"start_session", "start_experiment"} and not session_id:
        session = start_session(SessionStartRequest(experiment_id=experiment_id, notes=transcript)).model_dump()
        session_id = str(session["session_id"])
        session_payload = session
    elif request.command_type == "end_session":
        session_id = session_id or _active_session_id(store)
        if session_id is None:
            raise HTTPException(status_code=400, detail="No active session is available to end.")
        ended_session_payload = end_session(session_id, SessionEndRequest(notes=transcript)).model_dump()
    else:
        session_id = session_id or _active_session_id(store)
        if session_id is None:
            raise HTTPException(status_code=400, detail="No active session is available. Start a session before confirming voice notes.")

    if session_id is not None:
        event_request = session_event_from_voice_command(request.command_type, transcript, parsed_fields)
        event = append_session_event(
            session_id,
            SessionEventAppendRequest(
                event_type=event_request["event_type"],  # type: ignore[arg-type]
                title=str(event_request["title"]),
                content=str(event_request["content"]),
                metadata=dict(event_request["metadata"]),
            ),
        )
        event_payload = event.model_dump()
        session_record = store.get_session(session_id)
        if not experiment_id and session_record is not None:
            experiment_id = str(session_record.get("experiment_id") or "") or None

    if request.create_notebook_draft:
        user = _current_user_payload()
        workspace = user.get("current_workspace") if isinstance(user.get("current_workspace"), dict) else {}
        title = f"Voice {request.command_type.replace('_', ' ').title()}"
        draft = store.save_pending_entry(
            title=title,
            experiment_id=experiment_id,
            template="voice_assistant",
            structured={
                "voice_session_id": request.voice_session_id,
                "command_type": request.command_type,
                "transcript": transcript,
                "parsed_fields": parsed_fields,
                "requires_confirmation_before_commit": True,
            },
            markdown=voice_markdown_entry(request.command_type, transcript, parsed_fields),
            status="draft",
            owner_user_id=str(user.get("user_id")),
            created_by=str(user.get("user_id")),
            workspace_id=str(workspace.get("workspace_id") or ""),
        )
        draft_payload = draft
        _publish_event(
            EventType.DRAFT_CREATED,
            "voice_assistant",
            {"entry_id": draft.get("id"), "session_id": session_id, "experiment_id": experiment_id},
        )

    workflow_payload = _add_voice_workflow_note(store, experiment_id, request.command_type, transcript, session_id)

    return {
        "committed": True,
        "requires_confirmation": False,
        "voice_session_id": request.voice_session_id,
        "command_type": request.command_type,
        "session_id": session_id,
        "session": session_payload,
        "ended_session": ended_session_payload,
        "session_event": event_payload,
        "timeline_updated": event_payload is not None,
        "notebook_draft": draft_payload,
        "workflow_update": workflow_payload,
        "message": "Confirmed voice command saved. The original transcript was preserved unchanged.",
    }


def _active_session_id(store: SQLiteStore) -> str | None:
    """Return the current workspace's active session ID, if one exists."""

    active = next((session for session in store.list_sessions(workspace_id=_current_workspace_id()) if session.get("status") == "active"), None)
    return str(active["session_id"]) if active else None


def _add_voice_workflow_note(
    store: SQLiteStore,
    experiment_reference: str | None,
    command_type: str,
    transcript: str,
    session_id: str | None,
) -> dict[str, object]:
    """Attach confirmed voice context to the experiment workflow when possible."""

    if not experiment_reference:
        return {"updated": False, "message": "No experiment reference was available for workflow update."}
    experiment = store.find_experiment_by_reference(experiment_reference)
    if experiment is None:
        return {"updated": False, "message": f"No extracted experiment matched {experiment_reference}; workflow note was not created."}
    workflow = WorkflowEngine(store).workflow_for_experiment(experiment)
    updated = WorkflowEngine(store).add_note(
        str(workflow["workflow_id"]),
        f"Voice {command_type.replace('_', ' ')}: {transcript}",
        actor="VoiceAssistant",
        metadata={"session_id": session_id, "command_type": command_type, "source": "voice_assistant"},
    )
    _publish_event(
        EventType.WORKFLOW_NOTE_ADDED,
        "voice_assistant",
        {"workflow_id": updated.get("workflow_id"), "experiment_id": experiment.get("id"), "session_id": session_id},
    )
    return {
        "updated": True,
        "workflow_id": updated.get("workflow_id"),
        "current_stage": updated.get("current_stage"),
    }


@app.get("/entries", response_model=list[PendingEntrySummaryResponse], tags=["entries"])
def pending_entries(workspace_id: str | None = Query(default=None)) -> list[PendingEntrySummaryResponse]:
    """List locally saved pending notebook-entry drafts."""

    store = SQLiteStore(settings=settings)
    resolved_workspace_id = _current_workspace_id(workspace_id)
    return [PendingEntrySummaryResponse(**entry) for entry in store.list_pending_entries(workspace_id=resolved_workspace_id)]


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


@app.post("/evidence/query", tags=["evidence"])
def evidence_query(request: EvidenceQueryRequest) -> dict[str, object]:
    """Synthesize observed, supporting, contradictory, and missing evidence."""

    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Evidence question must not be empty.")
    try:
        return EvidenceEngine(settings=settings, knowledge_graph=knowledge_graph_service).query(question).as_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


def _mobile_route(path: str) -> str:
    return f"/mobile{path}"


def _compact_provenance(source: str, provider: str = "ResearchOS", **extra: object) -> dict[str, object]:
    return {"source": source, "provider": provider, **{key: value for key, value in extra.items() if value is not None}}


def _mobile_experiment_card(store: SQLiteStore, experiment: dict[str, object]) -> dict[str, object]:
    workflow = WorkflowEngine(store).workflow_for_experiment(experiment)
    linked_assets = store.list_assets_for_experiment(experiment)
    return {
        "id": experiment.get("id"),
        "title": experiment.get("title") or experiment.get("experiment_id") or experiment.get("id"),
        "human_experiment_id": experiment.get("experiment_id"),
        "date": experiment.get("date"),
        "workflow_stage": workflow.get("current_stage") or "Planning",
        "key_compounds": list(experiment.get("compounds") or [])[:4],
        "key_markers": list(experiment.get("markers") or [])[:4],
        "status": "needs_statistics" if not any(_asset_has_statistics(asset) for asset in linked_assets) else "has_statistics",
        "last_activity": experiment.get("date") or experiment.get("extracted_at"),
        "route": _mobile_route(f"/experiments/{experiment.get('id')}"),
        "icon": "experiment",
        "type_label": "Experiment",
    }


def _asset_has_statistics(asset: dict[str, object]) -> bool:
    """Return whether an asset carries parsed quantitative/statistical metadata."""

    metadata = asset.get("metadata")
    if not isinstance(metadata, dict):
        return False
    return bool(metadata.get("statistics") or metadata.get("statistics_summary") or metadata.get("statistical_results"))


def _mobile_asset_card(asset: dict[str, object]) -> dict[str, object]:
    return {
        "id": asset.get("asset_id"),
        "title": asset.get("title") or asset.get("filename"),
        "subtitle": f"{asset.get('provider') or 'local'} · {asset.get('asset_type') or 'asset'}",
        "type": asset.get("asset_type") or "asset",
        "route": f"#/assets/{asset.get('asset_id')}",
        "provenance": _compact_provenance("asset", str(asset.get("provider") or "local"), asset_id=asset.get("asset_id")),
    }


def _mobile_session_card(session: dict[str, object]) -> dict[str, object]:
    return {
        "session_id": session.get("session_id"),
        "experiment_id": session.get("experiment_id"),
        "status": session.get("status"),
        "title": session.get("experiment_id") or "Experiment session",
        "subtitle": session.get("notes") or session.get("start_time"),
        "start_time": session.get("start_time"),
        "end_time": session.get("end_time"),
        "route": _mobile_route(f"/sessions/{session.get('session_id')}"),
    }


def _create_experiment_from_wizard(request: NewExperimentWizardRequest, *, mobile: bool) -> dict[str, object]:
    """Create experiment planning objects and return a UI-ready payload."""

    if not request.title.strip():
        raise HTTPException(status_code=400, detail="Experiment title is required.")
    if not request.experiment_id.strip():
        raise HTTPException(status_code=400, detail="Experiment ID is required.")

    store = SQLiteStore(settings=settings)
    if store.find_experiment_by_reference(request.experiment_id.strip()) is not None:
        raise HTTPException(status_code=409, detail=f"Experiment ID already exists: {request.experiment_id.strip()}")

    user = _current_user_payload()
    workspace = user.get("current_workspace") if isinstance(user.get("current_workspace"), dict) else {}
    result = ExperimentWizardService(store).create(
        _wizard_payload(request),
        owner_user_id=str(user.get("user_id") or ""),
        created_by=str(user.get("user_id") or ""),
        workspace_id=str(workspace.get("workspace_id") or ""),
    )
    experiment = result["experiment"] if isinstance(result.get("experiment"), dict) else {}
    experiment_id = str(experiment.get("id") or request.experiment_id)
    _publish_event(
        EventType.EXPERIMENT_EXTRACTED,
        "experiment_wizard",
        {
            "experiment_id": experiment_id,
            "human_experiment_id": request.experiment_id,
            "source_provider": "wizard",
        },
    )
    if result.get("pending_entry"):
        _publish_event(
            EventType.DRAFT_CREATED,
            "experiment_wizard",
            {
                "entry_id": result["pending_entry"].get("id") if isinstance(result["pending_entry"], dict) else None,
                "experiment_id": request.experiment_id,
            },
        )
    if result.get("session"):
        _publish_event(
            EventType.SESSION_STARTED,
            "experiment_wizard",
            {
                "session_id": result["session"].get("session_id") if isinstance(result["session"], dict) else None,
                "experiment_id": request.experiment_id,
            },
        )

    response: dict[str, object] = {
        "experiment": _mobile_experiment_card(store, experiment) if mobile and experiment else experiment,
        "workflow": result.get("workflow") or {},
        "workspace_route": _mobile_route(f"/experiments/{experiment_id}/workspace") if mobile else f"/experiments/{experiment_id}/workspace",
        "document": result.get("document") or {},
        "pending_entry": result.get("pending_entry"),
        "session": _mobile_session_card(result["session"]) if mobile and isinstance(result.get("session"), dict) else result.get("session"),
        "notebook_draft": result.get("markdown") or "",
        "copilot": result.get("copilot") or {},
        "onenote": {
            "create_notebook_draft_available": True,
            "save_to_onenote_enabled": False,
            "message": "Save to OneNote is disabled until OneNote write-back is approved.",
        },
        "message": result.get("message") or "Experiment created.",
    }
    return response


def _save_resource_request(request: ResourceRequest, resource_id: str | None = None) -> dict[str, object]:
    """Persist a resource request with current user/workspace metadata."""

    if not request.name.strip():
        raise HTTPException(status_code=400, detail="Resource name is required.")
    store = SQLiteStore(settings=settings)
    user = _current_user_payload()
    workspace = user.get("current_workspace") if isinstance(user.get("current_workspace"), dict) else {}
    resource = store.save_resource(
        resource_id=resource_id,
        resource_type=request.resource_type,
        name=request.name.strip(),
        aliases=request.aliases,
        vendor=request.vendor,
        catalog_number=request.catalog_number,
        lot_number=request.lot_number,
        rrid=request.rrid,
        storage_location=request.storage_location,
        concentration=request.concentration,
        units=request.units,
        expiration=request.expiration,
        notes=request.notes,
        metadata=dict(request.metadata),
        owner_user_id=str(user.get("user_id") or ""),
        created_by=str(user.get("user_id") or ""),
        workspace_id=str(workspace.get("workspace_id") or ""),
    )
    _publish_event(
        EventType.KNOWLEDGE_GRAPH_UPDATED,
        "resources",
        {"resource_id": resource.get("resource_id"), "resource_type": resource.get("resource_type")},
    )
    return resource


def _current_user_workspace_metadata() -> tuple[dict[str, object], dict[str, object]]:
    """Return current user and workspace metadata for ownership scaffolding."""

    user = _current_user_payload()
    workspace = user.get("current_workspace") if isinstance(user.get("current_workspace"), dict) else {}
    return user, workspace


def _save_inventory_request(request: InventoryItemRequest, item_id: str | None = None) -> dict[str, object]:
    """Persist an inventory request."""

    if not request.name.strip():
        raise HTTPException(status_code=400, detail="Inventory item name is required.")
    store = SQLiteStore(settings=settings)
    if request.linked_resource_id and store.get_resource(request.linked_resource_id) is None:
        raise HTTPException(status_code=404, detail=f"Linked resource not found: {request.linked_resource_id}")
    user, workspace = _current_user_workspace_metadata()
    return store.save_inventory_item(
        item_id=item_id,
        name=request.name.strip(),
        category=request.category,
        vendor=request.vendor,
        catalog_number=request.catalog_number,
        lot_number=request.lot_number,
        rrid=request.rrid,
        price=request.price,
        unit=request.unit,
        storage_location=request.storage_location,
        quantity=request.quantity,
        reorder_threshold=request.reorder_threshold,
        expiration_date=request.expiration_date,
        barcode=request.barcode,
        qr_code=request.qr_code,
        internal_label=request.internal_label,
        freezer_box=request.freezer_box,
        freezer_position=request.freezer_position,
        shelf=request.shelf,
        room=request.room,
        notes=request.notes,
        linked_resource_id=request.linked_resource_id,
        owner_user_id=str(user.get("user_id") or ""),
        created_by=str(user.get("user_id") or ""),
        workspace_id=str(workspace.get("workspace_id") or ""),
    )


def _save_purchase_request(request: PurchaseRecordRequest, purchase_id: str | None = None) -> dict[str, object]:
    """Persist a completed/manual purchase record."""

    if not request.item_name.strip():
        raise HTTPException(status_code=400, detail="Purchase item name is required.")
    store = SQLiteStore(settings=settings)
    user, workspace = _current_user_workspace_metadata()
    return store.save_purchase_record(
        purchase_id=purchase_id,
        item_name=request.item_name.strip(),
        vendor=request.vendor,
        catalog_number=request.catalog_number,
        purchase_date=request.purchase_date,
        cost=request.cost,
        quantity=request.quantity,
        grant_or_funding_source=request.grant_or_funding_source,
        purchaser=request.purchaser,
        oracle_po_number=request.oracle_po_number,
        invoice_number=request.invoice_number,
        status=request.status,
        notes=request.notes,
        owner_user_id=str(user.get("user_id") or ""),
        created_by=str(user.get("user_id") or ""),
        workspace_id=str(workspace.get("workspace_id") or ""),
    )


def _save_purchase_request_workflow(
    request: PurchaseRequestRequest,
    request_id: str | None = None,
) -> dict[str, object]:
    """Persist a pre-Oracle purchase request workflow record."""

    if not request.item_name.strip():
        raise HTTPException(status_code=400, detail="Purchase request item name is required.")
    status = (request.status or "draft").strip().lower()
    if status not in PURCHASE_REQUEST_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid purchase request status: {request.status}")
    store = SQLiteStore(settings=settings)
    if request.linked_inventory_item_id and store.get_inventory_item(request.linked_inventory_item_id) is None:
        raise HTTPException(status_code=404, detail=f"Linked inventory item not found: {request.linked_inventory_item_id}")
    user, workspace = _current_user_workspace_metadata()
    return store.save_purchase_request(
        request_id=request_id,
        item_name=request.item_name.strip(),
        vendor=request.vendor,
        catalog_number=request.catalog_number,
        quantity_requested=request.quantity_requested,
        estimated_cost=request.estimated_cost,
        grant_or_funding_source=request.grant_or_funding_source,
        requested_by=request.requested_by or str(user.get("display_name") or user.get("email") or ""),
        request_date=request.request_date or datetime.now(timezone.utc).date().isoformat(),
        status=status,
        notes=request.notes,
        linked_inventory_item_id=request.linked_inventory_item_id,
        owner_user_id=str(user.get("user_id") or ""),
        created_by=str(user.get("user_id") or ""),
        workspace_id=str(workspace.get("workspace_id") or ""),
    )


def _purchase_request_with_status(request_id: str, status: str) -> dict[str, object]:
    """Move a purchase request to one status."""

    store = SQLiteStore(settings=settings)
    record = store.get_purchase_request(request_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Purchase request not found: {request_id}")
    payload = PurchaseRequestRequest(
        item_name=str(record.get("item_name") or ""),
        vendor=record.get("vendor"),
        catalog_number=record.get("catalog_number"),
        quantity_requested=record.get("quantity_requested"),
        estimated_cost=record.get("estimated_cost"),
        grant_or_funding_source=record.get("grant_or_funding_source"),
        requested_by=record.get("requested_by"),
        request_date=record.get("request_date"),
        status=status,
        notes=record.get("notes"),
        linked_inventory_item_id=record.get("linked_inventory_item_id"),
    )
    return _save_purchase_request_workflow(payload, request_id=request_id)


def _save_receiving_request(
    request: ReceivingRecordRequest,
    receiving_id: str | None = None,
) -> dict[str, object]:
    """Persist one receiving/intake record."""

    if not request.item_name.strip():
        raise HTTPException(status_code=400, detail="Receiving item name is required.")
    store = SQLiteStore(settings=settings)
    if request.purchase_request_id and store.get_purchase_request(request.purchase_request_id) is None:
        raise HTTPException(status_code=404, detail=f"Purchase request not found: {request.purchase_request_id}")
    linked_purchase = store.get_purchase_record(request.purchase_record_id) if request.purchase_record_id else None
    if request.purchase_record_id and linked_purchase is None:
        raise HTTPException(status_code=404, detail=f"Purchase record not found: {request.purchase_record_id}")
    if request.inventory_item_id and store.get_inventory_item(request.inventory_item_id) is None:
        raise HTTPException(status_code=404, detail=f"Inventory item not found: {request.inventory_item_id}")
    user, workspace = _current_user_workspace_metadata()
    notes = request.notes
    if linked_purchase:
        purchase_context = "Linked purchase record"
        details = [
            f"PO {linked_purchase.get('oracle_po_number')}" if linked_purchase.get("oracle_po_number") else "",
            f"invoice {linked_purchase.get('invoice_number')}" if linked_purchase.get("invoice_number") else "",
            f"grant {linked_purchase.get('grant_or_funding_source')}" if linked_purchase.get("grant_or_funding_source") else "",
        ]
        purchase_context = f"{purchase_context}: {', '.join([item for item in details if item])}."
        notes = f"{notes or ''}\n{purchase_context}".strip()
    saved = store.save_receiving_record(
        receiving_id=receiving_id,
        purchase_request_id=request.purchase_request_id,
        purchase_record_id=request.purchase_record_id,
        inventory_item_id=request.inventory_item_id,
        item_name=request.item_name.strip(),
        vendor=request.vendor,
        catalog_number=request.catalog_number,
        lot_number=request.lot_number,
        quantity_received=request.quantity_received,
        units=request.units,
        received_by=request.received_by or str(user.get("display_name") or user.get("email") or ""),
        received_date=request.received_date or datetime.now(timezone.utc).date().isoformat(),
        expiration_date=request.expiration_date,
        storage_location=request.storage_location,
        barcode_or_label=request.barcode_or_label,
        notes=notes,
        owner_user_id=str(user.get("user_id") or ""),
        created_by=str(user.get("user_id") or ""),
        workspace_id=str(workspace.get("workspace_id") or ""),
    )
    _publish_event(EventType.PROVIDER_SYNCED, "inventory", {"event": "receiving_record_saved", "receiving_id": saved.get("receiving_id")})
    return saved


def _receiving_from_purchase_request(request_record: dict[str, object]) -> dict[str, object]:
    """Create a receiving record from a received purchase request."""

    payload = ReceivingRecordRequest(
        purchase_request_id=str(request_record.get("request_id") or ""),
        inventory_item_id=request_record.get("linked_inventory_item_id"),
        item_name=str(request_record.get("item_name") or ""),
        vendor=request_record.get("vendor"),
        catalog_number=request_record.get("catalog_number"),
        quantity_received=request_record.get("quantity_requested"),
        received_by=request_record.get("requested_by"),
        received_date=datetime.now(timezone.utc).date().isoformat(),
        notes=f"Created when purchase request {request_record.get('request_id')} was marked received.",
    )
    return _save_receiving_request(payload)


def _intake_receiving_record(
    receiving_id: str,
    update_existing: bool = True,
) -> dict[str, object]:
    """Create or update inventory from a receiving record."""

    store = SQLiteStore(settings=settings)
    record = store.get_receiving_record(receiving_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Receiving record not found: {receiving_id}")
    inventory_item_id = record.get("inventory_item_id")
    quantity = float(record.get("quantity_received") or 0)
    inventory_item: dict[str, object] | None = None
    if inventory_item_id and update_existing:
        inventory_item = store.update_inventory_quantity(str(inventory_item_id), quantity)
        if inventory_item is None:
            raise HTTPException(status_code=404, detail=f"Inventory item not found: {inventory_item_id}")
    else:
        inventory_item = store.save_inventory_item(
            name=str(record.get("item_name") or ""),
            category="received",
            vendor=record.get("vendor"),
            catalog_number=record.get("catalog_number"),
            lot_number=record.get("lot_number"),
            unit=record.get("units"),
            storage_location=record.get("storage_location"),
            quantity=quantity if record.get("quantity_received") is not None else None,
            expiration_date=record.get("expiration_date"),
            barcode=record.get("barcode_or_label"),
            qr_code=record.get("barcode_or_label"),
            internal_label=record.get("barcode_or_label"),
            notes=f"Created from receiving record {receiving_id}. {record.get('notes') or ''}".strip(),
            workspace_id=record.get("workspace_id"),
            owner_user_id=record.get("owner_user_id"),
            created_by=record.get("created_by"),
        )
    updated_record = store.save_receiving_record(
        receiving_id=receiving_id,
        purchase_request_id=record.get("purchase_request_id"),
        purchase_record_id=record.get("purchase_record_id"),
        inventory_item_id=str(inventory_item.get("item_id")),
        item_name=str(record.get("item_name") or ""),
        vendor=record.get("vendor"),
        catalog_number=record.get("catalog_number"),
        lot_number=record.get("lot_number"),
        quantity_received=record.get("quantity_received"),
        units=record.get("units"),
        received_by=record.get("received_by"),
        received_date=record.get("received_date"),
        expiration_date=record.get("expiration_date"),
        storage_location=record.get("storage_location"),
        barcode_or_label=record.get("barcode_or_label"),
        notes=record.get("notes"),
        owner_user_id=record.get("owner_user_id"),
        created_by=record.get("created_by"),
        workspace_id=record.get("workspace_id"),
    )
    _publish_event(
        EventType.PROVIDER_SYNCED,
        "inventory",
        {"event": "inventory_intake", "receiving_id": receiving_id, "inventory_item_id": inventory_item.get("item_id")},
    )
    return {"receiving": updated_record, "inventory_item": inventory_item}


def _save_experiment_design_request(
    request: ExperimentDesignRequest,
    design_id: str | None = None,
) -> dict[str, object]:
    """Persist an experiment design with validation."""

    if not request.title.strip():
        raise HTTPException(status_code=400, detail="Experiment design title is required.")
    status = request.status.strip().lower()
    if status not in DESIGN_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid experiment design status: {request.status}")
    store = SQLiteStore(settings=settings)
    if request.linked_experiment_id and store.find_experiment_by_reference(request.linked_experiment_id) is None:
        raise HTTPException(status_code=404, detail=f"Linked experiment not found: {request.linked_experiment_id}")
    user, workspace = _current_user_workspace_metadata()
    return store.save_experiment_design(
        design_id=design_id,
        title=request.title.strip(),
        experiment_type=request.experiment_type,
        cell_line_or_model=request.cell_line_or_model,
        reporters=request.reporters,
        description=request.description,
        start_date=request.start_date,
        created_by=request.created_by or str(user.get("display_name") or user.get("email") or ""),
        linked_experiment_id=request.linked_experiment_id,
        status=status,
        owner_user_id=str(user.get("user_id") or ""),
        workspace_id=str(workspace.get("workspace_id") or ""),
    )


def _design_or_404(store: SQLiteStore, design_id: str) -> dict[str, object]:
    """Return a design or raise a FastAPI 404."""

    design = store.get_experiment_design(design_id)
    if design is None:
        raise HTTPException(status_code=404, detail=f"Experiment design not found: {design_id}")
    return design


def _save_design_condition(store: SQLiteStore, design_id: str, request: DesignConditionRequest) -> dict[str, object]:
    """Persist one design condition."""

    _design_or_404(store, design_id)
    if not request.condition_name.strip():
        raise HTTPException(status_code=400, detail="Condition name is required.")
    return store.save_design_condition(
        design_id=design_id,
        condition_name=request.condition_name.strip(),
        treatment=request.treatment,
        dose=request.dose,
        units=request.units,
        start_day=request.start_day,
        end_day=request.end_day,
        notes=request.notes,
        replicate_count=request.replicate_count,
        sample_count=request.sample_count,
    )


def _save_design_event(store: SQLiteStore, design_id: str, request: DesignEventRequest) -> dict[str, object]:
    """Persist one design event."""

    _design_or_404(store, design_id)
    event_type = request.event_type.strip().lower()
    if event_type not in EVENT_TYPES:
        event_type = "custom"
    if request.condition_id and store.get_design_condition(request.condition_id) is None:
        raise HTTPException(status_code=404, detail=f"Design condition not found: {request.condition_id}")
    return store.save_design_event(
        design_id=design_id,
        condition_id=request.condition_id,
        day=request.day,
        event_type=event_type,
        title=request.title,
        description=request.description,
        required=request.required,
        alert_enabled=request.alert_enabled,
        alert_offset_days=request.alert_offset_days,
        reminder_enabled=request.reminder_enabled,
        reminder_offset_days=request.reminder_offset_days,
        reminder_status=request.reminder_status,
        due_date=request.due_date,
        completed=request.completed,
        completed_at=request.completed_at,
        dismissed_at=request.dismissed_at,
    )


def _builtin_design_templates() -> list[dict[str, object]]:
    """Return built-in reusable experiment design templates."""

    return [dict(template) for template in BUILTIN_EXPERIMENT_DESIGN_TEMPLATES]


def _experiment_design_template_or_404(store: SQLiteStore, template_id: str) -> dict[str, object]:
    """Return a built-in or saved design template."""

    for template in _builtin_design_templates():
        if template.get("template_id") == template_id:
            return template
    template = store.get_experiment_design_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Experiment design template not found: {template_id}")
    return template


def _save_current_design_as_template(store: SQLiteStore, design: dict[str, object], name: str | None = None) -> dict[str, object]:
    """Convert a concrete design into a reusable template."""

    user, workspace = _current_user_workspace_metadata()
    return store.save_experiment_design_template(
        name=name or f"{design.get('title') or 'Experiment design'} template",
        description=str(design.get("description") or ""),
        experiment_type=design.get("experiment_type") if isinstance(design.get("experiment_type"), str) else None,
        default_cell_line_or_model=design.get("cell_line_or_model") if isinstance(design.get("cell_line_or_model"), str) else None,
        default_reporters=design.get("reporters") if isinstance(design.get("reporters"), list) else [],
        default_conditions=design.get("conditions") if isinstance(design.get("conditions"), list) else [],
        default_events=design.get("events") if isinstance(design.get("events"), list) else [],
        default_reminders=[
            event for event in design.get("events", [])
            if isinstance(event, dict) and (event.get("reminder_enabled") or event.get("alert_enabled"))
        ] if isinstance(design.get("events"), list) else [],
        tags=["saved design"],
        created_by=str(user.get("display_name") or user.get("email") or ""),
        owner_user_id=str(user.get("user_id") or ""),
        workspace_id=str(workspace.get("workspace_id") or ""),
    )


def _create_design_from_template(template: dict[str, object], request: TemplateCreateDesignRequest) -> ExperimentDesignResponse:
    """Create a concrete experiment design by copying a reusable template."""

    design = create_experiment_design(
        ExperimentDesignRequest(
            title=request.title or str(template.get("name") or "Experiment design"),
            experiment_type=template.get("experiment_type") if isinstance(template.get("experiment_type"), str) else None,
            cell_line_or_model=request.cell_line_or_model
            or (template.get("default_cell_line_or_model") if isinstance(template.get("default_cell_line_or_model"), str) else None),
            reporters=request.reporters if request.reporters is not None else list(template.get("default_reporters") or []),
            description=template.get("description") if isinstance(template.get("description"), str) else None,
            start_date=request.start_date,
            status=request.status,
        )
    )
    store = SQLiteStore(settings=settings)
    condition_by_name: dict[str, dict[str, object]] = {}
    for condition in template.get("default_conditions") or []:
        if not isinstance(condition, dict):
            continue
        saved_condition = _save_design_condition(
            store,
            design.design_id,
            DesignConditionRequest(
                condition_name=str(condition.get("condition_name") or condition.get("name") or "Condition"),
                treatment=condition.get("treatment") if isinstance(condition.get("treatment"), str) else None,
                dose=condition.get("dose") if isinstance(condition.get("dose"), str) else None,
                units=condition.get("units") if isinstance(condition.get("units"), str) else None,
                start_day=condition.get("start_day") if isinstance(condition.get("start_day"), str) else None,
                end_day=condition.get("end_day") if isinstance(condition.get("end_day"), str) else None,
                notes=condition.get("notes") if isinstance(condition.get("notes"), str) else None,
                replicate_count=condition.get("replicate_count") if isinstance(condition.get("replicate_count"), int) else None,
                sample_count=condition.get("sample_count") if isinstance(condition.get("sample_count"), int) else None,
            ),
        )
        condition_by_name[str(saved_condition.get("condition_name"))] = saved_condition
    first_condition = next(iter(condition_by_name.values()), None)
    for event in template.get("default_events") or []:
        if not isinstance(event, dict):
            continue
        condition = condition_by_name.get(str(event.get("condition_name") or "")) or first_condition
        _save_design_event(
            store,
            design.design_id,
            DesignEventRequest(
                condition_id=str(condition.get("condition_id")) if condition else None,
                day=str(event.get("day") or "D0"),
                event_type=str(event.get("event_type") or "custom"),
                title=str(event.get("title") or "Template event"),
                description=event.get("description") if isinstance(event.get("description"), str) else None,
                required=bool(event.get("required", True)),
                alert_enabled=bool(event.get("alert_enabled") or event.get("reminder_enabled")),
                reminder_enabled=bool(event.get("reminder_enabled") or event.get("alert_enabled")),
                reminder_offset_days=int(event.get("reminder_offset_days") or event.get("alert_offset_days") or 0),
            ),
        )
    return ExperimentDesignResponse(**_design_or_404(store, design.design_id))


def _save_plate_layout_request(
    store: SQLiteStore,
    request: PlateLayoutRequest,
    layout_id: str | None = None,
) -> dict[str, object]:
    """Persist a plate/sample layout with design validation."""

    design = _design_or_404(store, request.design_id)
    user, workspace = _current_user_workspace_metadata()
    wells = [well.model_dump() for well in request.wells]
    return store.save_plate_layout(
        layout_id=layout_id,
        design_id=str(design.get("design_id")),
        title=request.title,
        format=request.format,
        rows=request.rows,
        columns=request.columns,
        wells=wells,
        warnings=request.warnings,
        created_by=request.created_by or str(user.get("display_name") or user.get("email") or ""),
        owner_user_id=str(user.get("user_id") or ""),
        workspace_id=str(workspace.get("workspace_id") or ""),
    )


def _save_visual_builder_request(
    store: SQLiteStore,
    request: VisualExperimentBuilderRequest,
    builder_id: str | None = None,
) -> dict[str, object]:
    """Persist a visual experiment builder canvas."""

    if not request.title.strip():
        raise HTTPException(status_code=400, detail="Visual builder title is required.")
    user, workspace = _current_user_workspace_metadata()
    nodes = [node.model_dump() for node in request.nodes]
    connections = [connection.model_dump() for connection in request.connections]
    return store.save_visual_experiment_builder(
        builder_id=builder_id,
        title=request.title.strip(),
        description=request.description,
        nodes=nodes,
        connections=connections,
        generated_design_id=request.generated_design_id,
        generated_plate_layout_id=request.generated_plate_layout_id,
        warnings=request.warnings,
        created_by=request.created_by or str(user.get("display_name") or user.get("email") or ""),
        owner_user_id=str(user.get("user_id") or ""),
        workspace_id=str(workspace.get("workspace_id") or ""),
    )


def _visual_builder_or_404(store: SQLiteStore, builder_id: str) -> dict[str, object]:
    """Return a visual builder or raise 404."""

    builder = store.get_visual_experiment_builder(builder_id)
    if builder is None:
        raise HTTPException(status_code=404, detail=f"Visual experiment builder not found: {builder_id}")
    return builder


def _generate_from_visual_builder(
    store: SQLiteStore,
    builder: dict[str, object],
    request: VisualBuilderGenerateRequest,
) -> dict[str, object]:
    """Compile a visual builder into a concrete design and optional plate layout."""

    compiled = compile_visual_builder(
        builder.get("nodes") if isinstance(builder.get("nodes"), list) else [],
        builder.get("connections") if isinstance(builder.get("connections"), list) else [],
    )
    design = create_experiment_design(
        ExperimentDesignRequest(
            title=request.title or str(compiled.get("title") or builder.get("title") or "Visual experiment design"),
            experiment_type=compiled.get("experiment_type") if isinstance(compiled.get("experiment_type"), str) else "visual_builder",
            cell_line_or_model=compiled.get("cell_line_or_model") if isinstance(compiled.get("cell_line_or_model"), str) else None,
            reporters=compiled.get("reporters") if isinstance(compiled.get("reporters"), list) else [],
            description=f"Generated from visual builder {builder.get('builder_id')}.",
            start_date=request.start_date,
            status=request.status,
        )
    )
    condition_by_name: dict[str, dict[str, object]] = {}
    for condition in compiled.get("conditions", []):
        if not isinstance(condition, dict):
            continue
        saved_condition = _save_design_condition(
            store,
            design.design_id,
            DesignConditionRequest(
                condition_name=str(condition.get("condition_name") or "Condition"),
                treatment=condition.get("treatment") if isinstance(condition.get("treatment"), str) else None,
                dose=condition.get("dose") if isinstance(condition.get("dose"), str) else None,
                units=condition.get("units") if isinstance(condition.get("units"), str) else None,
                start_day=condition.get("start_day") if isinstance(condition.get("start_day"), str) else None,
                end_day=condition.get("end_day") if isinstance(condition.get("end_day"), str) else None,
                notes=condition.get("notes") if isinstance(condition.get("notes"), str) else None,
                replicate_count=condition.get("replicate_count") if isinstance(condition.get("replicate_count"), int) else 1,
                sample_count=condition.get("sample_count") if isinstance(condition.get("sample_count"), int) else 1,
            ),
        )
        condition_by_name[str(saved_condition.get("condition_name"))] = saved_condition
    first_condition = next(iter(condition_by_name.values()), None)
    for event in compiled.get("events", []):
        if not isinstance(event, dict):
            continue
        condition = condition_by_name.get(str(event.get("condition_name") or "")) or first_condition
        _save_design_event(
            store,
            design.design_id,
            DesignEventRequest(
                condition_id=str(condition.get("condition_id")) if condition else None,
                day=str(event.get("day") or "D0"),
                event_type=str(event.get("event_type") or "custom"),
                title=str(event.get("title") or "Visual event"),
                description=event.get("description") if isinstance(event.get("description"), str) else None,
                required=bool(event.get("required", True)),
                alert_enabled=bool(event.get("alert_enabled") or event.get("reminder_enabled")),
                reminder_enabled=bool(event.get("reminder_enabled") or event.get("alert_enabled")),
            ),
        )
    full_design = _design_or_404(store, design.design_id)
    plate_layout = None
    if request.generate_plate_layout:
        generated_layout = generate_plate_layout(
            full_design,
            format_name=request.plate_format,
            randomized=request.randomized_layout,
            balanced=request.balanced_layout,
            grouped_by_condition=not request.randomized_layout,
            title=f"{full_design.get('title')} layout",
        )
        user, workspace = _current_user_workspace_metadata()
        plate_layout = store.save_plate_layout(
            design_id=design.design_id,
            title=str(generated_layout["title"]),
            format=str(generated_layout["format"]),
            rows=int(generated_layout["rows"]),
            columns=int(generated_layout["columns"]),
            wells=generated_layout["wells"],
            warnings=generated_layout["warnings"],
            created_by=str(user.get("display_name") or user.get("email") or ""),
            owner_user_id=str(user.get("user_id") or ""),
            workspace_id=str(workspace.get("workspace_id") or ""),
        )
    updated_builder = store.save_visual_experiment_builder(
        builder_id=str(builder.get("builder_id")),
        title=str(builder.get("title") or ""),
        description=builder.get("description") if isinstance(builder.get("description"), str) else None,
        nodes=builder.get("nodes") if isinstance(builder.get("nodes"), list) else [],
        connections=builder.get("connections") if isinstance(builder.get("connections"), list) else [],
        generated_design_id=design.design_id,
        generated_plate_layout_id=str(plate_layout.get("layout_id")) if plate_layout else None,
        warnings=compiled.get("warnings") if isinstance(compiled.get("warnings"), list) else [],
        created_by=builder.get("created_by") if isinstance(builder.get("created_by"), str) else None,
        owner_user_id=builder.get("owner_user_id") if isinstance(builder.get("owner_user_id"), str) else None,
        workspace_id=builder.get("workspace_id") if isinstance(builder.get("workspace_id"), str) else None,
    )
    return {
        "builder": updated_builder,
        "compiled": compiled,
        "design": _design_or_404(store, design.design_id),
        "plate_layout": plate_layout,
        "timeline": build_design_timeline(_design_or_404(store, design.design_id)),
    }


def _designs_for_reminders(workspace_id: str | None = None) -> list[dict[str, object]]:
    """Return fully-loaded designs for reminder endpoints."""

    store = SQLiteStore(settings=settings)
    designs = [
        store.get_experiment_design(str(design["design_id"]))
        for design in store.list_experiment_designs(workspace_id=_current_workspace_id(workspace_id))
    ]
    return [design for design in designs if design]


def _update_design_reminder_event(event_id: str, status: str) -> dict[str, object]:
    """Mark a design event reminder complete or dismissed."""

    store = SQLiteStore(settings=settings)
    event = store.get_design_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Design event not found: {event_id}")
    now = datetime.now(timezone.utc).isoformat()
    updated = store.save_design_event(
        event_id=event_id,
        design_id=str(event["design_id"]),
        condition_id=event.get("condition_id"),
        day=str(event.get("day") or "D0"),
        event_type=str(event.get("event_type") or "custom"),
        title=str(event.get("title") or "Design event"),
        description=event.get("description"),
        required=bool(event.get("required")),
        alert_enabled=bool(event.get("alert_enabled")),
        alert_offset_days=int(event.get("alert_offset_days") or 0),
        reminder_enabled=bool(event.get("reminder_enabled") or event.get("alert_enabled")),
        reminder_offset_days=int(event.get("reminder_offset_days") if event.get("reminder_offset_days") is not None else event.get("alert_offset_days") or 0),
        reminder_status=status,
        due_date=event.get("due_date"),
        completed=status == "completed",
        completed_at=now if status == "completed" else event.get("completed_at"),
        dismissed_at=now if status == "dismissed" else event.get("dismissed_at"),
    )
    _publish_event(EventType.PROVIDER_SYNCED, "experiment_designs", {"event": f"reminder_{status}", "event_id": event_id, "design_id": event.get("design_id")})
    return updated


def _inventory_item_entry(
    store: SQLiteStore,
    item: dict[str, object],
    *,
    include_lot_numbers: bool = True,
    include_storage_locations: bool = False,
) -> dict[str, object]:
    """Return one inventory item formatted for methods generation."""

    linked_resource = store.get_resource(str(item.get("linked_resource_id"))) if item.get("linked_resource_id") else None
    return reagent_methods_entry(
        item,
        linked_resource,
        include_lot=include_lot_numbers,
        include_storage=include_storage_locations,
    )


def _experiment_reagent_context(
    store: SQLiteStore,
    experiment_id: str,
    workspace_id: str | None = None,
) -> dict[str, object]:
    """Resolve inventory/resources that appear linked to an experiment."""

    experiment = store.find_experiment_by_reference(experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail=f"Experiment not found: {experiment_id}")
    resolved_workspace = _current_workspace_id(workspace_id or str(experiment.get("workspace_id") or "") or None)
    entity_names = {
        str(value).strip().lower()
        for key in ["compounds", "markers", "antibodies", "treatments"]
        for value in (experiment.get(key) or [])
        if str(value).strip()
    }
    for key in ["cell_line", "organoid_batch"]:
        if experiment.get(key):
            entity_names.add(str(experiment[key]).strip().lower())

    resources = store.list_resources(workspace_id=resolved_workspace)
    matching_resources = []
    for resource in resources:
        names = {str(resource.get("name") or "").strip().lower()}
        names.update(str(alias).strip().lower() for alias in resource.get("aliases") or [])
        usages = store.resource_usages(str(resource.get("resource_id")))
        usage_match = any(
            str(usage.get("object_id")) in {str(experiment.get("id")), str(experiment.get("experiment_id"))}
            and str(usage.get("object_type") or "").lower() in {"experiment", "experiments"}
            for usage in usages
        )
        if usage_match or names.intersection(entity_names):
            matching_resources.append(resource)

    resource_ids = {str(resource.get("resource_id")) for resource in matching_resources if resource.get("resource_id")}
    usage_records = store.list_inventory_usage_for_experiment(str(experiment.get("id")), workspace_id=resolved_workspace)
    if experiment.get("experiment_id"):
        usage_records.extend(
            store.list_inventory_usage_for_experiment(str(experiment.get("experiment_id")), workspace_id=resolved_workspace)
        )
    usage_item_ids = {str(usage.get("inventory_item_id")) for usage in usage_records if usage.get("inventory_item_id")}
    inventory = []
    for item in store.list_inventory_items(workspace_id=resolved_workspace):
        item_names = {str(item.get("name") or "").strip().lower(), str(item.get("category") or "").strip().lower()}
        if str(item.get("item_id")) in usage_item_ids:
            inventory.append(item)
        elif item.get("linked_resource_id") and str(item.get("linked_resource_id")) in resource_ids:
            inventory.append(item)
        elif item_names.intersection(entity_names):
            inventory.append(item)

    seen_items: set[str] = set()
    unique_inventory = []
    for item in inventory:
        item_id = str(item.get("item_id"))
        if item_id in seen_items:
            continue
        seen_items.add(item_id)
        unique_inventory.append(item)

    inventory_resource_ids = {str(item.get("linked_resource_id")) for item in unique_inventory if item.get("linked_resource_id")}
    missing_inventory_resources = [
        resource
        for resource in matching_resources
        if str(resource.get("resource_id")) not in inventory_resource_ids
    ]
    warnings = [
        f"No inventory item is linked to resource {resource.get('name') or resource.get('resource_id')}."
        for resource in missing_inventory_resources
    ]
    return {
        "experiment": experiment,
        "inventory_items": unique_inventory,
        "inventory_usage": usage_records,
        "resources": matching_resources,
        "missing_inventory_resources": missing_inventory_resources,
        "warnings": warnings,
    }


def _record_inventory_usage(
    store: SQLiteStore,
    item_id: str,
    experiment_reference: str,
    request: InventoryUsageRequest,
) -> dict[str, object]:
    """Persist inventory usage and update linked local context."""

    item = store.get_inventory_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Inventory item not found: {item_id}")
    experiment = store.find_experiment_by_reference(experiment_reference)
    if experiment is None:
        raise HTTPException(status_code=404, detail=f"Experiment not found: {experiment_reference}")
    user, workspace = _current_user_workspace_metadata()
    used_by = request.used_by or str(user.get("display_name") or user.get("email") or user.get("user_id") or "")
    usage = store.record_inventory_usage(
        inventory_item_id=item_id,
        experiment_id=str(experiment.get("id")),
        session_id=request.session_id,
        protocol_id=request.protocol_id,
        amount_used=request.amount_used,
        units=request.units,
        date_used=request.date_used,
        used_by=used_by,
        purpose=request.purpose,
        notes=request.notes,
        decrement_quantity=request.decrement_quantity,
        workspace_id=str(workspace.get("workspace_id") or experiment.get("workspace_id") or item.get("workspace_id") or ""),
    )
    if item.get("linked_resource_id"):
        store.record_resource_usage(
            resource_id=str(item["linked_resource_id"]),
            object_type="experiment",
            object_id=str(experiment.get("id")),
            usage_type="inventory_used",
            source="inventory_usage",
            metadata={
                "inventory_item_id": item_id,
                "usage_id": usage.get("usage_id"),
                "amount_used": request.amount_used,
                "units": request.units,
                "purpose": request.purpose,
            },
            workspace_id=str(workspace.get("workspace_id") or experiment.get("workspace_id") or item.get("workspace_id") or ""),
        )
    if request.session_id:
        store.append_session_event(
            session_id=request.session_id,
            event_type="reagent_used",
            title=f"Used {item.get('name') or item_id}",
            content=request.notes or request.purpose,
            metadata={
                "inventory_item_id": item_id,
                "usage_id": usage.get("usage_id"),
                "experiment_id": experiment.get("id"),
                "amount_used": request.amount_used,
                "units": request.units,
            },
        )
    return usage


def _mobile_dashboard_card(
    title: str,
    subtitle: str,
    card_type: str,
    priority: int,
    route: str | None = None,
    action: str | None = None,
    provenance: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "title": title,
        "subtitle": subtitle,
        "type": card_type,
        "priority": priority,
        "route": route,
        "action": action,
        "provenance": provenance,
    }


def _mobile_intelligence_card(item: dict[str, object]) -> dict[str, object]:
    """Return a compact, display-ready intelligence card for mobile clients."""

    provenance = item.get("provenance") if isinstance(item.get("provenance"), list) else []
    compact_provenance = []
    for record in provenance[:3]:
        if not isinstance(record, dict):
            continue
        compact_provenance.append(
            {
                "fact": record.get("fact"),
                "source": record.get("source"),
                "provider": record.get("provider"),
                "id": record.get("experiment_id") or record.get("asset_id") or record.get("document_id") or record.get("resource_id") or record.get("session_id"),
            }
        )
    return {
        "item_id": item.get("item_id"),
        "title": item.get("title"),
        "subtitle": item.get("summary"),
        "type": item.get("item_type"),
        "priority": item.get("priority_score"),
        "priority_label": item.get("priority"),
        "timestamp": item.get("timestamp"),
        "route": item.get("route"),
        "suggested_action": item.get("suggested_action"),
        "related_experiments": list(item.get("related_experiments") or [])[:4],
        "related_resources": list(item.get("related_resources") or [])[:4],
        "related_literature": list(item.get("related_literature") or [])[:4],
        "pinned": bool(item.get("pinned")),
        "dismissed": bool(item.get("dismissed")),
        "icon": _mobile_intelligence_icon(str(item.get("item_type") or "")),
        "provenance": compact_provenance,
    }


def _mobile_intelligence_icon(item_type: str) -> str:
    mapping = {
        "Experiment Reminder": "science",
        "Workflow Reminder": "timeline",
        "Missing Analysis": "analytics",
        "Missing Notebook": "note",
        "Protocol Insight": "protocol",
        "Statistical Finding": "bar_chart",
        "Knowledge Graph Insight": "hub",
        "New Literature": "article",
        "Similar Experiment": "memory",
        "Resource Warning": "inventory",
        "Copilot Recommendation": "auto_awesome",
    }
    return mapping.get(item_type, "notifications")


def _mobile_morning_item(item: dict[str, object]) -> dict[str, object]:
    """Return a compact Morning Brief item."""

    provenance = item.get("provenance") if isinstance(item.get("provenance"), list) else []
    return {
        "title": item.get("title"),
        "summary": item.get("summary"),
        "timestamp": item.get("timestamp"),
        "priority": item.get("priority"),
        "suggested_action": item.get("suggested_action"),
        "route": item.get("route"),
        "related_experiments": list(item.get("related_experiments") or [])[:4],
        "related_resources": list(item.get("related_resources") or [])[:4],
        "related_literature": list(item.get("related_literature") or [])[:4],
        "provenance": [
            {
                "fact": record.get("fact"),
                "source": record.get("source"),
                "provider": record.get("provider"),
                "id": record.get("experiment_id") or record.get("asset_id") or record.get("document_id") or record.get("resource_id") or record.get("workflow_id"),
            }
            for record in provenance[:3]
            if isinstance(record, dict)
        ],
    }


def _mobile_workspace_payload(workspace: dict[str, object]) -> dict[str, object]:
    experiment = workspace.get("experiment") if isinstance(workspace.get("experiment"), dict) else {}
    copilot = workspace.get("research_copilot") if isinstance(workspace.get("research_copilot"), dict) else {}
    sections = copilot.get("sections") if isinstance(copilot.get("sections"), dict) else {}
    return {
        "overview": {
            "id": experiment.get("id"),
            "title": experiment.get("title"),
            "human_experiment_id": experiment.get("experiment_id"),
            "date": experiment.get("date"),
            "summary": (workspace.get("ai_summary") or {}).get("text") if isinstance(workspace.get("ai_summary"), dict) else None,
        },
        "workflow": workspace.get("workflow") or {},
        "timeline_preview": (workspace.get("timeline") or {}).get("events", [])[:5] if isinstance(workspace.get("timeline"), dict) else [],
        "key_notebook_notes": list(workspace.get("notebook_entries") or [])[:3],
        "key_statistics": list(workspace.get("statistics") or [])[:3],
        "key_images": [_mobile_asset_card(asset) for asset in list(workspace.get("microscopy") or [])[:6] if isinstance(asset, dict)],
        "key_graphpad_assets": [_mobile_asset_card(asset) for asset in list(workspace.get("graphpad") or [])[:4] if isinstance(asset, dict)],
        "key_spreadsheets": list(workspace.get("spreadsheets") or [])[:3],
        "key_resources": [_mobile_resource_card(resource) for resource in list(workspace.get("resources") or [])[:6] if isinstance(resource, dict)],
        "research_copilot_summary": {
            "provider": copilot.get("provider"),
            "natural_summary": copilot.get("natural_summary"),
            "key_findings": list(sections.get("key_findings") or [])[:3],
            "potential_concerns": list(sections.get("potential_concerns") or [])[:3],
        },
        "related_entities": list(workspace.get("related_entities") or [])[:8],
        "related_experiments": [_mobile_experiment_minimal(item) for item in list(workspace.get("related_experiments") or [])[:5] if isinstance(item, dict)],
        "scientific_memory": {
            "most_similar_experiments": list((workspace.get("scientific_memory") or {}).get("most_similar_experiments") or [])[:3]
            if isinstance(workspace.get("scientific_memory"), dict)
            else [],
        },
    }


def _mobile_quantification_payload(workspace: dict[str, object]) -> dict[str, object]:
    """Return a compact Quantification Workspace for mobile clients."""

    experiment = workspace.get("experiment") if isinstance(workspace.get("experiment"), dict) else {}
    overview = workspace.get("overview") if isinstance(workspace.get("overview"), dict) else {}
    copilot = workspace.get("research_copilot") if isinstance(workspace.get("research_copilot"), dict) else {}
    sections = copilot.get("sections") if isinstance(copilot.get("sections"), dict) else {}
    return {
        "experiment": _mobile_experiment_minimal(experiment),
        "overview": overview,
        "raw_images": list(workspace.get("raw_images") or [])[:8],
        "processed_images": list(workspace.get("processed_images") or [])[:4],
        "quantification_tables": list(workspace.get("quantification_tables") or [])[:6],
        "statistical_analysis": list(workspace.get("statistical_analysis") or [])[:6],
        "graphpad_assets": list(workspace.get("graphpad_assets") or [])[:6],
        "representative_figures": list(workspace.get("representative_figures") or [])[:3],
        "timeline_events": list(workspace.get("timeline_events") or [])[:10],
        "knowledge_graph": {
            "markers": list((workspace.get("knowledge_graph") or {}).get("markers") or [])[:8]
            if isinstance(workspace.get("knowledge_graph"), dict)
            else [],
            "compounds": list((workspace.get("knowledge_graph") or {}).get("compounds") or [])[:8]
            if isinstance(workspace.get("knowledge_graph"), dict)
            else [],
            "entities": list((workspace.get("knowledge_graph") or {}).get("entities") or [])[:8]
            if isinstance(workspace.get("knowledge_graph"), dict)
            else [],
        },
        "evidence_summary": (workspace.get("evidence") or {}).get("summary") if isinstance(workspace.get("evidence"), dict) else None,
        "workflow": workspace.get("workflow") or {},
        "copilot": {
            "provider": copilot.get("provider"),
            "current_quantitative_evidence": list(sections.get("current_quantitative_evidence") or [])[:3],
            "missing_analyses": list(sections.get("missing_analyses") or [])[:4],
            "recommended_next_steps": list(sections.get("recommended_next_steps") or [])[:3],
        },
        "future_modules": list(workspace.get("future_modules") or [])[:12],
        "limitations": list(workspace.get("limitations") or [])[:6],
    }


def _mobile_experiment_minimal(experiment: dict[str, object]) -> dict[str, object]:
    return {
        "id": experiment.get("id"),
        "title": experiment.get("title") or experiment.get("experiment_id"),
        "human_experiment_id": experiment.get("experiment_id"),
        "route": _mobile_route(f"/experiments/{experiment.get('id')}"),
    }


def _mobile_resource_card(resource: dict[str, object]) -> dict[str, object]:
    return {
        "id": resource.get("resource_id"),
        "title": resource.get("name"),
        "subtitle": f"{resource.get('resource_type') or 'resource'} · {resource.get('vendor') or 'local'}",
        "type": resource.get("resource_type") or "resource",
        "route": f"#/resources/{resource.get('resource_id')}",
        "provenance": _compact_provenance("resource", "resource_catalog", resource_id=resource.get("resource_id")),
    }


def _mobile_experiment_workspace(experiment_id: str) -> dict[str, object]:
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
        use_ai=False,
        knowledge_graph=knowledge_graph_service,
    )
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Experiment workspace not found: {experiment_id}")
    linked_designs = [
        design
        for design in store.list_experiment_designs(workspace_id=str((experiment or {}).get("workspace_id") or "") or None)
        if design.get("linked_experiment_id") in {experiment_id, str((experiment or {}).get("id") or ""), str((experiment or {}).get("experiment_id") or "")}
    ]
    design_sections = []
    for design in linked_designs:
        full_design = store.get_experiment_design(str(design["design_id"]))
        if full_design:
            reminders = all_reminders([full_design], include_drafts=True)
            completed = [item for item in reminders if item.get("reminder_status") == "completed"]
            design_sections.append({
                "design": full_design,
                "timeline": build_design_timeline(full_design),
                "reminders": reminders,
                "completed_reminders": completed,
            })
    workspace["experiment_designs"] = design_sections
    workspace.setdefault("sections", {})["experiment_designs"] = design_sections
    return workspace


@app.get("/mobile/status", tags=["mobile"])
def mobile_status() -> dict[str, object]:
    """Return compact mobile API status."""

    production = _production_readiness()
    return {
        "status": "ok",
        "project": "ResearchOS",
        "app_version": "v0.2 preview",
        "app_env": production["app_env"],
        "data_classification": production["data_classification"],
        "server_time": datetime.now(timezone.utc).isoformat(),
        "warnings": list(production.get("warnings") or [])[:3],
    }


@app.get("/mobile/connection-info", tags=["mobile"])
def mobile_connection_info(request: Request) -> dict[str, object]:
    """Return mobile client connection guidance without exposing secrets."""

    deployment = _deployment_status()
    request_host = request.url.hostname or ""
    request_port = request.url.port
    public_base_url = str(deployment.get("public_base_url") or "").strip().rstrip("/")
    request_base_url = f"{request.url.scheme}://{request_host}{f':{request_port}' if request_port else ''}"
    recommended_mobile_url = public_base_url or request_base_url
    warnings = list(deployment.get("warnings") or [])
    if request_host in {"127.0.0.1", "localhost"}:
        warnings.append("This request used localhost. A physical iPhone must use a LAN, HTTPS, or Tailscale URL instead.")
    if not public_base_url:
        warnings.append("Set PUBLIC_BASE_URL to the URL iPhones should use, such as http://192.168.1.25:8001 or a Tailscale HTTPS URL.")
    return {
        "server_name": settings.project_name,
        "version": "ResearchOS v0.2 preview",
        "environment": deployment.get("mode"),
        "app_env": settings.environment,
        "data_classification": settings.data_classification,
        "demo_mode": settings.environment != "production" or settings.data_classification == "demo",
        "public_base_url": public_base_url,
        "public_base_url_configured": bool(public_base_url),
        "current_host": request_host,
        "current_port": request_port,
        "configured_host": deployment.get("host"),
        "configured_port": deployment.get("port"),
        "request_base_url": request_base_url,
        "recommended_mobile_url": recommended_mobile_url,
        "localhost_only": bool(deployment.get("localhost_only")),
        "warnings": warnings,
    }


@app.get("/mobile/auth/me", tags=["mobile"])
def mobile_auth_me() -> dict[str, object]:
    """Return compact current-user information for mobile."""

    user = _current_user_payload()
    permissions = user.get("permission_summary") if isinstance(user.get("permission_summary"), dict) else {}
    workspace = user.get("current_workspace") if isinstance(user.get("current_workspace"), dict) else {}
    return {
        "user_id": user.get("user_id"),
        "display_name": user.get("display_name"),
        "email": user.get("email"),
        "role": user.get("role"),
        "workspace": {
            "workspace_id": workspace.get("workspace_id"),
            "name": workspace.get("name"),
            "role": (workspace.get("current_user_membership") or {}).get("role") if isinstance(workspace.get("current_user_membership"), dict) else user.get("role"),
        },
        "auth_mode": user.get("auth_mode"),
        "permissions_summary": {
            "can_view": user.get("can_view"),
            "can_edit": user.get("can_edit"),
            "can_admin": user.get("can_admin"),
            "note": (permissions.get("enforcement") or {}).get("note") if isinstance(permissions.get("enforcement"), dict) else None,
        },
    }


@app.get("/mobile/dashboard", tags=["mobile"])
def mobile_dashboard() -> dict[str, object]:
    """Return mobile-ready dashboard cards."""

    store = SQLiteStore(settings=settings)
    workspace = current_workspace(settings, store)
    workspace_id = str(workspace.get("workspace_id") or "")
    experiments = store.list_experiments(workspace_id=workspace_id)
    assets = store.list_assets(workspace_id=workspace_id)
    sessions_list = store.list_sessions(workspace_id=workspace_id)
    active = next((session for session in sessions_list if session.get("status") == "active"), None)
    cards = [
        _mobile_dashboard_card("Current workspace", str(workspace.get("name") or "ResearchOS workspace"), "workspace", 1, route="/mobile/settings", provenance=_compact_provenance("workspace", "sqlite", workspace_id=workspace.get("workspace_id"))),
        _mobile_dashboard_card("Active session", str(active.get("experiment_id") if active else "No active session"), "session", 2, route=_mobile_route("/sessions/active"), action="start_session" if active is None else "open_session"),
        _mobile_dashboard_card("Experiments", f"{len(experiments)} indexed", "experiments", 3, route=_mobile_route("/experiments")),
        _mobile_dashboard_card("Recent assets", f"{len(assets)} assets available", "assets", 4, route="#/assets"),
    ]
    if experiments:
        cards.extend(
            _mobile_dashboard_card(
                str(experiment.get("experiment_id") or experiment.get("title")),
                f"Stage: {WorkflowEngine(store).workflow_for_experiment(experiment).get('current_stage') or 'Planning'}",
                "recent_experiment",
                10 + index,
                route=_mobile_route(f"/experiments/{experiment.get('id')}/workspace"),
                provenance=_compact_provenance("experiment", "sqlite", experiment_id=experiment.get("id")),
            )
            for index, experiment in enumerate(experiments[:5])
        )
    cards.append(_mobile_dashboard_card("Ask ResearchOS", "Use local evidence and Copilot context.", "quick_action", 50, route=_mobile_route("/assistant/ask"), action="ask_assistant"))
    feed = lab_intelligence_service.build_feed(limit=12)
    morning = overnight_intelligence_service.morning_brief(period="today", limit=6)
    intelligence_cards = [_mobile_intelligence_card(item) for item in list(feed.get("items") or [])[:8] if isinstance(item, dict)]
    morning_card = _mobile_dashboard_card(
        "Morning Brief",
        str(morning.get("summary") or "No observed changes today."),
        "morning_brief",
        0,
        route="/mobile/intelligence/morning",
        action="open_morning_brief",
        provenance=_compact_provenance("morning_brief", "ResearchOS", workspace_id=workspace.get("workspace_id")),
    )
    return {
        "cards": [morning_card, *(intelligence_cards or sorted(cards, key=lambda item: int(item["priority"])))],
        "static_cards": sorted(cards, key=lambda item: int(item["priority"])),
        "intelligence_feed": {
            "total_items": feed.get("total_items", 0),
            "items": intelligence_cards,
            "filters": feed.get("filters", []),
        },
        "morning_brief": morning,
        "quick_actions": ["new_experiment", "start_session", "search", "ask_copilot"],
    }


@app.get("/mobile/intelligence/feed", tags=["mobile"])
def mobile_intelligence_feed(
    item_type: str | None = Query(default=None),
    include_dismissed: bool = Query(default=False),
    limit: int = Query(default=30, ge=1, le=100),
) -> dict[str, object]:
    """Return compact Laboratory Intelligence cards for mobile clients."""

    feed = lab_intelligence_service.build_feed(
        item_type=item_type,
        include_dismissed=include_dismissed,
        limit=limit,
    )
    return {
        "generated_at": feed.get("generated_at"),
        "total_items": feed.get("total_items", 0),
        "items": [_mobile_intelligence_card(item) for item in list(feed.get("items") or []) if isinstance(item, dict)],
        "filters": feed.get("filters", []),
        "priority_counts": feed.get("priority_counts", {}),
    }


@app.post("/mobile/intelligence/feed/{item_id}/dismiss", tags=["mobile"])
def mobile_dismiss_intelligence_item(item_id: str) -> dict[str, object]:
    """Dismiss one Laboratory Intelligence item from mobile."""

    return lab_intelligence_service.set_item_state(item_id, dismissed=True)


@app.post("/mobile/intelligence/feed/{item_id}/pin", tags=["mobile"])
def mobile_pin_intelligence_item(item_id: str, request: LabIntelligenceStateRequest | None = Body(default=None)) -> dict[str, object]:
    """Pin or unpin one Laboratory Intelligence item from mobile."""

    pinned = True if request is None or request.pinned is None else request.pinned
    return lab_intelligence_service.set_item_state(item_id, pinned=pinned)


@app.get("/mobile/intelligence/morning", tags=["mobile"])
def mobile_morning_intelligence_brief(
    period: Literal["today", "yesterday", "last_week"] = Query(default="today"),
    limit: int = Query(default=8, ge=1, le=30),
) -> dict[str, object]:
    """Return a compact Morning Brief for mobile clients."""

    brief = overnight_intelligence_service.morning_brief(period=period, limit=limit)
    sections = brief.get("sections") if isinstance(brief.get("sections"), dict) else {}
    return {
        "generated_at": brief.get("generated_at"),
        "period": brief.get("period"),
        "period_label": brief.get("period_label"),
        "summary": brief.get("summary"),
        "total_items": brief.get("total_items", 0),
        "sections": {
            key: [_mobile_morning_item(item) for item in list(value or [])[:limit] if isinstance(item, dict)]
            for key, value in sections.items()
        },
        "section_counts": brief.get("section_counts", {}),
        "principle": brief.get("principle"),
    }


@app.get("/mobile/search", tags=["mobile"])
def mobile_search(q: str = Query(..., min_length=1), limit_per_group: int = Query(4, ge=1, le=10)) -> dict[str, object]:
    """Return compact universal search results for mobile."""

    results = universal_search_service.search(q, limit_per_group=limit_per_group)
    grouped = {}
    for group, items in (results.get("grouped_results") or {}).items():
        grouped[group] = [
            {
                "title": item.get("title") or item.get("name") or item.get("id"),
                "subtitle": item.get("snippet") or item.get("summary") or item.get("type"),
                "type": group,
                "score": item.get("score"),
                "route": item.get("route") or item.get("href"),
            }
            for item in list(items)[:limit_per_group]
            if isinstance(item, dict)
        ]
    return {"query": q, "total_results": results.get("total_results", 0), "grouped_results": grouped, "suggested_queries": list(results.get("suggested_queries") or [])[:5], "related_entities": list(results.get("related_entities") or [])[:8]}


@app.get("/mobile/experiments", tags=["mobile"])
def mobile_experiments() -> dict[str, object]:
    """Return compact experiment cards for mobile lists."""

    store = SQLiteStore(settings=settings)
    workspace_id = _current_workspace_id()
    experiments = store.list_experiments(workspace_id=workspace_id)
    return {"experiments": [_mobile_experiment_card(store, experiment) for experiment in experiments], "count": len(experiments)}


@app.post("/mobile/experiments/create", tags=["mobile"])
def mobile_create_experiment(request: NewExperimentWizardRequest) -> dict[str, object]:
    """Create a planned experiment from the mobile New Experiment Wizard."""

    return _create_experiment_from_wizard(request, mobile=True)


@app.get("/mobile/experiments/{experiment_id}", tags=["mobile"])
def mobile_experiment_detail(experiment_id: str) -> dict[str, object]:
    """Return compact experiment detail for mobile."""

    store = SQLiteStore(settings=settings)
    experiment = store.find_experiment_by_reference(experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail=f"Experiment not found: {experiment_id}")
    timeline = _experiment_timeline(store, experiment)
    linked_assets = store.list_assets_for_experiment(experiment)
    statistics_assets = [asset for asset in linked_assets if _asset_has_statistics(asset)]
    image_assets = [asset for asset in linked_assets if _is_microscopy_asset(asset)]
    notebook_count = 1 if experiment.get("source_document_id") else 0
    return {
        "overview": _mobile_experiment_card(store, experiment),
        "workflow_stage": WorkflowEngine(store).workflow_for_experiment(experiment).get("current_stage"),
        "latest_timeline_events": list(timeline.get("events") or [])[:5],
        "key_findings": [experiment.get("conclusions")] if experiment.get("conclusions") else [],
        "linked_assets_count": len(linked_assets),
        "statistics_summary": f"{len(statistics_assets)} linked statistics asset(s)",
        "image_count": len(image_assets),
        "notebook_count": notebook_count,
        "quick_actions": ["open_workspace", "start_session", "ask_copilot", "compare_experiments"],
    }


@app.get("/mobile/experiments/{experiment_id}/workspace", tags=["mobile"])
def mobile_experiment_workspace(experiment_id: str) -> dict[str, object]:
    """Return a mobile-optimized experiment workspace."""

    return _mobile_workspace_payload(_mobile_experiment_workspace(experiment_id))


@app.get("/mobile/experiments/{experiment_id}/quantification", tags=["mobile"])
def mobile_experiment_quantification_workspace(experiment_id: str) -> dict[str, object]:
    """Return a mobile-optimized Quantification Workspace."""

    workspace = quantification_workspace_service.build(experiment_id, use_ai=False)
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Quantification workspace not found: {experiment_id}")
    return _mobile_quantification_payload(workspace)


@app.get("/mobile/experiments/{experiment_id}/timeline", tags=["mobile"])
def mobile_experiment_timeline(experiment_id: str) -> dict[str, object]:
    """Return compact timeline events for mobile."""

    store = SQLiteStore(settings=settings)
    experiment = store.find_experiment_by_reference(experiment_id)
    if experiment is None:
        assets = store.list_assets(experiment_id=experiment_id)
        if not assets:
            raise HTTPException(status_code=404, detail=f"Experiment not found: {experiment_id}")
        timeline = _virtual_experiment_timeline(store, experiment_id)
    else:
        timeline = _experiment_timeline(store, experiment)
    return {"experiment_id": experiment_id, "events": list(timeline.get("events") or [])[:25]}


@app.get("/mobile/sessions", tags=["mobile"])
def mobile_sessions() -> dict[str, object]:
    """Return compact session list for mobile."""

    store = SQLiteStore(settings=settings)
    sessions_list = store.list_sessions(workspace_id=_current_workspace_id())
    return {"sessions": [_mobile_session_card(session) for session in sessions_list], "count": len(sessions_list)}


@app.get("/mobile/sessions/active", tags=["mobile"])
def mobile_active_session() -> dict[str, object]:
    """Return the active session, if any."""

    store = SQLiteStore(settings=settings)
    active = next((session for session in store.list_sessions(workspace_id=_current_workspace_id()) if session.get("status") == "active"), None)
    return {"active_session": _mobile_session_card(active) if active else None}


@app.post("/mobile/sessions/start", tags=["mobile"])
def mobile_start_session(request: SessionStartRequest) -> dict[str, object]:
    """Start or return the active session from mobile bench workflow."""

    store = SQLiteStore(settings=settings)
    active = next((session for session in store.list_sessions(workspace_id=_current_workspace_id()) if session.get("status") == "active"), None)
    if active is not None:
        session = _mobile_session_card(active)
        return {
            "session_id": session["session_id"],
            "session": session,
            "active_session": session,
            "created_new": False,
            "message": "An active session already exists. Returning the existing session.",
        }

    session = _mobile_session_card(start_session(request).model_dump())
    return {
        "session_id": session["session_id"],
        "session": session,
        "active_session": session,
        "created_new": True,
        "message": "Started a new mobile Bench Mode session.",
    }


@app.post("/mobile/sessions/{session_id}/note", tags=["mobile"])
def mobile_session_note(session_id: str, request: MobileSessionNoteRequest) -> dict[str, object]:
    """Append a compact mobile note to a session."""

    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Session note text must not be empty.")
    event_type = "voice_note" if request.note_type == "voice_transcript" else request.note_type
    event = append_session_event(
        session_id,
        SessionEventAppendRequest(
            event_type=event_type,  # type: ignore[arg-type]
            title=request.note_type.replace("_", " ").title(),
            content=request.text.strip(),
            metadata={"source": "mobile"},
        ),
    )
    return {"event": event.model_dump(), "session_id": session_id}


def _mobile_bench_event(
    session_id: str,
    event_type: SessionEventType,
    title: str,
    content: str | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    """Append a typed Bench Mode action through the canonical session event API."""

    event = append_session_event(
        session_id,
        SessionEventAppendRequest(
            event_type=event_type,
            title=title,
            content=content,
            metadata={"source": "mobile_bench", **(metadata or {})},
        ),
    )
    return {
        "session_id": session_id,
        "event": event.model_dump(),
        "timeline_updated": True,
        "workspace_update_requested": True,
    }


@app.post("/mobile/sessions/{session_id}/observation", tags=["mobile"])
def mobile_session_observation(session_id: str, request: MobileObservationRequest) -> dict[str, object]:
    """Capture a one-tap Bench Mode observation."""

    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Observation text must not be empty.")
    return _mobile_bench_event(
        session_id=session_id,
        event_type="observation",
        title="Observation",
        content=text,
        metadata={"action": "observation"},
    )


@app.post("/mobile/sessions/{session_id}/treatment", tags=["mobile"])
def mobile_session_treatment(session_id: str, request: MobileTreatmentRequest) -> dict[str, object]:
    """Capture a minimal treatment event from Bench Mode."""

    metadata = {
        "action": "treatment",
        "compound": request.compound.strip() if request.compound else None,
        "dose": request.dose.strip() if request.dose else None,
        "units": request.units.strip() if request.units else None,
        "time": request.time.strip() if request.time else None,
    }
    metadata = {key: value for key, value in metadata.items() if value is not None}
    parts = [
        f"compound={metadata['compound']}" if metadata.get("compound") else None,
        f"dose={metadata['dose']} {metadata.get('units', '')}".strip() if metadata.get("dose") else None,
        f"time={metadata['time']}" if metadata.get("time") else None,
        request.notes.strip() if request.notes and request.notes.strip() else None,
    ]
    content = "; ".join(part for part in parts if part)
    if not content:
        raise HTTPException(status_code=400, detail="Treatment requires at least one field.")
    return _mobile_bench_event(
        session_id=session_id,
        event_type="treatment",
        title="Treatment",
        content=content,
        metadata=metadata,
    )


@app.post("/mobile/sessions/{session_id}/media-change", tags=["mobile"])
def mobile_session_media_change(session_id: str, request: MobileMediaChangeRequest) -> dict[str, object]:
    """Capture a minimal media-change event from Bench Mode."""

    media_type = request.media_type.strip() if request.media_type else ""
    notes = request.notes.strip() if request.notes else ""
    content = "; ".join(part for part in [f"media={media_type}" if media_type else None, notes or None] if part)
    if not content:
        raise HTTPException(status_code=400, detail="Media change requires media type or notes.")
    return _mobile_bench_event(
        session_id=session_id,
        event_type="media_change",
        title="Media Change",
        content=content,
        metadata={"action": "media_change", "media_type": media_type} if media_type else {"action": "media_change"},
    )


@app.post("/mobile/sessions/{session_id}/voice-note", tags=["mobile"])
def mobile_session_voice_note(session_id: str, request: MobileVoiceNoteRequest) -> dict[str, object]:
    """Capture a voice-note placeholder or future speech transcript from Bench Mode."""

    transcript = request.transcript.strip() if request.transcript else ""
    content = transcript or "Voice capture placeholder. Speech-to-text is not enabled yet."
    return _mobile_bench_event(
        session_id=session_id,
        event_type="voice_note",
        title="Voice Note",
        content=content,
        metadata={"action": "voice_note", "placeholder": request.placeholder},
    )


@app.post("/mobile/sessions/{session_id}/attach-placeholder", tags=["mobile"])
def mobile_session_attach_placeholder(session_id: str, request: MobileAttachPlaceholderRequest) -> dict[str, object]:
    """Record a placeholder for future camera, file, GraphPad, or sequencing attachment."""

    title = request.title.strip() if request.title else f"{request.attachment_type.title()} Attachment Placeholder"
    notes = request.notes.strip() if request.notes else f"{request.attachment_type.title()} attachment is not implemented yet."
    return _mobile_bench_event(
        session_id=session_id,
        event_type="manual_note",
        title=title,
        content=notes,
        metadata={"action": "attach_placeholder", "attachment_type": request.attachment_type},
    )


@app.post("/mobile/sessions/{session_id}/end", tags=["mobile"])
def mobile_end_session(session_id: str, request: SessionEndRequest | None = Body(default=None)) -> dict[str, object]:
    """End a mobile experiment session."""

    return {"session": _mobile_session_card(end_session(session_id, request).model_dump())}


@app.get("/mobile/knowledge/entity/{entity:path}", tags=["mobile"])
def mobile_knowledge_entity(entity: str) -> dict[str, object]:
    """Return compact knowledge entity detail."""

    detail = knowledge_graph_service.entity_detail(entity)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Knowledge graph entity not found: {entity}")
    return {
        "entity": detail.get("entity"),
        "entity_type": detail.get("entity_type"),
        "summary": detail.get("summary"),
        "related_entities": list(detail.get("related_entities") or [])[:10],
        "experiments": [_mobile_experiment_minimal(item) for item in list(detail.get("experiments") or [])[:6] if isinstance(item, dict)],
        "literature": list(detail.get("literature") or [])[:4],
        "microscopy_assets": [_mobile_asset_card(item) for item in list(detail.get("microscopy_assets") or [])[:6] if isinstance(item, dict)],
    }


@app.post("/mobile/assistant/ask", tags=["mobile"])
def mobile_assistant_ask(request: AssistantRequest) -> dict[str, object]:
    """Return compact assistant response for mobile."""

    question = _assistant_question(request)
    if not question:
        raise HTTPException(status_code=400, detail="Assistant question must not be empty.")
    answer = ask_research_assistant(question=question, settings=settings, use_ai=request.use_ai)
    return {
        "direct_answer": answer.direct_answer,
        "supporting_cards": list(answer.evidence_from_experiments or [])[:4],
        "related_experiments": list(answer.direct_matches or [])[:4],
        "related_entities": [],
        "suggested_next_questions": [
            "Show related experiments.",
            "Compare this with literature.",
            "What should we test next?",
        ],
        "limitations": list(answer.limitations_uncertainties or [])[:4],
    }


@app.post("/mobile/assistant/copilot", tags=["mobile"])
def mobile_assistant_copilot(request: AssistantRequest) -> dict[str, object]:
    """Return compact Research Copilot answer for mobile."""

    question = _assistant_question(request)
    if not question:
        raise HTTPException(status_code=400, detail="Copilot question must not be empty.")
    answer = answer_with_knowledge_graph(question=question, settings=settings, use_ai=request.use_ai)
    return {
        "direct_answer": answer.direct_answer,
        "supporting_cards": list(answer.experiments or [])[:4],
        "related_experiments": list(answer.experiments or [])[:4],
        "related_entities": list(answer.related_entities or [])[:8],
        "suggested_next_questions": [
            "Which prior experiments are most similar?",
            "What evidence supports this?",
            "What are the limitations?",
        ],
        "limitations": list(answer.limitations or [])[:4],
    }


@app.get("/mobile/settings", tags=["mobile"])
def mobile_settings() -> dict[str, object]:
    """Return compact mobile settings/readiness state."""

    deployment = _deployment_status()
    onenote = _onenote_readiness()
    production = _production_readiness()
    workspace = current_workspace(settings, SQLiteStore(settings=settings))
    return {
        "app_version": "ResearchOS v0.2 preview",
        "server_url": deployment.get("public_base_url") or f"http://{deployment.get('host')}:{deployment.get('port')}",
        "workspace": {"workspace_id": workspace.get("workspace_id"), "name": workspace.get("name")},
        "auth_mode": auth_mode(settings),
        "onenote_readiness": {
            "status": "ready" if onenote.get("read_only_sync_ready") else "not_ready",
            "message": onenote.get("read_only_sync_message"),
            "write_back_disabled": onenote.get("write_back_disabled"),
        },
        "production_readiness": {
            "status": "ready" if not production.get("warnings") else "preview",
            "warnings": list(production.get("warnings") or [])[:5],
        },
        "pwa_install_docs": "docs/MOBILE_PWA.md",
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

    for session in store.list_sessions():
        session_experiment_id = str(session.get("experiment_id") or "")
        if session_experiment_id not in experiment_references:
            continue
        for session_event in store.session_timeline(str(session["session_id"])):
            events.append(
                {
                    "timestamp": _timeline_timestamp(session_event.get("created_at")),
                    "event_type": str(session_event.get("event_type") or "session_event"),
                    "title": str(session_event.get("title") or "Session event"),
                    "description": str(session_event.get("content") or "Session event recorded in ResearchOS."),
                    "source": "experiment_session",
                    "linked_asset_ids": [str(session_event.get("asset_id"))] if session_event.get("asset_id") else [],
                    "linked_document_ids": [],
                    "session_id": str(session["session_id"]),
                    "session_event_id": str(session_event.get("event_id") or ""),
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

    usage_records = store.list_inventory_usage_for_experiment(str(experiment.get("id")))
    if experiment.get("experiment_id"):
        usage_records.extend(store.list_inventory_usage_for_experiment(str(experiment.get("experiment_id"))))
    seen_usage: set[str] = set()
    for usage in usage_records:
        usage_id = str(usage.get("usage_id"))
        if usage_id in seen_usage:
            continue
        seen_usage.add(usage_id)
        amount = usage.get("amount_used")
        units = usage.get("units")
        amount_text = f"{amount} {units}".strip() if amount is not None else "amount not recorded"
        events.append(
            {
                "timestamp": _timeline_timestamp(usage.get("date_used"), usage.get("created_at")),
                "event_type": "reagent_used",
                "title": f"Reagent used: {usage.get('inventory_item_name') or usage.get('inventory_item_id')}",
                "description": f"{amount_text}. Purpose: {usage.get('purpose') or 'not specified'}.",
                "source": "inventory_usage",
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
    result = scan_graphpad_assets(settings=settings, workspace_id=_current_workspace_id())
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
def statistics(workspace_id: str | None = Query(default=None)) -> list[AssetResponse]:
    """Return assets containing extracted statistics metadata."""

    store = SQLiteStore(settings=settings)
    resolved_workspace_id = _current_workspace_id(workspace_id)
    return [
        AssetResponse(**_asset_with_link_info(store, asset))
        for asset in graphpad_statistics_assets(settings=settings)
        if _record_matches_workspace(asset, resolved_workspace_id)
    ]


@app.get("/providers/images/status", response_model=ImageProviderStatusResponse, tags=["providers"])
def images_provider_status() -> ImageProviderStatusResponse:
    """Return microscopy/image provider configuration and asset count."""

    return ImageProviderStatusResponse(**microscopy_status(settings=settings))


@app.post("/providers/images/scan", response_model=ImageProviderScanResponse, tags=["providers"])
def images_provider_scan() -> ImageProviderScanResponse:
    """Scan configured image folders and register discovered files as assets."""

    store = SQLiteStore(settings=settings)
    result = scan_microscopy_assets(settings=settings, workspace_id=_current_workspace_id())
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
def images(workspace_id: str | None = Query(default=None)) -> list[AssetResponse]:
    """Return registered microscopy/image assets."""

    store = SQLiteStore(settings=settings)
    resolved_workspace_id = _current_workspace_id(workspace_id)
    return [
        AssetResponse(**_asset_with_link_info(store, asset))
        for asset in microscopy_assets(settings=settings)
        if _record_matches_workspace(asset, resolved_workspace_id)
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
    result = scan_spreadsheet_assets(settings=settings, workspace_id=_current_workspace_id())
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
def spreadsheets(workspace_id: str | None = Query(default=None)) -> list[AssetResponse]:
    """Return registered generic spreadsheet assets."""

    store = SQLiteStore(settings=settings)
    resolved_workspace_id = _current_workspace_id(workspace_id)
    return [
        AssetResponse(**_asset_with_link_info(store, asset))
        for asset in spreadsheet_assets(settings=settings)
        if _record_matches_workspace(asset, resolved_workspace_id)
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


@app.get("/resources", response_model=list[ResourceResponse], tags=["resources"])
def resources(
    resource_type: ResourceType | None = Query(default=None),
    query: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
) -> list[ResourceResponse]:
    """List reusable laboratory resources."""

    store = SQLiteStore(settings=settings)
    resolved_workspace_id = _current_workspace_id(workspace_id)
    return [
        ResourceResponse(**resource)
        for resource in store.list_resources(
            resource_type=resource_type,
            query=query,
            workspace_id=resolved_workspace_id,
        )
    ]


@app.get("/resources/type/{resource_type}", response_model=list[ResourceResponse], tags=["resources"])
def resources_by_type(resource_type: str, workspace_id: str | None = Query(default=None)) -> list[ResourceResponse]:
    """Return resources of one normalized resource type."""

    normalized_type = normalize_resource_type(resource_type)
    if normalized_type not in RESOURCE_TYPES:
        raise HTTPException(status_code=404, detail=f"Unknown resource type: {resource_type}")
    return resources(resource_type=normalized_type, query=None, workspace_id=workspace_id)


@app.get("/resources/{resource_id}", response_model=ResourceResponse, tags=["resources"])
def resource_detail(resource_id: str) -> ResourceResponse:
    """Return one reusable resource with usage history."""

    store = SQLiteStore(settings=settings)
    resource = store.get_resource(resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail=f"Resource not found: {resource_id}")
    return ResourceResponse(**resource)


@app.post("/resources", response_model=ResourceResponse, tags=["resources"])
def create_resource(request: ResourceRequest) -> ResourceResponse:
    """Create a reusable laboratory resource."""

    return ResourceResponse(**_save_resource_request(request))


@app.put("/resources/{resource_id}", response_model=ResourceResponse, tags=["resources"])
def update_resource(resource_id: str, request: ResourceRequest) -> ResourceResponse:
    """Update a reusable laboratory resource."""

    store = SQLiteStore(settings=settings)
    if store.get_resource(resource_id) is None:
        raise HTTPException(status_code=404, detail=f"Resource not found: {resource_id}")
    return ResourceResponse(**_save_resource_request(request, resource_id=resource_id))


@app.get("/inventory", response_model=list[InventoryItemResponse], tags=["inventory"])
def inventory_items(
    vendor: str | None = Query(default=None),
    category: str | None = Query(default=None),
    storage_location: str | None = Query(default=None),
    query: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
) -> list[InventoryItemResponse]:
    """List local lab inventory items."""

    store = SQLiteStore(settings=settings)
    return [
        InventoryItemResponse(**item)
        for item in store.list_inventory_items(
            vendor=vendor,
            category=category,
            storage_location=storage_location,
            query=query,
            workspace_id=_current_workspace_id(workspace_id),
        )
    ]


@app.post("/inventory", response_model=InventoryItemResponse, tags=["inventory"])
def create_inventory_item(request: InventoryItemRequest) -> InventoryItemResponse:
    """Create a local inventory item."""

    return InventoryItemResponse(**_save_inventory_request(request))


@app.get("/inventory/export-csv", tags=["inventory"])
def export_inventory_csv(workspace_id: str | None = Query(default=None)) -> Response:
    """Export inventory as a spreadsheet-compatible CSV."""

    store = SQLiteStore(settings=settings)
    csv_text = records_to_csv(
        store.list_inventory_items(workspace_id=_current_workspace_id(workspace_id)),
        INVENTORY_CSV_FIELDS,
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="researchos_inventory.csv"'},
    )


@app.get("/inventory/status", tags=["inventory"])
def inventory_status(workspace_id: str | None = Query(default=None)) -> dict[str, object]:
    """Return derived stock, expiration, and reorder status for inventory."""

    store = SQLiteStore(settings=settings)
    items = store.list_inventory_items(workspace_id=_current_workspace_id(workspace_id))
    return inventory_status_summary(items)


@app.get("/inventory/reorder-needed", tags=["inventory"])
def inventory_reorder_needed(workspace_id: str | None = Query(default=None)) -> dict[str, object]:
    """Return inventory items at or below reorder threshold."""

    store = SQLiteStore(settings=settings)
    summary = inventory_status_summary(store.list_inventory_items(workspace_id=_current_workspace_id(workspace_id)))
    return {
        "count": summary["reorder_needed_count"],
        "items": summary["reorder_needed"],
    }


@app.post("/inventory/{item_id}/request-reorder", response_model=PurchaseRequestResponse, tags=["inventory", "purchasing"])
def request_inventory_reorder(item_id: str) -> PurchaseRequestResponse:
    """Create a draft purchase request from one inventory item."""

    store = SQLiteStore(settings=settings)
    item = store.get_inventory_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Inventory item not found: {item_id}")
    quantity = item.get("reorder_threshold") or 1
    request = PurchaseRequestRequest(
        item_name=str(item.get("name") or ""),
        vendor=item.get("vendor"),
        catalog_number=item.get("catalog_number"),
        quantity_requested=float(quantity) if quantity is not None else None,
        estimated_cost=item.get("price"),
        status="draft",
        notes=f"Reorder requested from inventory item {item_id}. Current quantity: {item.get('quantity')}.",
        linked_inventory_item_id=item_id,
    )
    return PurchaseRequestResponse(**_save_purchase_request_workflow(request))


@app.get("/inventory/expiring", tags=["inventory"])
def inventory_expiring(
    days: int = Query(default=90, ge=1, le=365),
    workspace_id: str | None = Query(default=None),
) -> dict[str, object]:
    """Return expired and soon-expiring inventory items."""

    store = SQLiteStore(settings=settings)
    summary = inventory_status_summary(store.list_inventory_items(workspace_id=_current_workspace_id(workspace_id)))
    items = [
        item
        for item in summary["items"]
        if item.get("expired") or (
            item.get("days_until_expiration") is not None
            and 0 <= int(item["days_until_expiration"]) <= days
        )
    ]
    return {
        "days": days,
        "count": len(items),
        "expired_count": summary["expired_count"],
        "expiring_soon_count": len([item for item in items if item.get("expiring_soon")]),
        "items": items,
    }


@app.get("/inventory/lookup", response_model=InventoryItemResponse, tags=["inventory"])
def inventory_lookup(
    code: str = Query(..., min_length=1),
    workspace_id: str | None = Query(default=None),
) -> InventoryItemResponse:
    """Lookup inventory by barcode, QR code, or internal label."""

    store = SQLiteStore(settings=settings)
    item = store.lookup_inventory_item_by_code(code.strip(), workspace_id=_current_workspace_id(workspace_id))
    if item is None:
        raise HTTPException(status_code=404, detail=f"Inventory code not found: {code}")
    return InventoryItemResponse(**item)


@app.get("/inventory/{item_id}/usage", response_model=list[InventoryUsageResponse], tags=["inventory"])
def inventory_item_usage(item_id: str, workspace_id: str | None = Query(default=None)) -> list[InventoryUsageResponse]:
    """Return usage history for one inventory item."""

    store = SQLiteStore(settings=settings)
    if store.get_inventory_item(item_id) is None:
        raise HTTPException(status_code=404, detail=f"Inventory item not found: {item_id}")
    return [
        InventoryUsageResponse(**usage)
        for usage in store.list_inventory_usage_for_item(item_id, workspace_id=_current_workspace_id(workspace_id))
    ]


@app.post("/inventory/{item_id}/usage", response_model=InventoryUsageResponse, tags=["inventory"])
def record_inventory_item_usage(item_id: str, request: InventoryUsageRequest) -> InventoryUsageResponse:
    """Record use of one inventory item in an experiment."""

    if not request.experiment_id:
        raise HTTPException(status_code=400, detail="experiment_id is required when recording item usage.")
    store = SQLiteStore(settings=settings)
    usage = _record_inventory_usage(store, item_id, request.experiment_id, request)
    return InventoryUsageResponse(**usage)


@app.post("/inventory/{item_id}/assign-code", response_model=InventoryItemResponse, tags=["inventory"])
def assign_inventory_code(item_id: str, request: InventoryCodeAssignmentRequest) -> InventoryItemResponse:
    """Assign barcode, QR, internal label, and freezer location fields."""

    store = SQLiteStore(settings=settings)
    item = store.get_inventory_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Inventory item not found: {item_id}")
    merged = {**item, **request.model_dump(exclude_unset=True)}
    saved = store.save_inventory_item(
        item_id=item_id,
        name=str(merged.get("name") or ""),
        category=merged.get("category"),
        vendor=merged.get("vendor"),
        catalog_number=merged.get("catalog_number"),
        lot_number=merged.get("lot_number"),
        rrid=merged.get("rrid"),
        price=merged.get("price"),
        unit=merged.get("unit"),
        storage_location=merged.get("storage_location"),
        quantity=merged.get("quantity"),
        reorder_threshold=merged.get("reorder_threshold"),
        expiration_date=merged.get("expiration_date"),
        barcode=merged.get("barcode"),
        qr_code=merged.get("qr_code"),
        internal_label=merged.get("internal_label"),
        freezer_box=merged.get("freezer_box"),
        freezer_position=merged.get("freezer_position"),
        shelf=merged.get("shelf"),
        room=merged.get("room"),
        notes=merged.get("notes"),
        linked_resource_id=merged.get("linked_resource_id"),
        owner_user_id=merged.get("owner_user_id"),
        created_by=merged.get("created_by"),
        workspace_id=merged.get("workspace_id"),
    )
    return InventoryItemResponse(**saved)


@app.get("/inventory/{item_id}/label", tags=["inventory"])
def inventory_label(item_id: str) -> dict[str, object]:
    """Return printable barcode/QR label data for one inventory item."""

    store = SQLiteStore(settings=settings)
    item = store.get_inventory_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Inventory item not found: {item_id}")
    return inventory_label_data(item)


@app.get("/inventory/{item_id}", response_model=InventoryItemResponse, tags=["inventory"])
def inventory_item_detail(item_id: str) -> InventoryItemResponse:
    """Return one inventory item."""

    store = SQLiteStore(settings=settings)
    item = store.get_inventory_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Inventory item not found: {item_id}")
    return InventoryItemResponse(**item)


@app.put("/inventory/{item_id}", response_model=InventoryItemResponse, tags=["inventory"])
def update_inventory_item(item_id: str, request: InventoryItemRequest) -> InventoryItemResponse:
    """Update one inventory item."""

    store = SQLiteStore(settings=settings)
    if store.get_inventory_item(item_id) is None:
        raise HTTPException(status_code=404, detail=f"Inventory item not found: {item_id}")
    return InventoryItemResponse(**_save_inventory_request(request, item_id=item_id))


@app.delete("/inventory/{item_id}", tags=["inventory"])
def delete_inventory_item(item_id: str) -> dict[str, object]:
    """Delete one inventory item."""

    store = SQLiteStore(settings=settings)
    if not store.delete_inventory_item(item_id):
        raise HTTPException(status_code=404, detail=f"Inventory item not found: {item_id}")
    return {"deleted": True, "item_id": item_id}


@app.get("/inventory/{item_id}/methods-citation", tags=["inventory"])
def inventory_methods_citation(item_id: str) -> dict[str, object]:
    """Return paper-methods reagent citation text for an inventory item."""

    store = SQLiteStore(settings=settings)
    item = store.get_inventory_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Inventory item not found: {item_id}")
    linked_resource = store.get_resource(str(item.get("linked_resource_id"))) if item.get("linked_resource_id") else None
    return {
        "item_id": item_id,
        "methods_citation": methods_citation(item, linked_resource),
        "reagent_details": {
            "name": item.get("name"),
            "vendor": item.get("vendor") or (linked_resource or {}).get("vendor"),
            "catalog_number": item.get("catalog_number") or (linked_resource or {}).get("catalog_number"),
            "rrid": item.get("rrid") or (linked_resource or {}).get("rrid"),
            "lot_number": item.get("lot_number") or (linked_resource or {}).get("lot_number"),
        },
        "linked_resource": linked_resource,
    }


@app.post("/methods/reagents", tags=["methods"])
def build_methods_reagents(request: ReagentMethodsRequest) -> dict[str, object]:
    """Generate paper/grant/protocol-ready reagent text from inventory records."""

    store = SQLiteStore(settings=settings)
    entries = []
    warnings = []
    for item_id in request.inventory_item_ids:
        item = store.get_inventory_item(item_id)
        if item is None:
            warnings.append(f"Inventory item not found: {item_id}")
            continue
        entry = _inventory_item_entry(
            store,
            item,
            include_lot_numbers=request.include_lot_numbers,
            include_storage_locations=request.include_storage_locations,
        )
        entries.append(entry)
    result = build_reagent_methods_text(entries, style=request.style)
    return result | {"warnings": [*result.get("warnings", []), *warnings]}


@app.get("/experiments/{experiment_id}/reagents", tags=["experiments"])
def experiment_reagents(
    experiment_id: str,
    workspace_id: str | None = None,
) -> dict[str, object]:
    """Return inventory items and resources linked to an experiment."""

    context = _experiment_reagent_context(SQLiteStore(settings=settings), experiment_id, workspace_id=workspace_id)
    store = SQLiteStore(settings=settings)
    entries = [_inventory_item_entry(store, item) for item in context["inventory_items"]]
    return {
        "experiment": context["experiment"],
        "inventory_items": context["inventory_items"],
        "inventory_usage": context["inventory_usage"],
        "resources": context["resources"],
        "methods_entries": entries,
        "warnings": [*context["warnings"], *[warning for entry in entries for warning in entry.get("warnings", [])]],
    }


@app.get("/experiments/{experiment_id}/inventory-usage", response_model=list[InventoryUsageResponse], tags=["experiments", "inventory"])
def experiment_inventory_usage(
    experiment_id: str,
    workspace_id: str | None = Query(default=None),
) -> list[InventoryUsageResponse]:
    """Return inventory usage records for one experiment."""

    store = SQLiteStore(settings=settings)
    experiment = store.find_experiment_by_reference(experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail=f"Experiment not found: {experiment_id}")
    resolved_workspace = _current_workspace_id(workspace_id or str(experiment.get("workspace_id") or "") or None)
    records = store.list_inventory_usage_for_experiment(str(experiment.get("id")), workspace_id=resolved_workspace)
    if experiment.get("experiment_id"):
        records.extend(store.list_inventory_usage_for_experiment(str(experiment.get("experiment_id")), workspace_id=resolved_workspace))
    seen: set[str] = set()
    unique = []
    for record in records:
        usage_id = str(record.get("usage_id"))
        if usage_id in seen:
            continue
        seen.add(usage_id)
        unique.append(record)
    return [InventoryUsageResponse(**usage) for usage in unique]


@app.post("/experiments/{experiment_id}/inventory-usage", response_model=InventoryUsageResponse, tags=["experiments", "inventory"])
def record_experiment_inventory_usage(experiment_id: str, request: InventoryUsageRequest) -> InventoryUsageResponse:
    """Record an inventory item used by one experiment."""

    if not request.inventory_item_id:
        raise HTTPException(status_code=400, detail="inventory_item_id is required.")
    store = SQLiteStore(settings=settings)
    usage = _record_inventory_usage(store, request.inventory_item_id, experiment_id, request)
    return InventoryUsageResponse(**usage)


@app.get("/experiments/{experiment_id}/methods-materials", tags=["experiments", "methods"])
def experiment_methods_materials(
    experiment_id: str,
    style: Literal["paper", "grant", "protocol"] = "paper",
    include_lot_numbers: bool = True,
    include_storage_locations: bool = False,
    workspace_id: str | None = None,
) -> dict[str, object]:
    """Return a draft Materials/Reagents section for an experiment."""

    store = SQLiteStore(settings=settings)
    context = _experiment_reagent_context(store, experiment_id, workspace_id=workspace_id)
    entries = [
        _inventory_item_entry(
            store,
            item,
            include_lot_numbers=include_lot_numbers,
            include_storage_locations=include_storage_locations,
        )
        for item in context["inventory_items"]
    ]
    result = build_reagent_methods_text(entries, style=style)
    return {
        "experiment": context["experiment"],
        "style": result["style"],
        "text": result["text"],
        "entries": result["entries"],
        "inventory_usage": context["inventory_usage"],
        "resources": context["resources"],
        "warnings": [*context["warnings"], *result.get("warnings", [])],
    }


@app.get("/experiment-design-templates", response_model=list[ExperimentDesignTemplateResponse], tags=["experiment-design-templates"])
def experiment_design_templates(workspace_id: str | None = Query(default=None)) -> list[ExperimentDesignTemplateResponse]:
    """Return built-in and saved experiment design templates."""

    store = SQLiteStore(settings=settings)
    templates = [ExperimentDesignTemplateResponse(**template) for template in _builtin_design_templates()]
    templates.extend(
        ExperimentDesignTemplateResponse(**template)
        for template in store.list_experiment_design_templates(workspace_id=_current_workspace_id(workspace_id))
    )
    return templates


@app.post("/experiment-design-templates", response_model=ExperimentDesignTemplateResponse, tags=["experiment-design-templates"])
def create_experiment_design_template(request: ExperimentDesignTemplateRequest) -> ExperimentDesignTemplateResponse:
    """Create a reusable experiment design template."""

    if not request.name.strip():
        raise HTTPException(status_code=400, detail="Template name is required.")
    user, workspace = _current_user_workspace_metadata()
    store = SQLiteStore(settings=settings)
    template = store.save_experiment_design_template(
        name=request.name.strip(),
        description=request.description,
        experiment_type=request.experiment_type,
        default_cell_line_or_model=request.default_cell_line_or_model,
        default_reporters=request.default_reporters,
        default_conditions=request.default_conditions,
        default_events=request.default_events,
        default_reminders=request.default_reminders,
        tags=request.tags,
        created_by=request.created_by or str(user.get("display_name") or user.get("email") or ""),
        owner_user_id=str(user.get("user_id") or ""),
        workspace_id=str(workspace.get("workspace_id") or ""),
    )
    return ExperimentDesignTemplateResponse(**template)


@app.get("/experiment-design-templates/{template_id}", response_model=ExperimentDesignTemplateResponse, tags=["experiment-design-templates"])
def experiment_design_template_detail(template_id: str) -> ExperimentDesignTemplateResponse:
    """Return one reusable experiment design template."""

    return ExperimentDesignTemplateResponse(**_experiment_design_template_or_404(SQLiteStore(settings=settings), template_id))


@app.put("/experiment-design-templates/{template_id}", response_model=ExperimentDesignTemplateResponse, tags=["experiment-design-templates"])
def update_experiment_design_template(template_id: str, request: ExperimentDesignTemplateRequest) -> ExperimentDesignTemplateResponse:
    """Update a saved experiment design template."""

    if template_id.startswith("builtin:"):
        raise HTTPException(status_code=400, detail="Built-in design templates cannot be edited directly.")
    store = SQLiteStore(settings=settings)
    if store.get_experiment_design_template(template_id) is None:
        raise HTTPException(status_code=404, detail=f"Experiment design template not found: {template_id}")
    user, workspace = _current_user_workspace_metadata()
    template = store.save_experiment_design_template(
        template_id=template_id,
        name=request.name.strip(),
        description=request.description,
        experiment_type=request.experiment_type,
        default_cell_line_or_model=request.default_cell_line_or_model,
        default_reporters=request.default_reporters,
        default_conditions=request.default_conditions,
        default_events=request.default_events,
        default_reminders=request.default_reminders,
        tags=request.tags,
        created_by=request.created_by or str(user.get("display_name") or user.get("email") or ""),
        owner_user_id=str(user.get("user_id") or ""),
        workspace_id=str(workspace.get("workspace_id") or ""),
    )
    return ExperimentDesignTemplateResponse(**template)


@app.delete("/experiment-design-templates/{template_id}", tags=["experiment-design-templates"])
def delete_experiment_design_template(template_id: str) -> dict[str, object]:
    """Delete a saved experiment design template."""

    if template_id.startswith("builtin:"):
        raise HTTPException(status_code=400, detail="Built-in design templates cannot be deleted.")
    store = SQLiteStore(settings=settings)
    if not store.delete_experiment_design_template(template_id):
        raise HTTPException(status_code=404, detail=f"Experiment design template not found: {template_id}")
    return {"deleted": True, "template_id": template_id}


@app.post("/experiment-design-templates/{template_id}/create-design", response_model=ExperimentDesignResponse, tags=["experiment-design-templates"])
def create_design_from_experiment_design_template(
    template_id: str,
    request: TemplateCreateDesignRequest | None = Body(default=None),
) -> ExperimentDesignResponse:
    """Create a concrete experiment design from a reusable template."""

    template = _experiment_design_template_or_404(SQLiteStore(settings=settings), template_id)
    return _create_design_from_template(template, request or TemplateCreateDesignRequest())


@app.get("/plate-layouts", response_model=list[PlateLayoutResponse], tags=["plate-layouts"])
def plate_layouts(workspace_id: str | None = Query(default=None)) -> list[PlateLayoutResponse]:
    """List saved plate/rack/sample layouts."""

    store = SQLiteStore(settings=settings)
    return [
        PlateLayoutResponse(**layout)
        for layout in store.list_plate_layouts(workspace_id=_current_workspace_id(workspace_id))
    ]


@app.post("/plate-layouts", response_model=PlateLayoutResponse, tags=["plate-layouts"])
def create_plate_layout(request: PlateLayoutRequest) -> PlateLayoutResponse:
    """Create a plate/rack/sample layout manually."""

    store = SQLiteStore(settings=settings)
    return PlateLayoutResponse(**_save_plate_layout_request(store, request))


@app.get("/plate-layouts/{layout_id}", response_model=PlateLayoutResponse, tags=["plate-layouts"])
def plate_layout_detail(layout_id: str) -> PlateLayoutResponse:
    """Return one plate/rack/sample layout."""

    store = SQLiteStore(settings=settings)
    layout = store.get_plate_layout(layout_id)
    if layout is None:
        raise HTTPException(status_code=404, detail=f"Plate layout not found: {layout_id}")
    return PlateLayoutResponse(**layout)


@app.put("/plate-layouts/{layout_id}", response_model=PlateLayoutResponse, tags=["plate-layouts"])
def update_plate_layout(layout_id: str, request: PlateLayoutRequest) -> PlateLayoutResponse:
    """Update one plate/rack/sample layout."""

    store = SQLiteStore(settings=settings)
    if store.get_plate_layout(layout_id) is None:
        raise HTTPException(status_code=404, detail=f"Plate layout not found: {layout_id}")
    return PlateLayoutResponse(**_save_plate_layout_request(store, request, layout_id=layout_id))


@app.delete("/plate-layouts/{layout_id}", tags=["plate-layouts"])
def delete_plate_layout(layout_id: str) -> dict[str, object]:
    """Delete one plate/rack/sample layout."""

    store = SQLiteStore(settings=settings)
    if not store.delete_plate_layout(layout_id):
        raise HTTPException(status_code=404, detail=f"Plate layout not found: {layout_id}")
    return {"deleted": True, "layout_id": layout_id}


@app.post("/experiment-designs/{design_id}/generate-plate-layout", response_model=PlateLayoutResponse, tags=["plate-layouts", "experiment-designs"])
def generate_experiment_design_plate_layout(
    design_id: str,
    request: GeneratePlateLayoutRequest | None = Body(default=None),
) -> PlateLayoutResponse:
    """Generate a practical plate/rack/sample layout from a design."""

    store = SQLiteStore(settings=settings)
    design = _design_or_404(store, design_id)
    payload = request or GeneratePlateLayoutRequest()
    generated = generate_plate_layout(
        design,
        format_name=payload.format,
        rows=payload.rows,
        columns=payload.columns,
        randomized=payload.randomized,
        grouped_by_condition=payload.grouped_by_condition,
        balanced=payload.balanced,
        title=payload.title,
    )
    user, workspace = _current_user_workspace_metadata()
    layout = store.save_plate_layout(
        design_id=design_id,
        title=str(generated["title"]),
        format=str(generated["format"]),
        rows=int(generated["rows"]),
        columns=int(generated["columns"]),
        wells=generated["wells"],
        warnings=generated["warnings"],
        created_by=str(user.get("display_name") or user.get("email") or ""),
        owner_user_id=str(user.get("user_id") or ""),
        workspace_id=str(workspace.get("workspace_id") or ""),
    )
    return PlateLayoutResponse(**layout)


@app.get("/plate-layouts/{layout_id}/export-csv", tags=["plate-layouts"])
def export_plate_layout_csv(layout_id: str) -> Response:
    """Export one plate/rack/sample layout as CSV."""

    store = SQLiteStore(settings=settings)
    layout = store.get_plate_layout(layout_id)
    if layout is None:
        raise HTTPException(status_code=404, detail=f"Plate layout not found: {layout_id}")
    return Response(
        content=plate_layout_to_csv(layout),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="researchos_plate_layout.csv"'},
    )


@app.get("/visual-experiment-builders", response_model=list[VisualExperimentBuilderResponse], tags=["visual-builder"])
def visual_experiment_builders(workspace_id: str | None = Query(default=None)) -> list[VisualExperimentBuilderResponse]:
    """List saved visual experiment builder canvases."""

    store = SQLiteStore(settings=settings)
    return [
        VisualExperimentBuilderResponse(**builder)
        for builder in store.list_visual_experiment_builders(workspace_id=_current_workspace_id(workspace_id))
    ]


@app.post("/visual-experiment-builders", response_model=VisualExperimentBuilderResponse, tags=["visual-builder"])
def create_visual_experiment_builder(request: VisualExperimentBuilderRequest) -> VisualExperimentBuilderResponse:
    """Create a visual experiment builder canvas."""

    store = SQLiteStore(settings=settings)
    return VisualExperimentBuilderResponse(**_save_visual_builder_request(store, request))


@app.get("/visual-experiment-builders/{builder_id}", response_model=VisualExperimentBuilderResponse, tags=["visual-builder"])
def visual_experiment_builder_detail(builder_id: str) -> VisualExperimentBuilderResponse:
    """Return one visual experiment builder canvas."""

    return VisualExperimentBuilderResponse(**_visual_builder_or_404(SQLiteStore(settings=settings), builder_id))


@app.put("/visual-experiment-builders/{builder_id}", response_model=VisualExperimentBuilderResponse, tags=["visual-builder"])
def update_visual_experiment_builder(builder_id: str, request: VisualExperimentBuilderRequest) -> VisualExperimentBuilderResponse:
    """Update one visual experiment builder canvas."""

    store = SQLiteStore(settings=settings)
    _visual_builder_or_404(store, builder_id)
    return VisualExperimentBuilderResponse(**_save_visual_builder_request(store, request, builder_id=builder_id))


@app.delete("/visual-experiment-builders/{builder_id}", tags=["visual-builder"])
def delete_visual_experiment_builder(builder_id: str) -> dict[str, object]:
    """Delete one visual experiment builder canvas."""

    store = SQLiteStore(settings=settings)
    if not store.delete_visual_experiment_builder(builder_id):
        raise HTTPException(status_code=404, detail=f"Visual experiment builder not found: {builder_id}")
    return {"deleted": True, "builder_id": builder_id}


@app.post("/visual-experiment-builders/{builder_id}/compile", tags=["visual-builder"])
def compile_visual_experiment_builder(builder_id: str) -> dict[str, object]:
    """Compile a visual builder into design-compatible payloads without saving a design."""

    builder = _visual_builder_or_404(SQLiteStore(settings=settings), builder_id)
    compiled = compile_visual_builder(
        builder.get("nodes") if isinstance(builder.get("nodes"), list) else [],
        builder.get("connections") if isinstance(builder.get("connections"), list) else [],
    )
    return {"builder_id": builder_id, "compiled": compiled}


@app.post("/visual-experiment-builders/{builder_id}/generate-design", tags=["visual-builder"])
def generate_design_from_visual_experiment_builder(
    builder_id: str,
    request: VisualBuilderGenerateRequest | None = Body(default=None),
) -> dict[str, object]:
    """Generate ExperimentDesign, timeline, reminders, and optional plate layout from a visual builder."""

    store = SQLiteStore(settings=settings)
    builder = _visual_builder_or_404(store, builder_id)
    return _generate_from_visual_builder(store, builder, request or VisualBuilderGenerateRequest())


@app.get("/experiment-designs", response_model=list[ExperimentDesignResponse], tags=["experiment-designs"])
def experiment_designs(
    status: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
) -> list[ExperimentDesignResponse]:
    """List planned experiment designs."""

    store = SQLiteStore(settings=settings)
    return [
        ExperimentDesignResponse(**store.get_experiment_design(str(design["design_id"])))
        for design in store.list_experiment_designs(status=status, workspace_id=_current_workspace_id(workspace_id))
    ]


@app.post("/experiment-designs", response_model=ExperimentDesignResponse, tags=["experiment-designs"])
def create_experiment_design(request: ExperimentDesignRequest) -> ExperimentDesignResponse:
    """Create an experiment design plan."""

    return ExperimentDesignResponse(**_save_experiment_design_request(request))


@app.get("/experiment-designs/due-today", tags=["experiment-designs"])
def experiment_designs_due_today(workspace_id: str | None = Query(default=None)) -> dict[str, object]:
    """Return alert-enabled design events due today."""

    events = due_events(_designs_for_reminders(workspace_id), days=0)
    return {"count": len(events), "events": events}


@app.get("/experiment-designs/upcoming", tags=["experiment-designs"])
def experiment_designs_upcoming(
    days: int = Query(default=7, ge=1, le=365),
    workspace_id: str | None = Query(default=None),
) -> dict[str, object]:
    """Return alert-enabled design events due within a future window."""

    events = due_events(_designs_for_reminders(workspace_id), days=days)
    return {"days": days, "count": len(events), "events": events}


@app.get("/experiment-designs/reminders", tags=["experiment-designs"])
def experiment_design_reminders(
    include_drafts: bool = Query(default=False),
    workspace_id: str | None = Query(default=None),
) -> dict[str, object]:
    """Return all actionable experiment design reminders."""

    reminders = all_reminders(_designs_for_reminders(workspace_id), include_drafts=include_drafts)
    return {"count": len(reminders), "reminders": reminders}


@app.get("/experiment-designs/reminders/due-today", tags=["experiment-designs"])
def experiment_design_reminders_due_today(workspace_id: str | None = Query(default=None)) -> dict[str, object]:
    """Return experiment design reminders due today."""

    events = due_events(_designs_for_reminders(workspace_id), days=0)
    return {"count": len(events), "reminders": events}


@app.get("/experiment-designs/reminders/upcoming", tags=["experiment-designs"])
def experiment_design_reminders_upcoming(
    days: int = Query(default=7, ge=1, le=365),
    workspace_id: str | None = Query(default=None),
) -> dict[str, object]:
    """Return upcoming experiment design reminders."""

    events = due_events(_designs_for_reminders(workspace_id), days=days)
    return {"days": days, "count": len(events), "reminders": events}


@app.get("/experiment-designs/reminders/export-ics", tags=["experiment-designs"])
def export_experiment_design_reminders_ics(
    workspace_id: str | None = Query(default=None),
    include_drafts: bool = Query(default=False),
) -> Response:
    """Export dated experiment design reminders as an importable calendar file."""

    reminders = all_reminders(_designs_for_reminders(workspace_id), include_drafts=include_drafts)
    try:
        calendar_text = reminders_to_ics(reminders, require_all_dates=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=calendar_text,
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="researchos_experiment_design_reminders.ics"'},
    )


@app.post("/experiment-designs/reminders/{event_id}/complete", tags=["experiment-designs"])
def complete_experiment_design_reminder(event_id: str) -> dict[str, object]:
    """Complete a design reminder."""

    return {"event": _update_design_reminder_event(event_id, "completed")}


@app.post("/experiment-designs/reminders/{event_id}/dismiss", tags=["experiment-designs"])
def dismiss_experiment_design_reminder(event_id: str) -> dict[str, object]:
    """Dismiss a design reminder."""

    return {"event": _update_design_reminder_event(event_id, "dismissed")}


@app.post("/experiment-designs/doe/full-factorial", tags=["experiment-designs"])
def experiment_design_full_factorial(request: FullFactorialRequest) -> dict[str, object]:
    """Generate a simple full-factorial condition table."""

    if not request.factors:
        raise HTTPException(status_code=400, detail="At least one factor is required.")
    if any(not levels for levels in request.factors.values()):
        raise HTTPException(status_code=400, detail="Every factor must include at least one level.")
    return full_factorial(request.factors)


@app.post("/experiment-designs/doe/check-balance", tags=["experiment-designs"])
def experiment_design_check_balance(request: BalanceCheckRequest) -> dict[str, object]:
    """Run deterministic balance/control checks on planned conditions."""

    return check_design_balance([condition.model_dump() for condition in request.conditions])


def _import_experiment_design_from_mapping(request: DesignMappedCsvImportRequest) -> ExperimentDesignResponse:
    """Import an experiment design from CSV using explicit or suggested column mappings."""

    if not {"condition_name", "day"}.issubset(set(request.mapping.keys())):
        raise HTTPException(status_code=400, detail="Mapping must include condition_name and day.")
    normalized = import_design_rows(request.csv_text, request.mapping)
    rows = normalized["rows"]
    if not rows:
        raise HTTPException(status_code=400, detail="No rows detected in CSV text.")
    first = rows[0]
    title = request.title or first.get("title") or "Imported experiment design"
    design = create_experiment_design(
        ExperimentDesignRequest(
            title=title,
            experiment_type=request.experiment_type or first.get("experiment_type") or None,
            cell_line_or_model=request.cell_line_or_model or first.get("cell_line_or_model") or None,
            reporters=[item.strip() for item in re.split(r"[;,]", str(first.get("reporters") or "")) if item.strip()],
            description="Imported from mapped CSV design spreadsheet.",
            status="draft",
        )
    )
    store = SQLiteStore(settings=settings)
    conditions_by_name: dict[str, dict[str, object]] = {}
    replicate_counts: dict[str, int] = {}
    for row in rows:
        condition_name = row.get("condition_name") or "Condition"
        replicate_counts[condition_name] = max(
            replicate_counts.get(condition_name, 0),
            int(row.get("replicate") or 1) if str(row.get("replicate") or "").strip().isdigit() else 1,
        )
        if condition_name not in conditions_by_name:
            conditions_by_name[condition_name] = _save_design_condition(
                store,
                design.design_id,
                DesignConditionRequest(
                    condition_name=condition_name,
                    treatment=row.get("treatment") or None,
                    dose=row.get("dose") or None,
                    units=row.get("units") or None,
                    start_day=row.get("day") or None,
                    notes=row.get("notes") or None,
                    replicate_count=replicate_counts[condition_name],
                    sample_count=1,
                ),
            )
        event_type = (row.get("event_type") or "custom").strip().lower().replace(" ", "_")
        event_title = " ".join(
            part
            for part in [
                event_type.replace("_", " ").title(),
                condition_name,
                row.get("sample_id") or "",
            ]
            if part
        )
        notes = row.get("notes") or None
        if row.get("sample_id"):
            notes = " ".join(part for part in [notes, f"Sample ID: {row.get('sample_id')}"] if part)
        _save_design_event(
            store,
            design.design_id,
            DesignEventRequest(
                condition_id=str(conditions_by_name[condition_name]["condition_id"]),
                day=row.get("day") or "D0",
                event_type=event_type,
                title=event_title,
                description=notes,
                alert_enabled=truthy_design_value(row.get("alert_enabled") or row.get("reminder_enabled")),
                reminder_enabled=truthy_design_value(row.get("alert_enabled") or row.get("reminder_enabled")),
            ),
        )
    for condition_name, count in replicate_counts.items():
        condition = conditions_by_name[condition_name]
        if int(condition.get("replicate_count") or 0) != count:
            store.save_design_condition(
                design_id=design.design_id,
                condition_id=str(condition["condition_id"]),
                condition_name=condition_name,
                treatment=condition.get("treatment") if isinstance(condition.get("treatment"), str) else None,
                dose=condition.get("dose") if isinstance(condition.get("dose"), str) else None,
                units=condition.get("units") if isinstance(condition.get("units"), str) else None,
                start_day=condition.get("start_day") if isinstance(condition.get("start_day"), str) else None,
                notes=condition.get("notes") if isinstance(condition.get("notes"), str) else None,
                replicate_count=count,
                sample_count=condition.get("sample_count") if isinstance(condition.get("sample_count"), int) else 1,
            )
    return ExperimentDesignResponse(**_design_or_404(store, design.design_id))


@app.post("/experiment-designs/import-preview", tags=["experiment-designs"])
def preview_experiment_design_import(request: DesignImportRequest) -> dict[str, object]:
    """Preview a CSV design import."""

    return preview_design_import(request.csv_text)


@app.post("/experiment-designs/import-mapped-csv", response_model=ExperimentDesignResponse, tags=["experiment-designs"])
def import_experiment_design_mapped_csv(request: DesignMappedCsvImportRequest) -> ExperimentDesignResponse:
    """Import a design, conditions, and events using explicit field mappings."""

    return _import_experiment_design_from_mapping(request)


@app.post("/experiment-designs/import-csv", response_model=ExperimentDesignResponse, tags=["experiment-designs"])
def import_experiment_design_csv(request: DesignImportRequest) -> ExperimentDesignResponse:
    """Import a design, conditions, and events from spreadsheet-style CSV."""

    preview = preview_design_import(request.csv_text)
    mapping = preview.get("suggested_mappings") or {}
    return _import_experiment_design_from_mapping(
        DesignMappedCsvImportRequest(
            csv_text=request.csv_text,
            mapping=mapping,
            title=request.title,
            experiment_type=request.experiment_type,
            cell_line_or_model=request.cell_line_or_model,
            confirm_overwrite=request.confirm_overwrite,
        )
    )


@app.get("/experiment-designs/import-templates", response_model=list[DesignImportTemplateResponse], tags=["experiment-designs"])
def experiment_design_import_templates(workspace_id: str | None = Query(default=None)) -> list[DesignImportTemplateResponse]:
    """Return default and locally saved experiment design import templates."""

    store = SQLiteStore(settings=settings)
    templates = [DesignImportTemplateResponse(**template) for template in DEFAULT_DESIGN_IMPORT_TEMPLATES]
    templates.extend(
        DesignImportTemplateResponse(**template)
        for template in store.list_design_import_templates(workspace_id=_current_workspace_id(workspace_id))
    )
    return templates


@app.post("/experiment-designs/import-templates", response_model=DesignImportTemplateResponse, tags=["experiment-designs"])
def create_experiment_design_import_template(request: DesignImportTemplateRequest) -> DesignImportTemplateResponse:
    """Save a reusable experiment design import mapping template."""

    user, workspace = _current_user_workspace_metadata()
    store = SQLiteStore(settings=settings)
    template = store.save_design_import_template(
        name=request.name,
        provider=request.provider,
        mapping=request.mapping,
        owner_user_id=str(user.get("user_id") or ""),
        created_by=str(user.get("user_id") or ""),
        workspace_id=str(workspace.get("workspace_id") or ""),
    )
    return DesignImportTemplateResponse(**template)


@app.delete("/experiment-designs/import-templates/{template_id}", tags=["experiment-designs"])
def delete_experiment_design_import_template(template_id: str) -> dict[str, object]:
    """Delete a saved experiment design import template."""

    if template_id.startswith("default:"):
        raise HTTPException(status_code=400, detail="Default import templates cannot be deleted.")
    store = SQLiteStore(settings=settings)
    if not store.delete_design_import_template(template_id):
        raise HTTPException(status_code=404, detail=f"Import template not found: {template_id}")
    return {"deleted": True, "template_id": template_id}


@app.post("/experiment-designs/{design_id}/activate", response_model=ExperimentDesignResponse, tags=["experiment-designs"])
def activate_experiment_design(design_id: str) -> ExperimentDesignResponse:
    """Activate a design so its reminders appear on dashboards/mobile."""

    store = SQLiteStore(settings=settings)
    design = _design_or_404(store, design_id)
    activated = store.save_experiment_design(
        design_id=design_id,
        title=str(design.get("title") or ""),
        experiment_type=design.get("experiment_type"),
        cell_line_or_model=design.get("cell_line_or_model"),
        reporters=design.get("reporters") or [],
        description=design.get("description"),
        start_date=design.get("start_date") or datetime.now(timezone.utc).date().isoformat(),
        created_by=design.get("created_by"),
        linked_experiment_id=design.get("linked_experiment_id"),
        status="active",
        owner_user_id=design.get("owner_user_id"),
        workspace_id=design.get("workspace_id"),
    )
    _publish_event(EventType.PROVIDER_SYNCED, "experiment_designs", {"event": "design_activated", "design_id": design_id})
    return ExperimentDesignResponse(**activated)


@app.get("/experiment-designs/{design_id}", response_model=ExperimentDesignResponse, tags=["experiment-designs"])
def experiment_design_detail(design_id: str) -> ExperimentDesignResponse:
    """Return one design with conditions and events."""

    return ExperimentDesignResponse(**_design_or_404(SQLiteStore(settings=settings), design_id))


@app.put("/experiment-designs/{design_id}", response_model=ExperimentDesignResponse, tags=["experiment-designs"])
def update_experiment_design(design_id: str, request: ExperimentDesignRequest) -> ExperimentDesignResponse:
    """Update one experiment design."""

    store = SQLiteStore(settings=settings)
    _design_or_404(store, design_id)
    return ExperimentDesignResponse(**_save_experiment_design_request(request, design_id=design_id))


@app.delete("/experiment-designs/{design_id}", tags=["experiment-designs"])
def delete_experiment_design(design_id: str) -> dict[str, object]:
    """Delete an experiment design."""

    store = SQLiteStore(settings=settings)
    if not store.delete_experiment_design(design_id):
        raise HTTPException(status_code=404, detail=f"Experiment design not found: {design_id}")
    return {"deleted": True, "design_id": design_id}


@app.post("/experiment-designs/{design_id}/save-template", response_model=ExperimentDesignTemplateResponse, tags=["experiment-designs", "experiment-design-templates"])
def save_experiment_design_as_template(design_id: str, request: SaveDesignAsTemplateRequest | None = Body(default=None)) -> ExperimentDesignTemplateResponse:
    """Save an existing concrete design as a reusable template."""

    store = SQLiteStore(settings=settings)
    design = _design_or_404(store, design_id)
    template = _save_current_design_as_template(store, design, name=request.name if request else None)
    return ExperimentDesignTemplateResponse(**template)


@app.post("/experiment-designs/{design_id}/conditions", tags=["experiment-designs"])
def add_design_condition(design_id: str, request: DesignConditionRequest) -> dict[str, object]:
    """Add a condition to a design."""

    return _save_design_condition(SQLiteStore(settings=settings), design_id, request)


@app.post("/experiment-designs/{design_id}/events", tags=["experiment-designs"])
def add_design_event(design_id: str, request: DesignEventRequest) -> dict[str, object]:
    """Add a timeline event to a design."""

    return _save_design_event(SQLiteStore(settings=settings), design_id, request)


@app.get("/experiment-designs/{design_id}/timeline", tags=["experiment-designs"])
def experiment_design_timeline(design_id: str) -> dict[str, object]:
    """Return a day-by-day design timeline."""

    return build_design_timeline(_design_or_404(SQLiteStore(settings=settings), design_id))


@app.get("/experiment-designs/{design_id}/calendar", tags=["experiment-designs"])
def experiment_design_calendar(design_id: str) -> dict[str, object]:
    """Return a calendar-style design view."""

    return design_calendar(_design_or_404(SQLiteStore(settings=settings), design_id))


@app.get("/experiment-designs/{design_id}/export-csv", tags=["experiment-designs"])
def export_experiment_design_csv(design_id: str) -> Response:
    """Export a design as an Excel-friendly CSV."""

    design = _design_or_404(SQLiteStore(settings=settings), design_id)
    return Response(
        content=design_to_csv(design),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="researchos_experiment_design.csv"'},
    )


@app.get("/experiment-designs/{design_id}/export-ics", tags=["experiment-designs"])
def export_experiment_design_ics(design_id: str) -> Response:
    """Export one design's dated reminders as an importable calendar file."""

    design = _design_or_404(SQLiteStore(settings=settings), design_id)
    try:
        calendar_text = design_to_ics(design)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filename = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(design.get("title") or design_id)).strip("_") or "experiment_design"
    return Response(
        content=calendar_text,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{filename}.ics"'},
    )


@app.get("/experiment-designs/{design_id}/copilot", tags=["experiment-designs"])
def experiment_design_copilot(design_id: str) -> dict[str, object]:
    """Return deterministic design-quality checks for Research Copilot."""

    design = _design_or_404(SQLiteStore(settings=settings), design_id)
    return copilot_design_checks(design)


@app.get("/purchase-requests", response_model=list[PurchaseRequestResponse], tags=["purchasing"])
def purchase_requests(
    status: str | None = Query(default=None),
    query: str | None = Query(default=None),
    linked_inventory_item_id: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
) -> list[PurchaseRequestResponse]:
    """List lab purchase requests before Oracle/manual purchasing."""

    store = SQLiteStore(settings=settings)
    return [
        PurchaseRequestResponse(**record)
        for record in store.list_purchase_requests(
            status=status,
            query=query,
            linked_inventory_item_id=linked_inventory_item_id,
            workspace_id=_current_workspace_id(workspace_id),
        )
    ]


@app.post("/purchase-requests", response_model=PurchaseRequestResponse, tags=["purchasing"])
def create_purchase_request(request: PurchaseRequestRequest) -> PurchaseRequestResponse:
    """Create a draft or submitted lab purchase request."""

    return PurchaseRequestResponse(**_save_purchase_request_workflow(request))


@app.get("/purchase-requests/export-csv", tags=["purchasing"])
def export_purchase_requests_csv(workspace_id: str | None = Query(default=None)) -> Response:
    """Export purchase requests for boss/admin review."""

    store = SQLiteStore(settings=settings)
    csv_text = records_to_csv(
        store.list_purchase_requests(workspace_id=_current_workspace_id(workspace_id)),
        PURCHASE_REQUEST_CSV_FIELDS,
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="researchos_purchase_requests.csv"'},
    )


@app.get("/purchase-requests/{request_id}", response_model=PurchaseRequestResponse, tags=["purchasing"])
def purchase_request_detail(request_id: str) -> PurchaseRequestResponse:
    """Return one lab purchase request."""

    store = SQLiteStore(settings=settings)
    record = store.get_purchase_request(request_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Purchase request not found: {request_id}")
    return PurchaseRequestResponse(**record)


@app.put("/purchase-requests/{request_id}", response_model=PurchaseRequestResponse, tags=["purchasing"])
def update_purchase_request(request_id: str, request: PurchaseRequestRequest) -> PurchaseRequestResponse:
    """Update one lab purchase request."""

    store = SQLiteStore(settings=settings)
    if store.get_purchase_request(request_id) is None:
        raise HTTPException(status_code=404, detail=f"Purchase request not found: {request_id}")
    return PurchaseRequestResponse(**_save_purchase_request_workflow(request, request_id=request_id))


@app.post("/purchase-requests/{request_id}/submit", response_model=PurchaseRequestResponse, tags=["purchasing"])
def submit_purchase_request(request_id: str) -> PurchaseRequestResponse:
    """Submit a purchase request for boss/admin review."""

    return PurchaseRequestResponse(**_purchase_request_with_status(request_id, "submitted"))


@app.post("/purchase-requests/{request_id}/approve", response_model=PurchaseRequestResponse, tags=["purchasing"])
def approve_purchase_request(request_id: str) -> PurchaseRequestResponse:
    """Approve a purchase request for manual Oracle ordering."""

    return PurchaseRequestResponse(**_purchase_request_with_status(request_id, "approved"))


@app.post("/purchase-requests/{request_id}/mark-ordered", response_model=PurchaseRequestResponse, tags=["purchasing"])
def mark_purchase_request_ordered(request_id: str) -> PurchaseRequestResponse:
    """Mark a purchase request as ordered in Oracle/manual purchasing."""

    return PurchaseRequestResponse(**_purchase_request_with_status(request_id, "ordered"))


@app.post("/purchase-requests/{request_id}/mark-received", response_model=PurchaseRequestResponse, tags=["purchasing"])
def mark_purchase_request_received(
    request_id: str,
    request: PurchaseRequestReceiveRequest | None = None,
) -> PurchaseRequestResponse:
    """Mark a request received and optionally create receiving/intake records."""

    store = SQLiteStore(settings=settings)
    updated = _purchase_request_with_status(request_id, "received")
    receiving: dict[str, object] | None = None
    if request and request.create_receiving_record:
        receiving = _receiving_from_purchase_request(updated)
    if request and request.update_inventory_quantity and updated.get("linked_inventory_item_id"):
        quantity = updated.get("quantity_requested")
        if quantity is not None:
            store.update_inventory_quantity(str(updated["linked_inventory_item_id"]), float(quantity))
    if receiving:
        _publish_event(
            EventType.PROVIDER_SYNCED,
            "inventory",
            {"event": "purchase_request_received", "request_id": request_id, "receiving_id": receiving.get("receiving_id")},
        )
    return PurchaseRequestResponse(**updated)


@app.get("/receiving", response_model=list[ReceivingRecordResponse], tags=["purchasing", "inventory"])
def receiving_records(
    query: str | None = Query(default=None),
    purchase_request_id: str | None = Query(default=None),
    purchase_record_id: str | None = Query(default=None),
    inventory_item_id: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
) -> list[ReceivingRecordResponse]:
    """List receiving/intake records."""

    store = SQLiteStore(settings=settings)
    return [
        ReceivingRecordResponse(**record)
        for record in store.list_receiving_records(
            query=query,
            purchase_request_id=purchase_request_id,
            purchase_record_id=purchase_record_id,
            inventory_item_id=inventory_item_id,
            workspace_id=_current_workspace_id(workspace_id),
        )
    ]


@app.post("/receiving", response_model=ReceivingRecordResponse, tags=["purchasing", "inventory"])
def create_receiving_record(request: ReceivingRecordRequest) -> ReceivingRecordResponse:
    """Create a receiving record for ordered items arriving in the lab."""

    return ReceivingRecordResponse(**_save_receiving_request(request))


@app.get("/receiving/export-csv", tags=["purchasing", "inventory"])
def export_receiving_csv(workspace_id: str | None = Query(default=None)) -> Response:
    """Export receiving records as CSV."""

    store = SQLiteStore(settings=settings)
    csv_text = records_to_csv(
        store.list_receiving_records(workspace_id=_current_workspace_id(workspace_id)),
        RECEIVING_CSV_FIELDS,
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="researchos_receiving.csv"'},
    )


@app.get("/receiving/{receiving_id}", response_model=ReceivingRecordResponse, tags=["purchasing", "inventory"])
def receiving_detail(receiving_id: str) -> ReceivingRecordResponse:
    """Return one receiving/intake record."""

    store = SQLiteStore(settings=settings)
    record = store.get_receiving_record(receiving_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Receiving record not found: {receiving_id}")
    return ReceivingRecordResponse(**record)


@app.put("/receiving/{receiving_id}", response_model=ReceivingRecordResponse, tags=["purchasing", "inventory"])
def update_receiving_record(receiving_id: str, request: ReceivingRecordRequest) -> ReceivingRecordResponse:
    """Update one receiving/intake record."""

    store = SQLiteStore(settings=settings)
    if store.get_receiving_record(receiving_id) is None:
        raise HTTPException(status_code=404, detail=f"Receiving record not found: {receiving_id}")
    return ReceivingRecordResponse(**_save_receiving_request(request, receiving_id=receiving_id))


@app.post("/receiving/{receiving_id}/create-or-update-inventory", tags=["purchasing", "inventory"])
def create_or_update_inventory_from_receiving(
    receiving_id: str,
    request: ReceivingInventoryIntakeRequest | None = None,
) -> dict[str, object]:
    """Create a new inventory item or update linked inventory from receiving."""

    return _intake_receiving_record(receiving_id, update_existing=True if request is None else request.update_existing)


@app.get("/purchases", response_model=list[PurchaseRecordResponse], tags=["purchasing"])
def purchases(
    vendor: str | None = Query(default=None),
    grant_or_funding_source: str | None = Query(default=None),
    status: str | None = Query(default=None),
    query: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
) -> list[PurchaseRecordResponse]:
    """List local purchase records."""

    store = SQLiteStore(settings=settings)
    return [
        PurchaseRecordResponse(**record)
        for record in store.list_purchase_records(
            vendor=vendor,
            grant_or_funding_source=grant_or_funding_source,
            status=status,
            query=query,
            workspace_id=_current_workspace_id(workspace_id),
        )
    ]


@app.post("/purchases", response_model=PurchaseRecordResponse, tags=["purchasing"])
def create_purchase(request: PurchaseRecordRequest) -> PurchaseRecordResponse:
    """Create a purchase record."""

    return PurchaseRecordResponse(**_save_purchase_request(request))


@app.get("/purchases/export-csv", tags=["purchasing"])
def export_purchases_csv(workspace_id: str | None = Query(default=None)) -> Response:
    """Export purchases as a spreadsheet-compatible CSV."""

    store = SQLiteStore(settings=settings)
    csv_text = records_to_csv(
        store.list_purchase_records(workspace_id=_current_workspace_id(workspace_id)),
        PURCHASE_CSV_FIELDS,
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="researchos_purchases.csv"'},
    )


@app.get("/purchases/summary", tags=["purchasing"])
def purchases_summary(workspace_id: str | None = Query(default=None)) -> dict[str, object]:
    """Return grant, vendor, month, total, and recent purchase summaries."""

    store = SQLiteStore(settings=settings)
    records = store.list_purchase_records(workspace_id=_current_workspace_id(workspace_id))
    return purchase_summary(records)


@app.get("/purchases/by-grant", tags=["purchasing"])
def purchases_by_grant(workspace_id: str | None = Query(default=None)) -> dict[str, object]:
    """Return purchase spend grouped by grant or funding source."""

    store = SQLiteStore(settings=settings)
    records = store.list_purchase_records(workspace_id=_current_workspace_id(workspace_id))
    summary = purchase_summary(records)
    return {
        "total_spend": summary["total_spend"],
        "purchase_count": summary["purchase_count"],
        "grants": summary["spend_by_grant"],
    }


@app.post("/purchases/import-csv", tags=["purchasing"])
def import_purchases_csv(request: PurchaseCsvImportRequest) -> dict[str, object]:
    """Import Oracle/exported purchasing CSV rows into local purchase records."""

    if request.provider != "oracle_purchasing":
        raise HTTPException(status_code=400, detail="Only oracle_purchasing CSV imports are scaffolded currently.")
    imported = []
    for row in parse_csv_text(request.csv_text):
        normalized = normalize_purchase_csv_row(row)
        if not normalized.get("item_name"):
            continue
        imported.append(_save_purchase_request(PurchaseRecordRequest(**normalized)))
    return {
        "provider": ORACLE_PURCHASING_PROVIDER,
        "imported_count": len(imported),
        "records": imported,
    }


@app.post("/purchases/import-preview", tags=["purchasing"])
def preview_purchases_import(request: PurchaseImportPreviewRequest) -> dict[str, object]:
    """Preview a purchasing CSV and suggest flexible field mappings."""

    return purchase_import_preview(request.csv_text)


@app.post("/purchases/import-mapped-csv", tags=["purchasing"])
def import_purchases_mapped_csv(request: PurchaseMappedCsvImportRequest) -> dict[str, object]:
    """Import purchasing CSV rows using an explicit ResearchOS field mapping."""

    if request.provider != "oracle_purchasing":
        raise HTTPException(status_code=400, detail="Only oracle_purchasing mapped CSV imports are scaffolded currently.")
    if "item_name" not in request.mapping:
        raise HTTPException(status_code=400, detail="Mapping must include item_name.")
    imported = []
    skipped_rows: list[dict[str, object]] = []
    for index, row in enumerate(parse_csv_text(request.csv_text), start=1):
        mapped = apply_purchase_mapping(row, request.mapping)
        if not mapped.get("item_name"):
            skipped_rows.append({"row": index, "reason": "Missing item_name after mapping."})
            continue
        imported.append(_save_purchase_request(PurchaseRecordRequest(**mapped)))
    return {
        "provider": ORACLE_PURCHASING_PROVIDER,
        "mapping": request.mapping,
        "imported_count": len(imported),
        "skipped_count": len(skipped_rows),
        "skipped_rows": skipped_rows,
        "records": imported,
    }


@app.get("/purchases/import-templates", response_model=list[PurchaseImportTemplateResponse], tags=["purchasing"])
def purchase_import_templates(workspace_id: str | None = Query(default=None)) -> list[PurchaseImportTemplateResponse]:
    """Return default and locally saved purchasing import mapping templates."""

    store = SQLiteStore(settings=settings)
    templates = [PurchaseImportTemplateResponse(**template) for template in DEFAULT_PURCHASE_IMPORT_TEMPLATES]
    templates.extend(
        PurchaseImportTemplateResponse(**template)
        for template in store.list_purchase_import_templates(workspace_id=_current_workspace_id(workspace_id))
    )
    return templates


@app.post("/purchases/import-templates", response_model=PurchaseImportTemplateResponse, tags=["purchasing"])
def create_purchase_import_template(request: PurchaseImportTemplateRequest) -> PurchaseImportTemplateResponse:
    """Save a reusable purchasing import mapping template."""

    user, workspace = _current_user_workspace_metadata()
    store = SQLiteStore(settings=settings)
    template = store.save_purchase_import_template(
        name=request.name,
        provider=request.provider,
        mapping=request.mapping,
        owner_user_id=str(user.get("user_id") or ""),
        created_by=str(user.get("user_id") or ""),
        workspace_id=str(workspace.get("workspace_id") or ""),
    )
    return PurchaseImportTemplateResponse(**template)


@app.delete("/purchases/import-templates/{template_id}", tags=["purchasing"])
def delete_purchase_import_template(template_id: str) -> dict[str, object]:
    """Delete a saved purchasing import mapping template."""

    if template_id.startswith("default:"):
        raise HTTPException(status_code=400, detail="Default import templates cannot be deleted.")
    store = SQLiteStore(settings=settings)
    if not store.delete_purchase_import_template(template_id):
        raise HTTPException(status_code=404, detail=f"Import template not found: {template_id}")
    return {"deleted": True, "template_id": template_id}


@app.get("/purchases/{purchase_id}", response_model=PurchaseRecordResponse, tags=["purchasing"])
def purchase_detail(purchase_id: str) -> PurchaseRecordResponse:
    """Return one purchase record."""

    store = SQLiteStore(settings=settings)
    record = store.get_purchase_record(purchase_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Purchase record not found: {purchase_id}")
    return PurchaseRecordResponse(**record)


@app.put("/purchases/{purchase_id}", response_model=PurchaseRecordResponse, tags=["purchasing"])
def update_purchase(purchase_id: str, request: PurchaseRecordRequest) -> PurchaseRecordResponse:
    """Update one purchase record."""

    store = SQLiteStore(settings=settings)
    if store.get_purchase_record(purchase_id) is None:
        raise HTTPException(status_code=404, detail=f"Purchase record not found: {purchase_id}")
    return PurchaseRecordResponse(**_save_purchase_request(request, purchase_id=purchase_id))


@app.get("/assets", response_model=list[AssetResponse], tags=["assets"])
def assets(
    asset_type: AssetType | None = Query(default=None),
    query: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
) -> list[AssetResponse]:
    """List registered research assets with optional type/search filters."""

    store = SQLiteStore(settings=settings)
    resolved_workspace_id = _current_workspace_id(workspace_id)
    return [
        AssetResponse(**_asset_with_link_info(store, asset))
        for asset in store.list_assets(asset_type=asset_type, query=query, workspace_id=resolved_workspace_id)
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


@app.get("/memory", tags=["memory"])
def memory_index(workspace_id: str | None = Query(default=None)) -> dict[str, object]:
    """Return Scientific Memory index status for the active workspace."""

    resolved_workspace_id = _current_workspace_id(workspace_id)
    return ScientificMemoryService(settings=settings, workspace_id=resolved_workspace_id).summary()


@app.get("/memory/experiment/{experiment_id:path}", tags=["memory"])
def memory_experiment(experiment_id: str, workspace_id: str | None = Query(default=None)) -> dict[str, object]:
    """Return one experiment's deterministic Scientific Memory vectors."""

    resolved_workspace_id = _current_workspace_id(workspace_id)
    try:
        return ScientificMemoryService(settings=settings, workspace_id=resolved_workspace_id).experiment_memory(experiment_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/memory/similar", tags=["memory"])
def memory_similar(request: MemorySimilarRequest, workspace_id: str | None = Query(default=None)) -> dict[str, object]:
    """Return similar experiments and related memory context."""

    resolved_workspace_id = _current_workspace_id(workspace_id)
    try:
        return ScientificMemoryService(settings=settings, workspace_id=resolved_workspace_id).similar_payload(
            request.experiment_id,
            limit=request.limit,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/experiments", response_model=list[ExperimentResponse], tags=["experiments"])
def experiments(workspace_id: str | None = Query(default=None)) -> list[ExperimentResponse]:
    """List structured experiments extracted from research documents."""

    store = SQLiteStore(settings=settings)
    resolved_workspace_id = _current_workspace_id(workspace_id)
    return [
        ExperimentResponse(**_experiment_with_assets(store, experiment))
        for experiment in store.list_experiments(workspace_id=resolved_workspace_id)
    ]


@app.post("/experiments/create", tags=["experiments"])
def create_experiment(request: NewExperimentWizardRequest) -> dict[str, object]:
    """Create a planned experiment from the New Experiment Wizard."""

    return _create_experiment_from_wizard(request, mobile=False)


def _general_experiment_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ExperimentConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ExperimentAuthorizationError):
        return HTTPException(status_code=404, detail="Experiment not found.")
    if isinstance(exc, ExperimentValidationError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@app.get("/experiment-creation-modes", tags=["experiments"])
def experiment_creation_modes() -> dict[str, object]:
    """Return supported and future-ready experiment creation modes."""

    return {
        "fully_implemented": [
            {"id": "blank", "label": "Blank Experiment", "description": "Start with a free-form notebook and optional structured plan."},
            {"id": "protocol", "label": "Start from Protocol", "description": "Select a protocol version and inherit linked timeline events."},
            {"id": "guided_builder", "label": "Guided Builder", "description": "Create basics, cohorts, conditions, interventions, and timeline events."},
            {"id": "describe", "label": "Describe Experiment", "description": "Use Experiment Design Copilot to turn narrative text or voice transcripts into a reviewed draft."},
        ],
        "placeholders": [
            {"id": "import_spreadsheet", "label": "Import Spreadsheet", "description": "Future mapped design import into the generalized schema."},
        ],
    }


@app.get("/general-protocols", tags=["experiments", "protocols"])
def general_protocols() -> list[dict[str, object]]:
    return _general_experiment_service().list_protocols()


def _protocol_hub_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProtocolHubValidationError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@app.get("/protocol-hub/protocols", tags=["protocol-hub"])
def protocol_hub_protocols(q: str | None = Query(default=None)) -> list[dict[str, object]]:
    """List structured, versioned Protocol Hub protocols."""

    return _protocol_hub_service().list_protocols(query=q)


@app.get("/protocol-hub/templates", tags=["protocol-hub"])
def protocol_hub_templates() -> list[dict[str, object]]:
    """Return section-only protocol templates."""

    return _protocol_hub_service().protocol_templates()


@app.get("/protocol-hub/meyer-onboarding", tags=["protocol-hub"])
def protocol_hub_meyer_onboarding() -> dict[str, object]:
    """Return the intentionally incomplete Meyer draft onboarding payload."""

    return _protocol_hub_service().meyer_onboarding()


@app.post("/protocol-hub/create-blank", tags=["protocol-hub"])
def create_blank_protocol_hub_protocol(request_body: ProtocolHubBlankRequest, request: Request) -> dict[str, object]:
    """Create an incomplete blank protocol draft."""

    try:
        return _protocol_hub_service().create_blank_protocol(
            actor_user_id=_request_user_id(request),
            lab_id=request_body.lab_id,
            title=request_body.title,
            category=request_body.category,
            biological_system=request_body.biological_system,
            sample_unit=request_body.sample_unit,
            version_number=request_body.version_number,
            content=request_body.content,
        )
    except ProtocolHubValidationError as exc:
        raise _protocol_hub_http_error(exc)


@app.post("/protocol-hub/imports", tags=["protocol-hub"])
def create_protocol_hub_import(request_body: ProtocolHubImportRequest, request: Request) -> dict[str, object]:
    """Store protocol import metadata without embedding large binary content."""

    return _protocol_hub_service().create_import(
        actor_user_id=_request_user_id(request),
        lab_id=request_body.lab_id,
        source_type=request_body.source_type,
        original_filename=request_body.original_filename,
        storage_reference=request_body.storage_reference,
        mime_type=request_body.mime_type,
    )


@app.post("/protocol-hub/drafts/from-text", tags=["protocol-hub"])
def create_protocol_hub_text_draft(request_body: ProtocolHubTextDraftRequest, request: Request) -> dict[str, object]:
    """Create a reviewable protocol extraction draft from pasted, described, or imported text."""

    try:
        return _protocol_hub_service().create_extraction_draft_from_text(
            actor_user_id=_request_user_id(request),
            lab_id=request_body.lab_id,
            source_text=request_body.source_text,
            origin=request_body.origin,
            proposed_title=request_body.proposed_title,
            proposed_category=request_body.proposed_category,
            source_citation=request_body.source_citation,
            import_id=request_body.import_id,
        )
    except ProtocolHubValidationError as exc:
        raise _protocol_hub_http_error(exc)


@app.post("/protocol-hub/drafts/describe", tags=["protocol-hub"])
def describe_protocol_hub_draft(request_body: ProtocolHubTextDraftRequest, request: Request) -> dict[str, object]:
    """Create a protocol draft from a plain-language description or voice transcript."""

    try:
        return _protocol_hub_service().create_extraction_draft_from_text(
            actor_user_id=_request_user_id(request),
            lab_id=request_body.lab_id,
            source_text=request_body.source_text,
            origin="voice" if request_body.origin == "voice" else "manual",
            proposed_title=request_body.proposed_title,
            proposed_category=request_body.proposed_category,
            source_citation=request_body.source_citation,
            import_id=request_body.import_id,
        )
    except ProtocolHubValidationError as exc:
        raise _protocol_hub_http_error(exc)


@app.get("/protocol-hub/drafts/{extraction_id}", tags=["protocol-hub"])
def protocol_hub_draft(extraction_id: str) -> dict[str, object]:
    try:
        return _protocol_hub_service().get_extraction_draft(extraction_id)
    except ProtocolHubValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.put("/protocol-hub/drafts/{extraction_id}", tags=["protocol-hub"])
def update_protocol_hub_draft(extraction_id: str, request_body: ProtocolHubDraftUpdateRequest) -> dict[str, object]:
    try:
        return _protocol_hub_service().update_extraction_draft(
            extraction_id,
            {key: value for key, value in request_body.model_dump().items() if value is not None},
        )
    except ProtocolHubValidationError as exc:
        raise _protocol_hub_http_error(exc)


@app.post("/protocol-hub/drafts/{extraction_id}/approve", tags=["protocol-hub"])
def approve_protocol_hub_draft(extraction_id: str, request_body: ProtocolHubDraftApproveRequest, request: Request) -> dict[str, object]:
    try:
        return _protocol_hub_service().approve_extraction_draft(
            actor_user_id=_request_user_id(request),
            extraction_id=extraction_id,
            version_label=request_body.version_label,
            confirmed=request_body.confirmed,
            target_protocol_id=request_body.target_protocol_id,
        )
    except ProtocolHubValidationError as exc:
        raise _protocol_hub_http_error(exc)


@app.post("/protocol-hub/protocols", tags=["protocol-hub"])
def create_protocol_hub_protocol(request_body: ProtocolHubCreateRequest, request: Request) -> dict[str, object]:
    """Create or update a structured protocol with an initial version."""

    try:
        return _protocol_hub_service().create_or_update_protocol(
            actor_user_id=_request_user_id(request),
            lab_id=request_body.lab_id,
            title=request_body.title,
            short_name=request_body.short_name,
            description=request_body.description,
            category=request_body.category,
            biological_system=request_body.biological_system,
            sample_unit=request_body.sample_unit,
            version_number=request_body.version_number,
            summary_of_changes=request_body.summary_of_changes,
            content=request_body.content,
            events=list(request_body.events),
            materials=list(request_body.materials),
            media=list(request_body.media),
            expected_results=list(request_body.expected_results),
            troubleshooting=list(request_body.troubleshooting),
        )
    except ProtocolHubValidationError as exc:
        raise _protocol_hub_http_error(exc)


@app.get("/protocol-hub/protocols/{protocol_id}", tags=["protocol-hub"])
def protocol_hub_protocol(protocol_id: str) -> dict[str, object]:
    protocol = _protocol_hub_service().get_protocol(protocol_id)
    if protocol is None:
        raise HTTPException(status_code=404, detail="Protocol not found.")
    return protocol


@app.get("/protocol-hub/versions/{protocol_version_id}", tags=["protocol-hub"])
def protocol_hub_version_workspace(protocol_version_id: str) -> dict[str, object]:
    try:
        return _protocol_hub_service().version_workspace(protocol_version_id)
    except ProtocolHubValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/protocol-hub/protocols/{protocol_id}/versions", tags=["protocol-hub"])
def create_protocol_hub_version(protocol_id: str, request_body: ProtocolHubVersionRequest, request: Request) -> dict[str, object]:
    try:
        return _protocol_hub_service().create_version(
            actor_user_id=_request_user_id(request),
            protocol_id=protocol_id,
            version_number=request_body.version_number,
            summary_of_changes=request_body.summary_of_changes,
            content=request_body.content,
            events=list(request_body.events),
        )
    except ProtocolHubValidationError as exc:
        raise _protocol_hub_http_error(exc)


@app.get("/protocol-hub/protocols/{protocol_id}/usage", tags=["protocol-hub"])
def protocol_hub_usage(protocol_id: str) -> dict[str, object]:
    return _protocol_hub_service().usage_statistics(protocol_id)


@app.get("/protocol-hub/compare", tags=["protocol-hub"])
def protocol_hub_compare(left_version_id: str = Query(...), right_version_id: str = Query(...)) -> dict[str, object]:
    try:
        return _protocol_hub_service().compare_versions(left_version_id, right_version_id)
    except ProtocolHubValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/protocol-hub/search", tags=["protocol-hub"])
def protocol_hub_search(q: str = Query(...)) -> dict[str, object]:
    return _protocol_hub_service().search(q)


@app.put("/protocol-hub/notebooks/{document_id}", tags=["protocol-hub"])
def save_protocol_hub_notebook(document_id: str, request_body: ProtocolNotebookSaveRequest, request: Request) -> dict[str, object]:
    try:
        user_id = _request_user_id(request)
        notebook = _protocol_hub_service().save_notebook(
            actor_user_id=user_id,
            document_id=document_id,
            current_version=request_body.current_version,
            content=request_body.content,
        )
        try:
            _research_object_service().sync_text_references(
                user_id=user_id,
                source_object_id=document_id,
                source_object_type="Notebook Entry",
                text=request_body.content,
            )
        except Exception:
            logger.debug("Protocol notebook object reference sync failed.", exc_info=True)
        return notebook
    except ProtocolHubValidationError as exc:
        raise _protocol_hub_http_error(exc)


@app.get("/general-protocols/{protocol_id}", tags=["experiments", "protocols"])
def general_protocol_detail(protocol_id: str) -> dict[str, object]:
    protocol = _general_experiment_service().get_protocol(protocol_id)
    if protocol is None:
        raise HTTPException(status_code=404, detail="Protocol not found.")
    return protocol


@app.get("/general-protocol-versions/{protocol_version_id}", tags=["experiments", "protocols"])
def general_protocol_version(protocol_version_id: str) -> dict[str, object]:
    version = _general_experiment_service().get_protocol_version(protocol_version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Protocol version not found.")
    return version


@app.post("/experiments/general", tags=["experiments"])
def create_general_experiment(request_body: GeneralExperimentCreateRequest, request: Request) -> dict[str, object]:
    service = _general_experiment_service()
    try:
        experiment = service.create_blank_experiment(
            actor_user_id=_request_user_id(request),
            lab_id=request_body.lab_id,
            title=request_body.title,
            experiment_id=request_body.experiment_id,
            short_description=request_body.short_description,
            biological_system=request_body.biological_system,
            sample_unit_type=request_body.sample_unit_type,
            start_date=request_body.start_date,
            expected_end_day=request_body.expected_end_day,
            status=request_body.status,
        )
        return {"experiment": experiment}
    except (ExperimentAuthorizationError, ExperimentValidationError, ExperimentConflictError) as exc:
        raise _general_experiment_http_error(exc)


@app.post("/experiments/notebook-first", tags=["experiments"])
def create_notebook_first_experiment(request_body: NotebookFirstExperimentCreateRequest, request: Request) -> dict[str, object]:
    """Immediately create an empty notebook-first experiment workspace."""

    service = _general_experiment_service()
    user_id = _request_user_id(request)
    title = (request_body.title or "").strip()
    if not title:
        title = f"Untitled Experiment {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    try:
        experiment = service.create_blank_experiment(
            actor_user_id=user_id,
            lab_id=request_body.lab_id,
            title=title,
            experiment_id=request_body.experiment_id,
            status="draft",
        )
        workspace = service.get_workspace(str(experiment["experiment_id"]), user_id)
        if request_body.initial_note and workspace:
            notebook = workspace.get("notebook") if isinstance(workspace.get("notebook"), dict) else {}
            content = str(notebook.get("content") or "")
            appended = f"{content.rstrip()}\n\n{request_body.initial_note.strip()}\n"
            service.save_notebook(
                user_id=user_id,
                document_id=str(notebook.get("document_id")),
                current_version=int(notebook.get("version") or 1),
                content=appended,
            )
            workspace = service.get_workspace(str(experiment["experiment_id"]), user_id)
        return {
            "experiment": experiment,
            "workspace": workspace,
            "open_to": "notebook",
            "philosophy": "notebook_first",
        }
    except (ExperimentAuthorizationError, ExperimentValidationError, ExperimentConflictError) as exc:
        raise _general_experiment_http_error(exc)


@app.post("/experiments/general/from-protocol", tags=["experiments"])
def create_general_experiment_from_protocol(request_body: GeneralExperimentFromProtocolRequest, request: Request) -> dict[str, object]:
    service = _general_experiment_service()
    try:
        experiment = service.create_from_protocol(
            actor_user_id=_request_user_id(request),
            protocol_id=request_body.protocol_id,
            protocol_version_id=request_body.protocol_version_id,
            title=request_body.title,
            lab_id=request_body.lab_id,
            experiment_id=request_body.experiment_id,
        )
        return {"experiment": experiment}
    except (ExperimentAuthorizationError, ExperimentValidationError, ExperimentConflictError) as exc:
        raise _general_experiment_http_error(exc)


@app.post("/experiments/{experiment_id}/protocols/attach", tags=["experiments"])
def attach_protocol_to_experiment(experiment_id: str, request_body: GeneralProtocolAttachRequest, request: Request) -> dict[str, object]:
    """Attach a protocol to an existing notebook-first workspace."""

    service = _general_experiment_service()
    user_id = _request_user_id(request)
    try:
        link = service.link_protocol(
            actor_user_id=user_id,
            experiment_id=experiment_id,
            protocol_id=request_body.protocol_id,
            protocol_version_id=request_body.protocol_version_id,
            relationship=request_body.relationship,
            inherit_events=request_body.inherit_events,
        )
        if request_body.insert_summary_note:
            protocol = service.get_protocol(request_body.protocol_id) or {}
            notebook = service.get_or_create_notebook(user_id, experiment_id)
            summary = (
                f"\n\n## Attached Protocol\n\n"
                f"- Protocol: {protocol.get('title') or request_body.protocol_id}\n"
                f"- Version: {request_body.protocol_version_id}\n"
                f"- Timeline inherited: {'yes' if request_body.inherit_events else 'no'}\n"
                "Researcher-selected protocol attachment; notebook content was not overwritten.\n"
            )
            service.save_notebook(
                user_id=user_id,
                document_id=str(notebook["document_id"]),
                current_version=int(notebook["version"]),
                content=f"{str(notebook.get('content') or '').rstrip()}{summary}",
            )
        workspace = service.get_workspace(experiment_id, user_id)
        return {"link": link, "workspace": workspace}
    except (ExperimentAuthorizationError, ExperimentValidationError, ExperimentConflictError) as exc:
        raise _general_experiment_http_error(exc)


@app.put("/experiments/{experiment_id}/general", tags=["experiments"])
def update_general_experiment(experiment_id: str, request_body: GeneralExperimentUpdateRequest, request: Request) -> dict[str, object]:
    service = _general_experiment_service()
    user_id = _request_user_id(request)
    try:
        if request_body.title is None:
            raise ExperimentValidationError("No supported experiment fields were provided.")
        experiment = service.update_experiment_title(
            actor_user_id=user_id,
            experiment_id=experiment_id,
            title=request_body.title,
        )
        workspace = service.get_workspace(experiment_id, user_id)
        return {"experiment": experiment, "workspace": workspace}
    except (ExperimentAuthorizationError, ExperimentValidationError, ExperimentConflictError) as exc:
        raise _general_experiment_http_error(exc)


@app.get("/experiments/{experiment_id}/general-workspace", tags=["experiments"])
def general_experiment_workspace(experiment_id: str, request: Request) -> dict[str, object]:
    workspace = _general_experiment_service().get_workspace(experiment_id, _request_user_id(request))
    if workspace is None:
        raise HTTPException(status_code=404, detail="Experiment not found.")
    return workspace


@app.post("/experiments/{experiment_id}/cohorts", tags=["experiments"])
def add_general_cohort(experiment_id: str, request_body: GeneralCohortRequest, request: Request) -> dict[str, object]:
    try:
        return _general_experiment_service().add_cohort(_request_user_id(request), experiment_id, request_body.model_dump())
    except (ExperimentAuthorizationError, ExperimentValidationError, ExperimentConflictError) as exc:
        raise _general_experiment_http_error(exc)


@app.post("/experiments/{experiment_id}/conditions", tags=["experiments"])
def add_general_condition(experiment_id: str, request_body: GeneralConditionRequest, request: Request) -> dict[str, object]:
    try:
        return _general_experiment_service().add_condition(_request_user_id(request), experiment_id, request_body.model_dump())
    except (ExperimentAuthorizationError, ExperimentValidationError, ExperimentConflictError) as exc:
        raise _general_experiment_http_error(exc)


@app.post("/experiments/{experiment_id}/interventions", tags=["experiments"])
def add_general_intervention(experiment_id: str, request_body: GeneralInterventionRequest, request: Request) -> dict[str, object]:
    try:
        return _general_experiment_service().add_intervention(_request_user_id(request), experiment_id, request_body.model_dump())
    except (ExperimentAuthorizationError, ExperimentValidationError, ExperimentConflictError) as exc:
        raise _general_experiment_http_error(exc)


@app.post("/experiments/{experiment_id}/events", tags=["experiments"])
def add_general_event(experiment_id: str, request_body: GeneralEventRequest, request: Request) -> dict[str, object]:
    try:
        return _general_experiment_service().add_event(_request_user_id(request), experiment_id, request_body.model_dump())
    except (ExperimentAuthorizationError, ExperimentValidationError, ExperimentConflictError) as exc:
        raise _general_experiment_http_error(exc)


@app.get("/experiments/{experiment_id}/general-timeline", tags=["experiments"])
def general_experiment_timeline(experiment_id: str, request: Request) -> dict[str, object]:
    try:
        return _general_experiment_service().timeline(experiment_id, _request_user_id(request))
    except (ExperimentAuthorizationError, ExperimentValidationError, ExperimentConflictError) as exc:
        raise _general_experiment_http_error(exc)


@app.get("/experiments/{experiment_id}/notebook", tags=["experiments"])
def general_experiment_notebook(experiment_id: str, request: Request) -> dict[str, object]:
    try:
        return _general_experiment_service().get_or_create_notebook(_request_user_id(request), experiment_id)
    except (ExperimentAuthorizationError, ExperimentValidationError, ExperimentConflictError) as exc:
        raise _general_experiment_http_error(exc)


@app.put("/experiment-notebooks/{document_id}", tags=["experiments"])
def save_general_experiment_notebook(document_id: str, request_body: NotebookSaveRequest, request: Request) -> dict[str, object]:
    try:
        user_id = _request_user_id(request)
        notebook = _general_experiment_service().save_notebook(
            user_id=user_id,
            document_id=document_id,
            current_version=request_body.current_version,
            content=request_body.content,
            document_format=request_body.document_format,
            title=request_body.title,
        )
        try:
            _research_object_service().sync_text_references(
                user_id=user_id,
                source_object_id=document_id,
                source_object_type="Notebook Entry",
                text=request_body.content,
            )
        except Exception:
            logger.debug("Experiment notebook object reference sync failed.", exc_info=True)
        return notebook
    except (ExperimentAuthorizationError, ExperimentValidationError, ExperimentConflictError) as exc:
        raise _general_experiment_http_error(exc)


@app.post("/experiment-notebooks/{document_id}/attachments", tags=["experiments"])
def add_general_experiment_notebook_attachment(document_id: str, request_body: NotebookAttachmentRequest, request: Request) -> dict[str, object]:
    try:
        return _general_experiment_service().add_notebook_attachment(_request_user_id(request), document_id, request_body.model_dump())
    except (ExperimentAuthorizationError, ExperimentValidationError, ExperimentConflictError) as exc:
        raise _general_experiment_http_error(exc)


@app.post("/experiment-extraction-drafts", tags=["experiments"])
def experiment_extraction_draft(request_body: ExtractionDraftRequest, request: Request) -> dict[str, object]:
    try:
        return _general_experiment_service().create_extraction_draft(_request_user_id(request), request_body.model_dump())
    except (ExperimentAuthorizationError, ExperimentValidationError, ExperimentConflictError) as exc:
        raise _general_experiment_http_error(exc)


def _experiment_copilot_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ExperimentCopilotError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@app.get("/experiment-copilot/demo-narrative", tags=["experiments"])
def experiment_copilot_demo_narrative() -> dict[str, str]:
    """Return the retinal organoid SAG demo narrative."""

    return _experiment_design_copilot().demo_narrative()


@app.post("/experiment-copilot/draft", tags=["experiments"])
def experiment_copilot_create_draft(request_body: ExperimentCopilotDraftRequest, request: Request) -> dict[str, object]:
    """Convert narrative scientific text into a review-only draft experiment."""

    try:
        return _experiment_design_copilot().create_draft(
            user_id=_request_user_id(request),
            narrative=request_body.narrative,
            source_type=request_body.source_type,
            lab_id=request_body.lab_id,
        )
    except ExperimentCopilotError as exc:
        raise _experiment_copilot_http_error(exc)


@app.get("/experiment-copilot/drafts/{session_id}", tags=["experiments"])
def experiment_copilot_get_draft(session_id: str, request: Request) -> dict[str, object]:
    """Return a copilot draft session for the current user."""

    try:
        return _experiment_design_copilot().get_draft(_request_user_id(request), session_id)
    except ExperimentCopilotError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/experiment-copilot/drafts/{session_id}/clarify", tags=["experiments"])
def experiment_copilot_clarify(session_id: str, request_body: ExperimentCopilotClarifyRequest, request: Request) -> dict[str, object]:
    """Apply clarification answers to a draft and update readiness for approval."""

    try:
        return _experiment_design_copilot().answer_clarifications(
            _request_user_id(request),
            session_id,
            dict(request_body.answers),
        )
    except ExperimentCopilotError as exc:
        raise _experiment_copilot_http_error(exc)


@app.post("/experiment-copilot/drafts/{session_id}/approve", tags=["experiments"])
def experiment_copilot_approve(session_id: str, request_body: ExperimentCopilotApproveRequest, request: Request) -> dict[str, object]:
    """Create a structured draft experiment only after explicit researcher approval."""

    try:
        return _experiment_design_copilot().approve_draft(
            _request_user_id(request),
            session_id,
            title=request_body.title,
            experiment_id=request_body.experiment_id,
        )
    except ExperimentCopilotError as exc:
        raise _experiment_copilot_http_error(exc)


@app.post("/sample-planning/preview", tags=["experiments"])
def sample_planning_preview(request_body: SamplePlanningPreviewRequest) -> dict[str, object]:
    return SamplePlanningService().preview(dict(request_body.assumptions))


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


@app.get("/experiments/{experiment_id}/quantification", tags=["experiments"])
def experiment_quantification_workspace(experiment_id: str, use_ai: bool = Query(False)) -> dict[str, object]:
    """Return the Quantification Workspace for one experiment."""

    workspace = quantification_workspace_service.build(experiment_id, use_ai=use_ai)
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Quantification workspace not found: {experiment_id}")
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
