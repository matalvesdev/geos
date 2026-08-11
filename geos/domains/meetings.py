"""Meeting Scheduling Engine (SPEC-031/032): meeting lifecycle management.

Meetings flow through: SCHEDULED → COMPLETED / CANCELLED / NO_SHOW.

The engine supports local scheduling with Google Calendar/Meet adapter
planned for future phases (credential-gated, SPEC-032). For now, meetings
are tracked locally with deterministic scheduling logic.
"""

from __future__ import annotations

from typing import Any

from ..core.events import SqliteEventBus
from ..storage.database import Database
from ..storage.repos import NotFoundError, RepoFactory
from ..util import new_id, now_iso

# Meeting statuses
MEETING_STATUSES: dict[str, set[str]] = {
    "SCHEDULED": {"COMPLETED", "CANCELLED", "NO_SHOW"},
    "COMPLETED": set(),
    "CANCELLED": set(),
    "NO_SHOW": set(),
}

# Meeting types
MEETING_TYPES = (
    "discovery", "demo", "follow_up", "negotiation", "close",
    "check_in", "onsite", "virtual",
)


class MeetingError(ValueError):
    """Invalid meeting operation (bad transition, missing required field)."""


class MeetingEngine:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._repo = RepoFactory(db)

    # ---- lifecycle ---------------------------------------------------------
    def schedule(
        self,
        title: str,
        scheduled_at: str,
        lead_id: str | None = None,
        deal_id: str | None = None,
        meeting_type: str = "discovery",
        duration_minutes: int = 30,
        timezone: str = "UTC",
        location: str | None = None,
        meeting_url: str | None = None,
        description: str | None = None,
        owner_id: str | None = None,
        attendees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Schedule a new meeting."""
        title = title.strip()
        if not title:
            raise MeetingError("title is required")
        if meeting_type not in MEETING_TYPES:
            raise MeetingError(f"unknown meeting_type {meeting_type!r}")

        # Validate lead/deal exist if provided
        if lead_id:
            self._repo.leads.get(lead_id)
        if deal_id:
            self._repo.crm.get_deal(deal_id)

        meeting_id = self._repo.meetings.create(
            title=title,
            scheduled_at=scheduled_at,
            lead_id=lead_id,
            deal_id=deal_id,
            meeting_type=meeting_type,
            duration_minutes=duration_minutes,
            timezone=timezone,
            location=location,
            meeting_url=meeting_url,
            description=description,
            owner_id=owner_id,
            attendees=attendees,
        )

        try:
            SqliteEventBus(self._db).publish(
                "meeting.scheduled",
                {"meeting_id": meeting_id, "title": title, "scheduled_at": scheduled_at},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass

        return self.get(meeting_id)

    def get(self, meeting_id: str) -> dict[str, Any]:
        """Get a meeting by ID."""
        item = self._repo.meetings.get(meeting_id)
        if item is None:
            raise NotFoundError(f"meeting {meeting_id}")
        return item

    def list(
        self,
        status: str | None = None,
        lead_id: str | None = None,
        deal_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List meetings with optional filters."""
        return self._repo.meetings.list(
            status=status, lead_id=lead_id, deal_id=deal_id, limit=limit
        )

    def upcoming(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get upcoming meetings."""
        return self._repo.meetings.upcoming(limit=limit)

    # ---- lifecycle transitions ---------------------------------------------
    def transition(self, meeting_id: str, target: str) -> dict[str, Any]:
        """Transition meeting to a new status."""
        item = self.get(meeting_id)
        target = target.upper()
        allowed = MEETING_STATUSES.get(item["status"], set())
        if target not in allowed:
            raise MeetingError(
                f"invalid transition {item['status']} → {target} "
                f"(allowed: {sorted(allowed) or 'none'})"
            )

        self._repo.meetings.update_status(meeting_id, target)

        try:
            SqliteEventBus(self._db).publish(
                "meeting.status_changed",
                {"meeting_id": meeting_id, "from": item["status"], "to": target},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass

        return self.get(meeting_id)

    def complete(self, meeting_id: str, notes: str | None = None, outcome: str | None = None) -> dict[str, Any]:
        """Complete a meeting with notes and outcome."""
        item = self.get(meeting_id)
        if item["status"] != "SCHEDULED":
            raise MeetingError(f"cannot complete meeting in status {item['status']}")

        self._repo.meetings.complete(meeting_id, notes, outcome)
        self._repo.meetings.update_status(meeting_id, "COMPLETED")

        try:
            SqliteEventBus(self._db).publish(
                "meeting.completed",
                {"meeting_id": meeting_id, "outcome": outcome},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass

        return self.get(meeting_id)

    def cancel(self, meeting_id: str, reason: str | None = None) -> dict[str, Any]:
        """Cancel a meeting."""
        return self.transition(meeting_id, "CANCELLED")

    def mark_no_show(self, meeting_id: str) -> dict[str, Any]:
        """Mark a meeting as no-show."""
        return self.transition(meeting_id, "NO_SHOW")

    # ---- summary -----------------------------------------------------------
    def summary(self, meeting_id: str) -> dict[str, Any]:
        """Get comprehensive meeting summary."""
        item = self.get(meeting_id)
        lead = None
        deal = None

        if item.get("lead_id"):
            try:
                lead = self._repo.leads.get(item["lead_id"])
            except NotFoundError:
                pass

        if item.get("deal_id"):
            try:
                deal = self._repo.crm.get_deal(item["deal_id"])
            except NotFoundError:
                pass

        return {
            "meeting": item,
            "lead": lead,
            "deal": deal,
            "attendee_count": len(item.get("attendees") or []),
        }

    def analytics(self) -> dict[str, Any]:
        """Get meeting analytics."""
        all_meetings = self.list(limit=1000)
        total = len(all_meetings)
        completed = sum(1 for m in all_meetings if m["status"] == "COMPLETED")
        no_show = sum(1 for m in all_meetings if m["status"] == "NO_SHOW")
        cancelled = sum(1 for m in all_meetings if m["status"] == "CANCELLED")

        return {
            "total": total,
            "completed": completed,
            "no_show": no_show,
            "cancelled": cancelled,
            "completion_rate": round(completed / total * 100, 1) if total else 0,
            "no_show_rate": round(no_show / total * 100, 1) if total else 0,
        }
