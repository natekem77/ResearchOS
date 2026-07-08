"""Typed event models for ResearchOS automation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


class EventType(StrEnum):
    """Canonical ResearchOS event names.

    Values intentionally match the milestone terminology so logs and future
    integrations can use stable event names.
    """

    NOTEBOOK_IMPORTED = "NotebookImported"
    EXPERIMENT_EXTRACTED = "ExperimentExtracted"
    ASSET_REGISTERED = "AssetRegistered"
    ASSET_LINKED = "AssetLinked"
    SPREADSHEET_PARSED = "SpreadsheetParsed"
    GRAPHPAD_PARSED = "GraphPadParsed"
    STATISTICS_GENERATED = "StatisticsGenerated"
    IMAGE_IMPORTED = "ImageImported"
    LITERATURE_IMPORTED = "LiteratureImported"
    KNOWLEDGE_GRAPH_UPDATED = "KnowledgeGraphUpdated"
    WORKSPACE_UPDATED = "WorkspaceUpdated"
    TIMELINE_UPDATED = "TimelineUpdated"
    DRAFT_CREATED = "DraftCreated"
    PROVIDER_SYNCED = "ProviderSynced"
    SESSION_STARTED = "SessionStarted"
    SESSION_EVENT_APPENDED = "SessionEventAppended"
    SESSION_ENDED = "SessionEnded"
    LIFECYCLE_TRANSITIONED = "LifecycleTransitioned"
    WORKFLOW_TRANSITIONED = "WorkflowTransitioned"
    WORKFLOW_NOTE_ADDED = "WorkflowNoteAdded"
    DASHBOARD_UPDATED = "DashboardUpdated"
    SEARCH_INDEX_UPDATED = "SearchIndexUpdated"


@dataclass(frozen=True)
class ResearchOSEvent:
    """One immutable event published by a ResearchOS provider or service."""

    event_type: EventType
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: f"event:{uuid4().hex}")
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    correlation_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation for tests, logs, and diagnostics."""

        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "source": self.source,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
        }
