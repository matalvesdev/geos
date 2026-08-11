"""Tests for Lead Intelligence Engine (SPEC-026/027/028)."""

from __future__ import annotations

import unittest

from geos.domains.leads import LeadEngine, LeadError, LEAD_SOURCES
from geos.storage.database import Database


class LeadEngineBasicTests(unittest.TestCase):
    """Basic lead CRUD and lifecycle tests."""

    def setUp(self) -> None:
        self.db = Database(":memory:")
        self.db.open()
        self.db.migrate()
        self.engine = LeadEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_capture_lead(self) -> None:
        """Capture a new lead."""
        item = self.engine.capture(
            email="test@example.com",
            name="Test Lead",
            company="Test Corp",
            source="website",
        )
        self.assertEqual(item["email"], "test@example.com")
        self.assertEqual(item["name"], "Test Lead")
        self.assertEqual(item["status"], "CAPTURED")
        self.assertIsNotNone(item["id"])

    def test_capture_empty_email_raises(self) -> None:
        """Empty email should raise LeadError."""
        with self.assertRaises(LeadError):
            self.engine.capture(email="")

    def test_capture_invalid_source_raises(self) -> None:
        """Invalid source should raise LeadError."""
        with self.assertRaises(LeadError):
            self.engine.capture(email="test@example.com", source="invalid")

    def test_capture_duplicate_email_raises(self) -> None:
        """Duplicate email should raise LeadError."""
        self.engine.capture(email="test@example.com")
        with self.assertRaises(LeadError):
            self.engine.capture(email="test@example.com")

    def test_get_lead(self) -> None:
        """Get lead by ID."""
        created = self.engine.capture(email="test@example.com")
        fetched = self.engine.get(created["id"])
        self.assertEqual(fetched["id"], created["id"])

    def test_list_leads(self) -> None:
        """List leads with filters."""
        self.engine.capture(email="a@test.com", source="website")
        self.engine.capture(email="b@test.com", source="webinar")

        all_leads = self.engine.list()
        self.assertEqual(len(all_leads), 2)

        filtered = self.engine.list(source="website")
        self.assertEqual(len(filtered), 1)

    def test_transition_captured_to_qualified(self) -> None:
        """Transition CAPTURED → QUALIFIED."""
        item = self.engine.capture(email="test@example.com")
        qualified = self.engine.transition(item["id"], "QUALIFIED")
        self.assertEqual(qualified["status"], "QUALIFIED")

    def test_invalid_transition_raises(self) -> None:
        """Invalid transition should raise LeadError."""
        item = self.engine.capture(email="test@example.com")
        with self.assertRaises(LeadError):
            self.engine.transition(item["id"], "WON")  # CAPTURED → WON invalid

    def test_disqualify_lead(self) -> None:
        """Disqualify a lead."""
        item = self.engine.capture(email="test@example.com")
        disqualified = self.engine.disqualify(item["id"], reason="no_budget")
        self.assertEqual(disqualified["status"], "DISQUALIFIED")
        self.assertEqual(disqualified["disqualification_reason"], "no_budget")


class LeadScoringTests(unittest.TestCase):
    """Tests for lead scoring (SPEC-027)."""

    def setUp(self) -> None:
        self.db = Database(":memory:")
        self.db.open()
        self.db.migrate()
        self.engine = LeadEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_score_lead(self) -> None:
        """Score a lead."""
        item = self.engine.capture(
            email="test@example.com",
            company="Test Corp",
            source="demo_request",
        )
        result = self.engine.score(item["id"])
        self.assertIn("score", result)
        self.assertIn("breakdown", result)
        self.assertIsInstance(result["score"], float)

    def test_score_breakdown_components(self) -> None:
        """Score breakdown has all components."""
        item = self.engine.capture(email="test@example.com")
        result = self.engine.score(item["id"])
        breakdown = result["breakdown"]
        self.assertIn("fit", breakdown["components"])
        self.assertIn("intent", breakdown["components"])
        self.assertIn("engagement", breakdown["components"])
        self.assertIn("relationship", breakdown["components"])


class LeadInteractionTests(unittest.TestCase):
    """Tests for lead interactions."""

    def setUp(self) -> None:
        self.db = Database(":memory:")
        self.db.open()
        self.db.migrate()
        self.engine = LeadEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_record_interaction(self) -> None:
        """Record an interaction."""
        item = self.engine.capture(email="test@example.com")
        updated = self.engine.record_interaction(
            item["id"], "email", summary="Sent welcome email"
        )
        self.assertEqual(updated["interaction_count"], 1)

    def test_list_interactions(self) -> None:
        """List interactions for a lead."""
        item = self.engine.capture(email="test@example.com")
        self.engine.record_interaction(item["id"], "email")
        self.engine.record_interaction(item["id"], "call")

        interactions = self.engine.list_interactions(item["id"])
        self.assertEqual(len(interactions), 2)


if __name__ == "__main__":
    unittest.main()
