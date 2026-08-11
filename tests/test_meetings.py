"""Tests for Meeting Scheduling Engine (SPEC-031/032)."""

from __future__ import annotations

import unittest

from geos.domains.meetings import MeetingEngine, MeetingError
from geos.domains.leads import LeadEngine
from geos.storage.database import Database


class MeetingEngineTests(unittest.TestCase):
    """Meeting lifecycle tests."""

    def setUp(self) -> None:
        self.db = Database(":memory:")
        self.db.open()
        self.db.migrate()
        self.engine = MeetingEngine(self.db)
        self.lead_engine = LeadEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_schedule_meeting(self) -> None:
        """Schedule a new meeting."""
        item = self.engine.schedule(
            title="Discovery Call",
            scheduled_at="2026-08-15T10:00:00Z",
            meeting_type="discovery",
            duration_minutes=30,
        )
        self.assertEqual(item["title"], "Discovery Call")
        self.assertEqual(item["status"], "SCHEDULED")
        self.assertEqual(item["meeting_type"], "discovery")

    def test_schedule_empty_title_raises(self) -> None:
        """Empty title should raise MeetingError."""
        with self.assertRaises(MeetingError):
            self.engine.schedule(title="", scheduled_at="2026-08-15T10:00:00Z")

    def test_schedule_invalid_type_raises(self) -> None:
        """Invalid meeting type should raise MeetingError."""
        with self.assertRaises(MeetingError):
            self.engine.schedule(
                title="Test",
                scheduled_at="2026-08-15T10:00:00Z",
                meeting_type="invalid",
            )

    def test_schedule_with_lead(self) -> None:
        """Schedule meeting linked to a lead."""
        lead = self.lead_engine.capture(email="test@example.com")
        meeting = self.engine.schedule(
            title="Follow-up",
            scheduled_at="2026-08-15T10:00:00Z",
            lead_id=lead["id"],
        )
        self.assertEqual(meeting["lead_id"], lead["id"])

    def test_complete_meeting(self) -> None:
        """Complete a meeting."""
        meeting = self.engine.schedule(
            title="Demo",
            scheduled_at="2026-08-15T10:00:00Z",
        )
        completed = self.engine.complete(
            meeting["id"],
            notes="Great demo",
            outcome="Interested",
        )
        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(completed["outcome"], "Interested")

    def test_cancel_meeting(self) -> None:
        """Cancel a meeting."""
        meeting = self.engine.schedule(
            title="Meeting",
            scheduled_at="2026-08-15T10:00:00Z",
        )
        cancelled = self.engine.cancel(meeting["id"])
        self.assertEqual(cancelled["status"], "CANCELLED")

    def test_mark_no_show(self) -> None:
        """Mark meeting as no-show."""
        meeting = self.engine.schedule(
            title="Meeting",
            scheduled_at="2026-08-15T10:00:00Z",
        )
        no_show = self.engine.mark_no_show(meeting["id"])
        self.assertEqual(no_show["status"], "NO_SHOW")

    def test_invalid_transition_raises(self) -> None:
        """Invalid transition should raise MeetingError."""
        meeting = self.engine.schedule(
            title="Meeting",
            scheduled_at="2026-08-15T10:00:00Z",
        )
        self.engine.complete(meeting["id"])
        with self.assertRaises(MeetingError):
            self.engine.transition(meeting["id"], "CANCELLED")  # COMPLETED is terminal

    def test_upcoming_meetings(self) -> None:
        """Get upcoming meetings."""
        self.engine.schedule(
            title="Future Meeting",
            scheduled_at="2099-01-01T10:00:00Z",
        )
        upcoming = self.engine.upcoming()
        self.assertEqual(len(upcoming), 1)

    def test_analytics(self) -> None:
        """Get meeting analytics."""
        m1 = self.engine.schedule(title="M1", scheduled_at="2026-08-15T10:00:00Z")
        m2 = self.engine.schedule(title="M2", scheduled_at="2026-08-16T10:00:00Z")
        self.engine.complete(m1["id"])
        self.engine.mark_no_show(m2["id"])

        analytics = self.engine.analytics()
        self.assertEqual(analytics["total"], 2)
        self.assertEqual(analytics["completed"], 1)
        self.assertEqual(analytics["no_show"], 1)


if __name__ == "__main__":
    unittest.main()
