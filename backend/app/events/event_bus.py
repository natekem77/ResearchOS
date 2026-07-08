"""Synchronous in-process event bus for ResearchOS.

The implementation is intentionally small and synchronous for the local-first
MVP. The public API mirrors an async/event-stream future: providers publish
events and subscribers register handlers by event type.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from threading import RLock

from app.events.event_models import EventType, ResearchOSEvent

logger = logging.getLogger(__name__)
EventHandler = Callable[[ResearchOSEvent], None]


class EventBus:
    """Simple synchronous event bus with idempotent event processing."""

    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._wildcard_subscribers: list[EventHandler] = []
        self._processed_event_ids: set[str] = set()
        self._history: list[ResearchOSEvent] = []
        self._lock = RLock()

    def subscribe(self, event_type: EventType | str | None, handler: EventHandler) -> None:
        """Register a handler for one event type, or all events with ``None``."""

        resolved = _resolve_event_type(event_type)
        with self._lock:
            target = self._wildcard_subscribers if resolved is None else self._subscribers[resolved]
            if handler not in target:
                target.append(handler)

    def unsubscribe(self, event_type: EventType | str | None, handler: EventHandler) -> None:
        """Remove a previously registered handler."""

        resolved = _resolve_event_type(event_type)
        with self._lock:
            target = self._wildcard_subscribers if resolved is None else self._subscribers[resolved]
            if handler in target:
                target.remove(handler)

    def publish(self, event: ResearchOSEvent) -> bool:
        """Publish one event.

        Returns ``True`` when the event was processed. Duplicate ``event_id``
        values are ignored and return ``False``.
        """

        with self._lock:
            if event.event_id in self._processed_event_ids:
                logger.debug("Skipping duplicate ResearchOS event %s", event.event_id)
                return False
            self._processed_event_ids.add(event.event_id)
            self._history.append(event)
            handlers = [*self._subscribers.get(event.event_type, []), *self._wildcard_subscribers]

        logger.debug("Publishing ResearchOS event %s from %s", event.event_type.value, event.source)
        for handler in handlers:
            handler(event)
        return True

    def history(self) -> list[ResearchOSEvent]:
        """Return processed events in publication order."""

        with self._lock:
            return list(self._history)

    def clear(self) -> None:
        """Clear subscribers and processed events.

        This is intended for tests. Application code should usually create one
        process-level bus and keep it for the lifetime of the backend.
        """

        with self._lock:
            self._subscribers.clear()
            self._wildcard_subscribers.clear()
            self._processed_event_ids.clear()
            self._history.clear()


_GLOBAL_EVENT_BUS = EventBus()


def get_event_bus() -> EventBus:
    """Return the process-local ResearchOS event bus."""

    return _GLOBAL_EVENT_BUS


def _resolve_event_type(event_type: EventType | str | None) -> EventType | None:
    if event_type is None:
        return None
    if isinstance(event_type, EventType):
        return event_type
    return EventType(event_type)
