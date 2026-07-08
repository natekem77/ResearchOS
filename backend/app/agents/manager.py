"""Agent manager for deterministic ResearchOS scientific agents."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.agents.base import ScientificAgent
from app.agents.default_agents import (
    ImageAgent,
    KnowledgeGraphAgent,
    LiteratureAgent,
    NotebookAgent,
    ProtocolAgent,
    SessionAgent,
    StatisticsAgent,
)
from app.events.event_bus import EventBus
from app.events.event_models import ResearchOSEvent

logger = logging.getLogger(__name__)


@dataclass
class AgentManager:
    """Register, enable, disable, list, and dispatch deterministic agents."""

    event_bus: EventBus
    agents: dict[str, ScientificAgent] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    started: bool = False
    handled_event_ids: set[str] = field(default_factory=set)
    failures: list[dict[str, Any]] = field(default_factory=list)

    def start(self) -> None:
        """Subscribe manager to the EventBus."""

        if self.started:
            return
        self.event_bus.subscribe(None, self.handle_event)
        self.started = True

    def stop(self) -> None:
        """Unsubscribe manager from the EventBus."""

        if not self.started:
            return
        self.event_bus.unsubscribe(None, self.handle_event)
        self.started = False

    def register_agent(self, agent: ScientificAgent) -> None:
        """Register or replace a deterministic agent."""

        self.agents[agent.agent_id] = agent
        if agent.agent_id not in self.order:
            self.order.append(agent.agent_id)

    def enable_agent(self, agent_id: str) -> bool:
        """Enable an agent by ID."""

        agent = self.agents.get(agent_id)
        if agent is None:
            return False
        agent.enabled = True
        return True

    def disable_agent(self, agent_id: str) -> bool:
        """Disable an agent by ID."""

        agent = self.agents.get(agent_id)
        if agent is None:
            return False
        agent.enabled = False
        return True

    def list_agents(self) -> list[dict[str, Any]]:
        """Return agent statuses in registration order."""

        return [self.agents[agent_id].status() for agent_id in self.order if agent_id in self.agents]

    def handle_event(self, event: ResearchOSEvent) -> None:
        """Dispatch one event to enabled agents in registration order."""

        if event.event_id in self.handled_event_ids:
            return
        self.handled_event_ids.add(event.event_id)
        emitted_events: list[ResearchOSEvent] = []
        for agent_id in list(self.order):
            agent = self.agents.get(agent_id)
            if agent is None or not agent.can_handle(event):
                continue
            try:
                emitted_events.extend(agent.handle_event(event))
            except Exception as exc:
                logger.warning("ResearchOS agent %s failed on %s: %s", agent_id, event.event_type.value, exc)
                self.failures.append(
                    {
                        "agent_id": agent_id,
                        "event_id": event.event_id,
                        "event_type": event.event_type.value,
                        "error": str(exc),
                    }
                )
                self.failures = self.failures[-25:]
        for emitted in emitted_events:
            self.event_bus.publish(emitted)

    def status(self) -> dict[str, Any]:
        """Return manager and agent diagnostics."""

        return {
            "started": self.started,
            "agent_count": len(self.agents),
            "enabled_count": sum(1 for agent in self.agents.values() if agent.enabled),
            "handled_event_count": len(self.handled_event_ids),
            "agents": self.list_agents(),
            "failures": list(self.failures),
        }


def create_default_agent_manager(event_bus: EventBus, refreshables: dict[str, Any] | None = None) -> AgentManager:
    """Create the default deterministic scientific agent set."""

    refreshables = refreshables or {}
    manager = AgentManager(event_bus=event_bus)
    for agent in [
        NotebookAgent(),
        SessionAgent(),
        StatisticsAgent(),
        KnowledgeGraphAgent(refreshable=refreshables.get("knowledge_graph")),
        ImageAgent(),
        LiteratureAgent(),
        ProtocolAgent(),
    ]:
        manager.register_agent(agent)
    return manager
