"""Tests for CRM Engine (SPEC-029)."""

from __future__ import annotations

import unittest

from geos.domains.crm import CRMEngine, CRMError
from geos.domains.leads import LeadEngine
from geos.storage.database import Database


class CRMEngineDealTests(unittest.TestCase):
    """CRM deal lifecycle tests."""

    def setUp(self) -> None:
        self.db = Database(":memory:")
        self.db.open()
        self.db.migrate()
        self.engine = CRMEngine(self.db)
        self.lead_engine = LeadEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_create_deal(self) -> None:
        """Create a new deal."""
        item = self.engine.create_deal(
            name="Test Deal",
            value=10000,
            currency="BRL",
        )
        self.assertEqual(item["name"], "Test Deal")
        self.assertEqual(item["value"], 10000)
        self.assertEqual(item["stage"], "PROSPECTING")
        self.assertEqual(item["status"], "OPEN")

    def test_create_deal_empty_name_raises(self) -> None:
        """Empty name should raise CRMError."""
        with self.assertRaises(CRMError):
            self.engine.create_deal(name="")

    def test_create_deal_with_lead(self) -> None:
        """Create a deal linked to a lead."""
        lead = self.lead_engine.capture(email="test@example.com")
        deal = self.engine.create_deal(name="Test Deal", lead_id=lead["id"])
        self.assertEqual(deal["lead_id"], lead["id"])

    def test_transition_deal(self) -> None:
        """Transition deal through stages."""
        deal = self.engine.create_deal(name="Test Deal")
        qualified = self.engine.transition_deal(deal["id"], "QUALIFICATION")
        self.assertEqual(qualified["stage"], "QUALIFICATION")
        self.assertEqual(qualified["probability"], 0.2)

    def test_invalid_stage_transition_raises(self) -> None:
        """Invalid stage transition should raise CRMError."""
        deal = self.engine.create_deal(name="Test Deal")
        with self.assertRaises(CRMError):
            self.engine.transition_deal(deal["id"], "NEGOTIATION")  # skip stages

    def test_pipeline_summary(self) -> None:
        """Get pipeline summary."""
        self.engine.create_deal(name="Deal 1", value=10000)
        self.engine.create_deal(name="Deal 2", value=20000)

        summary = self.engine.pipeline_summary()
        self.assertEqual(summary["total_deals"], 2)
        self.assertEqual(summary["total_value"], 30000)


class CRMActivityTests(unittest.TestCase):
    """CRM activity tests."""

    def setUp(self) -> None:
        self.db = Database(":memory:")
        self.db.open()
        self.db.migrate()
        self.engine = CRMEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_create_activity(self) -> None:
        """Create an activity."""
        deal = self.engine.create_deal(name="Test Deal")
        activity = self.engine.create_activity(
            activity_type="call",
            deal_id=deal["id"],
            subject="Discovery call",
        )
        self.assertEqual(activity["activity_type"], "call")
        self.assertEqual(activity["deal_id"], deal["id"])

    def test_complete_activity(self) -> None:
        """Complete an activity."""
        deal = self.engine.create_deal(name="Test Deal")
        activity = self.engine.create_activity(
            activity_type="email",
            deal_id=deal["id"],
        )
        completed = self.engine.complete_activity(activity["id"], notes="Sent")
        self.assertEqual(completed["completed"], 1)


if __name__ == "__main__":
    unittest.main()
