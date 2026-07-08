"""Tests for the ResearchOS event bus and automation engine."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.events.automation_engine import AutomationEngine
from app.events.event_bus import EventBus
from app.events.event_models import EventType, ResearchOSEvent
from app.global_knowledge_graph import KnowledgeGraphService
from app.research_document import DocumentChunk, ResearchDocument
from app.storage import SQLiteStore


class RefreshCounter:
    """Tiny refreshable service used to verify automation subscriptions."""

    def __init__(self) -> None:
        self.count = 0

    def refresh(self) -> None:
        self.count += 1


class EventBusTests(unittest.TestCase):
    """Event publication should be ordered, idempotent, and provider-agnostic."""

    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def test_event_ordering_and_duplicate_suppression(self) -> None:
        bus = EventBus()
        seen: list[str] = []
        bus.subscribe(EventType.ASSET_REGISTERED, lambda event: seen.append(event.event_type.value))
        first = ResearchOSEvent(event_type=EventType.ASSET_REGISTERED, source="test", event_id="event:fixed")
        second = ResearchOSEvent(event_type=EventType.ASSET_REGISTERED, source="test", event_id="event:fixed")

        self.assertTrue(bus.publish(first))
        self.assertFalse(bus.publish(second))

        self.assertEqual(seen, ["AssetRegistered"])
        self.assertEqual([event.event_id for event in bus.history()], ["event:fixed"])

    def test_automation_engine_publishes_derived_events_in_order(self) -> None:
        bus = EventBus()
        graph = RefreshCounter()
        search = RefreshCounter()
        dashboard = RefreshCounter()
        engine = AutomationEngine(
            event_bus=bus,
            refreshables={"knowledge_graph": graph, "search_index": search, "dashboard": dashboard},
        )
        engine.start()

        bus.publish(ResearchOSEvent(event_type=EventType.SPREADSHEET_PARSED, source="spreadsheet", event_id="event:sheet"))

        event_names = [event.event_type.value for event in bus.history()]
        self.assertEqual(
            event_names,
            [
                "SpreadsheetParsed",
                "KnowledgeGraphUpdated",
                "WorkspaceUpdated",
                "TimelineUpdated",
                "DashboardUpdated",
                "SearchIndexUpdated",
            ],
        )
        self.assertEqual(graph.count, 1)
        self.assertEqual(search.count, 1)
        self.assertEqual(dashboard.count, 1)

    def test_automation_engine_does_not_duplicate_derived_processing(self) -> None:
        bus = EventBus()
        graph = RefreshCounter()
        engine = AutomationEngine(event_bus=bus, refreshables={"knowledge_graph": graph})
        engine.start()
        event = ResearchOSEvent(event_type=EventType.IMAGE_IMPORTED, source="microscopy", event_id="event:image")

        bus.publish(event)
        bus.publish(event)

        self.assertEqual(graph.count, 1)
        self.assertEqual([item.event_type.value for item in bus.history()].count("KnowledgeGraphUpdated"), 1)

    def test_graph_workspace_and_timeline_update_events_are_emitted(self) -> None:
        bus = EventBus()
        updates: list[str] = []
        bus.subscribe(EventType.KNOWLEDGE_GRAPH_UPDATED, lambda event: updates.append(event.event_type.value))
        bus.subscribe(EventType.WORKSPACE_UPDATED, lambda event: updates.append(event.event_type.value))
        bus.subscribe(EventType.TIMELINE_UPDATED, lambda event: updates.append(event.event_type.value))
        engine = AutomationEngine(event_bus=bus)
        engine.start()

        bus.publish(ResearchOSEvent(event_type=EventType.ASSET_LINKED, source="assets"))

        self.assertEqual(updates, ["KnowledgeGraphUpdated", "WorkspaceUpdated", "TimelineUpdated"])

    def test_knowledge_graph_refreshes_after_import_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            graph = KnowledgeGraphService(settings=settings, store=store)
            bus = EventBus()
            engine = AutomationEngine(event_bus=bus, refreshables={"knowledge_graph": graph})
            engine.start()
            self.assertEqual(graph.summary()["entity_count"], 0)

            document = ResearchDocument(
                id="doc:event",
                provider="markdown",
                source_id="event.md",
                title="Event-driven SAG note",
                content="SAG and SIX6 were recorded in this notebook entry.",
                metadata={"entities": {"compound": ["SAG"], "marker": ["SIX6"]}},
            )
            store.upsert_document(
                document,
                [DocumentChunk(id="chunk:event", document_id=document.id, chunk_index=0, text=document.content, token_estimate=10)],
            )
            bus.publish(ResearchOSEvent(event_type=EventType.NOTEBOOK_IMPORTED, source="markdown", payload={"document_id": document.id}))

            detail = graph.entity_detail("SAG")

        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["entity"], "SAG")


if __name__ == "__main__":
    unittest.main()
