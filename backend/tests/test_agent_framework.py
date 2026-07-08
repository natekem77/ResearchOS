"""Tests for deterministic Scientific Agent framework."""

from __future__ import annotations

import unittest

from app.agents.base import BaseAgent
from app.agents.default_agents import KnowledgeGraphAgent, StatisticsAgent
from app.agents.manager import AgentManager, create_default_agent_manager
from app.events.event_bus import EventBus
from app.events.event_models import EventType, ResearchOSEvent


class RecordingAgent(BaseAgent):
    """Records event handling order for tests."""

    def __init__(self, agent_id: str, events: list[str], fail: bool = False) -> None:
        super().__init__(
            agent_id=agent_id,
            name=agent_id,
            description="test agent",
            event_types={EventType.NOTEBOOK_IMPORTED},
        )
        self.events = events
        self.fail = fail

    def run(self, event: ResearchOSEvent) -> list[ResearchOSEvent]:
        self.events.append(self.agent_id)
        if self.fail:
            raise RuntimeError("agent failure")
        return []


class RefreshCounter:
    """Refreshable test double."""

    def __init__(self) -> None:
        self.count = 0

    def refresh(self) -> None:
        self.count += 1


class AgentFrameworkTests(unittest.TestCase):
    """Scientific agents should be deterministic event subscribers."""

    def test_registration_enable_disable_and_list(self) -> None:
        bus = EventBus()
        manager = AgentManager(event_bus=bus)
        agent = RecordingAgent("agent_a", [])
        manager.register_agent(agent)

        self.assertEqual(manager.list_agents()[0]["agent_id"], "agent_a")
        self.assertTrue(manager.disable_agent("agent_a"))
        self.assertFalse(manager.list_agents()[0]["enabled"])
        self.assertTrue(manager.enable_agent("agent_a"))
        self.assertTrue(manager.list_agents()[0]["enabled"])
        self.assertFalse(manager.enable_agent("missing"))

    def test_multiple_agents_run_in_registration_order(self) -> None:
        bus = EventBus()
        calls: list[str] = []
        manager = AgentManager(event_bus=bus)
        manager.register_agent(RecordingAgent("first", calls))
        manager.register_agent(RecordingAgent("second", calls))
        manager.start()

        bus.publish(ResearchOSEvent(event_type=EventType.NOTEBOOK_IMPORTED, source="test"))

        self.assertEqual(calls, ["first", "second"])

    def test_disabled_agent_does_not_run(self) -> None:
        bus = EventBus()
        calls: list[str] = []
        manager = AgentManager(event_bus=bus)
        manager.register_agent(RecordingAgent("disabled", calls))
        manager.disable_agent("disabled")
        manager.start()

        bus.publish(ResearchOSEvent(event_type=EventType.NOTEBOOK_IMPORTED, source="test"))

        self.assertEqual(calls, [])

    def test_agent_failure_is_captured_and_does_not_stop_other_agents(self) -> None:
        bus = EventBus()
        calls: list[str] = []
        manager = AgentManager(event_bus=bus)
        manager.register_agent(RecordingAgent("bad", calls, fail=True))
        manager.register_agent(RecordingAgent("good", calls))
        manager.start()

        with self.assertLogs("app.agents.manager", level="WARNING"):
            bus.publish(ResearchOSEvent(event_type=EventType.NOTEBOOK_IMPORTED, source="test"))

        self.assertEqual(calls, ["bad", "good"])
        self.assertEqual(manager.status()["failures"][0]["agent_id"], "bad")
        self.assertEqual(manager.list_agents()[0]["error_count"], 1)

    def test_statistics_agent_emits_statistics_generated_event(self) -> None:
        bus = EventBus()
        manager = AgentManager(event_bus=bus)
        manager.register_agent(StatisticsAgent())
        manager.start()

        bus.publish(
            ResearchOSEvent(
                event_type=EventType.GRAPHPAD_PARSED,
                source="graphpad",
                payload={"asset_id": "asset:stats"},
                event_id="event:graphpad",
            )
        )

        self.assertIn("StatisticsGenerated", [event.event_type.value for event in bus.history()])

    def test_knowledge_graph_agent_refreshes_cache(self) -> None:
        bus = EventBus()
        refreshable = RefreshCounter()
        manager = AgentManager(event_bus=bus)
        manager.register_agent(KnowledgeGraphAgent(refreshable=refreshable))
        manager.start()

        bus.publish(ResearchOSEvent(event_type=EventType.IMAGE_IMPORTED, source="microscopy"))

        self.assertEqual(refreshable.count, 1)

    def test_default_agent_manager_contains_initial_agents(self) -> None:
        manager = create_default_agent_manager(EventBus())
        ids = {agent["agent_id"] for agent in manager.list_agents()}

        self.assertTrue(
            {
                "notebook_agent",
                "session_agent",
                "statistics_agent",
                "knowledge_graph_agent",
                "image_agent",
                "literature_agent",
                "protocol_agent",
            }.issubset(ids)
        )


if __name__ == "__main__":
    unittest.main()
