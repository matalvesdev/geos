"""Tests for Email/Nurture Engine (SPEC-033)."""

from __future__ import annotations

import unittest

from geos.domains.email_nurture import EmailNurtureEngine, EmailError
from geos.domains.leads import LeadEngine
from geos.storage.database import Database


class EmailSequenceTests(unittest.TestCase):
    """Email sequence tests."""

    def setUp(self) -> None:
        self.db = Database(":memory:")
        self.db.open()
        self.db.migrate()
        self.engine = EmailNurtureEngine(self.db)
        self.lead_engine = LeadEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_create_sequence(self) -> None:
        """Create a new email sequence."""
        item = self.engine.create_sequence(
            name="Welcome Series",
            trigger_event="lead_captured",
            description="Welcome new leads",
        )
        self.assertEqual(item["name"], "Welcome Series")
        self.assertEqual(item["status"], "DRAFT")
        self.assertEqual(item["trigger_event"], "lead_captured")

    def test_create_empty_name_raises(self) -> None:
        """Empty name should raise EmailError."""
        with self.assertRaises(EmailError):
            self.engine.create_sequence(name="", trigger_event="lead_captured")

    def test_create_invalid_trigger_raises(self) -> None:
        """Invalid trigger should raise EmailError."""
        with self.assertRaises(EmailError):
            self.engine.create_sequence(name="Test", trigger_event="invalid")

    def test_activate_sequence(self) -> None:
        """Activate a DRAFT sequence."""
        seq = self.engine.create_sequence(
            name="Welcome",
            trigger_event="lead_captured",
        )
        active = self.engine.activate_sequence(seq["id"])
        self.assertEqual(active["status"], "ACTIVE")

    def test_pause_sequence(self) -> None:
        """Pause an ACTIVE sequence."""
        seq = self.engine.create_sequence(
            name="Welcome",
            trigger_event="lead_captured",
        )
        self.engine.activate_sequence(seq["id"])
        paused = self.engine.pause_sequence(seq["id"])
        self.assertEqual(paused["status"], "PAUSED")


class EmailEnrollmentTests(unittest.TestCase):
    """Email enrollment tests."""

    def setUp(self) -> None:
        self.db = Database(":memory:")
        self.db.open()
        self.db.migrate()
        self.engine = EmailNurtureEngine(self.db)
        self.lead_engine = LeadEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_enroll_lead(self) -> None:
        """Enroll a lead in a sequence."""
        seq = self.engine.create_sequence(
            name="Welcome",
            trigger_event="lead_captured",
        )
        self.engine.activate_sequence(seq["id"])

        lead = self.lead_engine.capture(email="test@example.com")
        enrollment = self.engine.enroll_lead(seq["id"], lead["id"])
        self.assertEqual(enrollment["status"], "ACTIVE")
        self.assertEqual(enrollment["current_step"], 0)

    def test_enroll_suppressed_email_raises(self) -> None:
        """Enrolling suppressed email should raise EmailError."""
        seq = self.engine.create_sequence(
            name="Welcome",
            trigger_event="lead_captured",
        )
        self.engine.activate_sequence(seq["id"])

        lead = self.lead_engine.capture(email="test@example.com")
        self.engine.suppress_email("test@example.com", reason="unsubscribed")

        with self.assertRaises(EmailError):
            self.engine.enroll_lead(seq["id"], lead["id"])


class EmailSuppressionTests(unittest.TestCase):
    """Email suppression tests."""

    def setUp(self) -> None:
        self.db = Database(":memory:")
        self.db.open()
        self.db.migrate()
        self.engine = EmailNurtureEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_suppress_email(self) -> None:
        """Suppress an email."""
        result = self.engine.suppress_email("test@example.com", reason="unsubscribed")
        self.assertEqual(result["email"], "test@example.com")
        self.assertEqual(result["reason"], "unsubscribed")

    def test_is_suppressed(self) -> None:
        """Check if email is suppressed."""
        self.assertFalse(self.engine.is_suppressed("test@example.com"))
        self.engine.suppress_email("test@example.com")
        self.assertTrue(self.engine.is_suppressed("test@example.com"))

    def test_list_suppressions(self) -> None:
        """List suppressed emails."""
        self.engine.suppress_email("a@test.com")
        self.engine.suppress_email("b@test.com")
        suppressions = self.engine.list_suppressions()
        self.assertEqual(len(suppressions), 2)


if __name__ == "__main__":
    unittest.main()
