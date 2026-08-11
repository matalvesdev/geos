"""Event bus (SPEC-004, ADR-0003). In-process dispatch + SQLite persisted log.

Business event types (spec §49) are declared as constants so domains share one vocabulary.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Protocol

from ..storage.database import Database
from ..storage.repos import Event, EventRepository
from ..util import new_id, now_iso

logger = logging.getLogger("geos.events")


# --- Named business events (spec §49) ---------------------------------------------
class EventTypes:
    PRODUCT_FEATURE_RELEASED = "product.feature.released"
    DOCS_UPDATED = "docs.updated"
    BLOG_PUBLISHED = "blog.published"
    CONTENT_PUBLISHED = "content.published"
    CONTENT_SCHEDULED = "content.scheduled"
    USER_ACTIVATED = "user.activated"
    EXPERIMENT_COMPLETED = "experiment.completed"
    COMMUNITY_QUESTION_CREATED = "community.question.created"
    KEYWORD_RANK_CHANGED = "keyword.rank.changed"
    LEAD_CREATED = "lead.created"
    LEAD_UPDATED = "lead.updated"
    LEAD_QUALIFIED = "lead.qualified"
    LEAD_MEETING_READY = "lead.meeting_ready"
    MEETING_CREATED = "meeting.created"
    MEETING_COMPLETED = "meeting.completed"
    OPPORTUNITY_CREATED = "opportunity.created"
    OPPORTUNITY_WON = "opportunity.won"
    OPPORTUNITY_LOST = "opportunity.lost"


Handler = Callable[[Event], None]


class EventBusProtocol(Protocol):
    """Adapter contract (ADR-0003): a production broker implements this."""

    def publish(self, event_type: str, payload: dict[str, Any], trace_id: str | None = None) -> Event: ...
    def subscribe(self, event_type: str, handler: Handler) -> None: ...
    def unsubscribe(self, event_type: str, handler: Handler) -> None: ...
    def dispatch(self, event: Event) -> None: ...


class SqliteEventBus:
    """Default bus: synchronous dispatch + persisted event log."""

    def __init__(self, db: Database, persist: bool = True) -> None:
        self._repo = EventRepository(db)
        self._persist = persist
        self._handlers: dict[str, list[Handler]] = {}

    def publish(self, event_type: str, payload: dict[str, Any],
                trace_id: str | None = None) -> Event:
        event = Event(
            event_type=event_type, payload=payload, trace_id=trace_id,
            id=new_id(), created_at=now_iso(),
        )
        if self._persist:
            try:
                self._repo.insert(event)
            except Exception:  # pragma: no cover - resilience path
                logger.warning("failed to persist event %s", event_type, exc_info=True)
        self.dispatch(event)
        return event

    def subscribe(self, event_type: str, handler: Handler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def dispatch(self, event: Event) -> None:
        for handler in list(self._handlers.get(event.event_type, [])):
            self._run_safe(handler, event)
        for handler in list(self._handlers.get("*", [])):
            self._run_safe(handler, event)

    @staticmethod
    def _run_safe(handler: Handler, event: Event) -> None:
        try:
            handler(event)
        except Exception:  # noqa: BLE001 - bus must never crash subscribers
            logger.error("event handler %r failed for %s", handler, event.event_type,
                         exc_info=True)
