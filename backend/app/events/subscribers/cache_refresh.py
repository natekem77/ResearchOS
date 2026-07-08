"""Subscribers that refresh provider-agnostic derived services."""

from __future__ import annotations

from typing import Protocol

from app.events.event_models import ResearchOSEvent


class Refreshable(Protocol):
    """Minimal cache refresh protocol used by automation subscribers."""

    def refresh(self) -> object:
        """Invalidate or rebuild local cache state."""


class CacheRefreshSubscriber:
    """Refresh a derived service whenever upstream provider data changes."""

    def __init__(self, service: Refreshable, name: str) -> None:
        self.service = service
        self.name = name
        self.events_seen: list[str] = []

    def __call__(self, event: ResearchOSEvent) -> None:
        self.events_seen.append(event.event_id)
        self.service.refresh()
