"""Automation engine that connects provider events to derived ResearchOS layers."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.events.event_bus import EventBus
from app.events.event_models import EventType, ResearchOSEvent

logger = logging.getLogger(__name__)

UPSTREAM_EVENTS = {
    EventType.NOTEBOOK_IMPORTED,
    EventType.EXPERIMENT_EXTRACTED,
    EventType.ASSET_REGISTERED,
    EventType.ASSET_LINKED,
    EventType.SPREADSHEET_PARSED,
    EventType.GRAPHPAD_PARSED,
    EventType.STATISTICS_GENERATED,
    EventType.IMAGE_IMPORTED,
    EventType.LITERATURE_IMPORTED,
    EventType.DRAFT_CREATED,
    EventType.PROVIDER_SYNCED,
    EventType.SESSION_STARTED,
    EventType.SESSION_EVENT_APPENDED,
    EventType.SESSION_ENDED,
    EventType.WORKFLOW_TRANSITIONED,
    EventType.WORKFLOW_NOTE_ADDED,
}


@dataclass
class AutomationEngine:
    """Synchronous automation layer built on top of the EventBus."""

    event_bus: EventBus
    refreshables: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._started = False
        self._processed_event_ids: set[str] = set()
        self._derived_by_correlation: set[tuple[str, EventType]] = set()
        self._event_counts: dict[str, int] = defaultdict(int)

    def start(self) -> None:
        """Subscribe the automation engine to provider/source events."""

        if self._started:
            return
        for event_type in UPSTREAM_EVENTS:
            self.event_bus.subscribe(event_type, self.handle_event)
        self._started = True

    def stop(self) -> None:
        """Unsubscribe the automation engine."""

        if not self._started:
            return
        for event_type in UPSTREAM_EVENTS:
            self.event_bus.unsubscribe(event_type, self.handle_event)
        self._started = False

    def handle_event(self, event: ResearchOSEvent) -> None:
        """Process one source event and publish derived update events."""

        if event.event_id in self._processed_event_ids:
            return
        self._processed_event_ids.add(event.event_id)
        self._event_counts[event.event_type.value] += 1

        self._refresh("knowledge_graph")
        self._refresh("search_index")
        self._refresh("dashboard")

        self._publish_once(event, EventType.KNOWLEDGE_GRAPH_UPDATED, {"reason": event.event_type.value})
        self._publish_once(event, EventType.WORKSPACE_UPDATED, {"reason": event.event_type.value})
        self._publish_once(event, EventType.TIMELINE_UPDATED, {"reason": event.event_type.value})
        self._publish_once(event, EventType.DASHBOARD_UPDATED, {"reason": event.event_type.value})
        self._publish_once(event, EventType.SEARCH_INDEX_UPDATED, {"reason": event.event_type.value})

    def status(self) -> dict[str, Any]:
        """Return automation diagnostics without exposing private data."""

        return {
            "started": self._started,
            "processed_event_count": len(self._processed_event_ids),
            "event_counts": dict(self._event_counts),
            "refreshables": sorted(self.refreshables),
        }

    def _refresh(self, name: str) -> None:
        service = self.refreshables.get(name)
        refresh = getattr(service, "refresh", None)
        if callable(refresh):
            refresh()

    def _publish_once(self, source_event: ResearchOSEvent, event_type: EventType, payload: dict[str, Any]) -> None:
        correlation_id = source_event.correlation_id or source_event.event_id
        key = (correlation_id, event_type)
        if key in self._derived_by_correlation:
            return
        self._derived_by_correlation.add(key)
        derived = ResearchOSEvent(
            event_type=event_type,
            source="automation_engine",
            payload={
                **payload,
                "source_event_id": source_event.event_id,
                "source": source_event.source,
                "source_payload": source_event.payload,
            },
            correlation_id=correlation_id,
        )
        self.event_bus.publish(derived)
