"""Base classes for deterministic ResearchOS scientific agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from app.events.event_models import EventType, ResearchOSEvent


class ScientificAgent(Protocol):
    """Minimal interface implemented by deterministic workflow agents."""

    agent_id: str
    name: str
    enabled: bool
    event_types: set[EventType]

    def handle_event(self, event: ResearchOSEvent) -> list[ResearchOSEvent]:
        """React deterministically to one event."""

    def status(self) -> dict[str, Any]:
        """Return agent diagnostics."""


@dataclass
class BaseAgent:
    """Base deterministic agent with status tracking and failure isolation."""

    agent_id: str
    name: str
    description: str
    event_types: set[EventType]
    enabled: bool = True
    run_count: int = 0
    error_count: int = 0
    last_run: str | None = None
    last_error: str | None = None
    last_event_type: str | None = None
    actions: list[str] = field(default_factory=list)

    def can_handle(self, event: ResearchOSEvent) -> bool:
        """Return whether this enabled agent should handle an event."""

        return self.enabled and event.event_type in self.event_types

    def handle_event(self, event: ResearchOSEvent) -> list[ResearchOSEvent]:
        """Run the agent and update diagnostics."""

        self.run_count += 1
        self.last_run = datetime.now(timezone.utc).isoformat()
        self.last_event_type = event.event_type.value
        self.last_error = None
        try:
            emitted = self.run(event)
            self.actions.append(f"{event.event_type.value}:{len(emitted)}")
            self.actions = self.actions[-12:]
            return emitted
        except Exception as exc:
            self.error_count += 1
            self.last_error = str(exc)
            raise

    def run(self, event: ResearchOSEvent) -> list[ResearchOSEvent]:
        """Override in subclasses to perform deterministic work."""

        del event
        return []

    def status(self) -> dict[str, Any]:
        """Return API-safe agent status."""

        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "event_types": sorted(event_type.value for event_type in self.event_types),
            "run_count": self.run_count,
            "error_count": self.error_count,
            "last_run": self.last_run,
            "last_error": self.last_error,
            "last_event_type": self.last_event_type,
            "actions": list(self.actions),
        }


class RefreshMixin:
    """Mixin for agents that refresh a cache-backed service."""

    refreshable_name: str = ""

    def __init__(self, *args: Any, refreshable: Any | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.refreshable = refreshable

    def refresh(self) -> None:
        refresh = getattr(self.refreshable, "refresh", None)
        if callable(refresh):
            refresh()
