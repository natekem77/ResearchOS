"""Built-in deterministic ResearchOS scientific agents."""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent, RefreshMixin
from app.events.event_models import EventType, ResearchOSEvent


class NotebookAgent(BaseAgent):
    """Tracks notebook imports and extracted experiments."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="notebook_agent",
            name="Notebook Agent",
            description="Tracks notebook imports and experiment extraction events.",
            event_types={EventType.NOTEBOOK_IMPORTED, EventType.EXPERIMENT_EXTRACTED, EventType.DRAFT_CREATED},
        )


class SessionAgent(BaseAgent):
    """Tracks live experiment sessions and session timelines."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="session_agent",
            name="Session Agent",
            description="Tracks session starts, session timeline updates, and session endings.",
            event_types={EventType.SESSION_STARTED, EventType.SESSION_EVENT_APPENDED, EventType.SESSION_ENDED},
        )


class StatisticsAgent(BaseAgent):
    """Detects when quantitative provider outputs should generate statistics."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="statistics_agent",
            name="Statistics Agent",
            description="Reacts to GraphPad and spreadsheet parsed events and emits statistics updates.",
            event_types={EventType.GRAPHPAD_PARSED, EventType.SPREADSHEET_PARSED},
        )
        self._emitted_for: set[str] = set()

    def run(self, event: ResearchOSEvent) -> list[ResearchOSEvent]:
        key = str(event.payload.get("asset_id") or event.event_id)
        if key in self._emitted_for:
            return []
        self._emitted_for.add(key)
        return [
            ResearchOSEvent(
                event_type=EventType.STATISTICS_GENERATED,
                source=self.agent_id,
                payload={"source_event_id": event.event_id, **event.payload},
                correlation_id=event.correlation_id or event.event_id,
            )
        ]


class KnowledgeGraphAgent(RefreshMixin, BaseAgent):
    """Refreshes the Knowledge Graph after new scientific evidence arrives."""

    def __init__(self, refreshable: Any | None = None) -> None:
        super().__init__(
            agent_id="knowledge_graph_agent",
            name="Knowledge Graph Agent",
            description="Refreshes Knowledge Graph cache from deterministic provider metadata.",
            event_types={
                EventType.NOTEBOOK_IMPORTED,
                EventType.EXPERIMENT_EXTRACTED,
                EventType.ASSET_REGISTERED,
                EventType.ASSET_LINKED,
                EventType.SPREADSHEET_PARSED,
                EventType.GRAPHPAD_PARSED,
                EventType.STATISTICS_GENERATED,
                EventType.IMAGE_IMPORTED,
                EventType.LITERATURE_IMPORTED,
                EventType.SESSION_EVENT_APPENDED,
            },
            refreshable=refreshable,
        )

    def run(self, event: ResearchOSEvent) -> list[ResearchOSEvent]:
        del event
        self.refresh()
        return []


class ImageAgent(BaseAgent):
    """Tracks microscopy and image import events."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="image_agent",
            name="Image Agent",
            description="Tracks image and microscopy imports.",
            event_types={EventType.IMAGE_IMPORTED},
        )


class LiteratureAgent(BaseAgent):
    """Tracks literature imports."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="literature_agent",
            name="Literature Agent",
            description="Tracks literature imports for downstream graph/search refreshes.",
            event_types={EventType.LITERATURE_IMPORTED},
        )


class ProtocolAgent(BaseAgent):
    """Tracks protocol-relevant imports and assets."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="protocol_agent",
            name="Protocol Agent",
            description="Tracks protocol-like notebook and asset events without editing protocols.",
            event_types={EventType.NOTEBOOK_IMPORTED, EventType.ASSET_REGISTERED, EventType.PROVIDER_SYNCED},
        )
