"""Tests for Campaigns Engine (SPEC-040)."""

from __future__ import annotations

import unittest
from pathlib import Path

from geos.domains.campaigns import CampaignEngine, CampaignError, CAMPAIGN_TYPES
from geos.storage.database import Database


class CampaignEngineBasicTests(unittest.TestCase):
    """Basic campaign CRUD and lifecycle tests."""

    def setUp(self) -> None:
        self.db = Database(":memory:")
        self.db.open()
        self.db.migrate()
        self.engine = CampaignEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_create_campaign(self) -> None:
        """Create a basic campaign."""
        item = self.engine.create(
            name="Test Campaign",
            campaign_type="content_distribution",
            hypothesis="Test hypothesis",
        )
        self.assertEqual(item["name"], "Test Campaign")
        self.assertEqual(item["status"], "PLANNED")
        self.assertEqual(item["campaign_type"], "content_distribution")
        self.assertEqual(item["hypothesis"], "Test hypothesis")
        self.assertIsNotNone(item["id"])
        self.assertIsNotNone(item["slug"])

    def test_create_campaign_empty_name_raises(self) -> None:
        """Empty name should raise CampaignError."""
        with self.assertRaises(CampaignError):
            self.engine.create(name="")

    def test_create_campaign_invalid_type_raises(self) -> None:
        """Invalid campaign type should raise CampaignError."""
        with self.assertRaises(CampaignError):
            self.engine.create(name="Test", campaign_type="invalid_type")

    def test_get_campaign(self) -> None:
        """Get campaign by ID."""
        created = self.engine.create(name="Get Test")
        fetched = self.engine.get(created["id"])
        self.assertEqual(fetched["id"], created["id"])
        self.assertEqual(fetched["name"], "Get Test")

    def test_get_nonexistent_raises(self) -> None:
        """Get nonexistent campaign should raise NotFoundError."""
        with self.assertRaises(Exception):
            self.engine.get("nonexistent-id")

    def test_list_campaigns(self) -> None:
        """List campaigns with filters."""
        self.engine.create(name="Campaign 1", campaign_type="content_distribution")
        self.engine.create(name="Campaign 2", campaign_type="lead_generation")
        self.engine.create(name="Campaign 3", campaign_type="content_distribution")

        all_campaigns = self.engine.list()
        self.assertEqual(len(all_campaigns), 3)

        filtered = self.engine.list(campaign_type="content_distribution")
        self.assertEqual(len(filtered), 2)

    def test_transition_planned_to_active(self) -> None:
        """Transition PLANNED → ACTIVE."""
        item = self.engine.create(name="Transition Test")
        activated = self.engine.activate(item["id"])
        self.assertEqual(activated["status"], "ACTIVE")

    def test_transition_active_to_paused(self) -> None:
        """Transition ACTIVE → PAUSED."""
        item = self.engine.create(name="Pause Test")
        self.engine.activate(item["id"])
        paused = self.engine.pause(item["id"])
        self.assertEqual(paused["status"], "PAUSED")

    def test_transition_active_to_completed(self) -> None:
        """Transition ACTIVE → COMPLETED."""
        item = self.engine.create(name="Complete Test")
        self.engine.activate(item["id"])
        completed = self.engine.complete(item["id"], result="Success")
        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(completed["result"], "Success")

    def test_transition_planned_to_cancelled(self) -> None:
        """Transition PLANNED → CANCELLED."""
        item = self.engine.create(name="Cancel Test")
        cancelled = self.engine.cancel(item["id"], reason="No budget")
        self.assertEqual(cancelled["status"], "CANCELLED")
        self.assertEqual(cancelled["cancel_reason"], "No budget")

    def test_invalid_transition_raises(self) -> None:
        """Invalid transition should raise CampaignError."""
        item = self.engine.create(name="Invalid Transition")
        with self.assertRaises(CampaignError):
            self.engine.transition(item["id"], "COMPLETED")  # PLANNED → COMPLETED invalid

    def test_completed_campaign_cannot_transition(self) -> None:
        """Completed campaign cannot transition."""
        item = self.engine.create(name="Done Campaign")
        self.engine.activate(item["id"])
        self.engine.complete(item["id"])
        with self.assertRaises(CampaignError):
            self.engine.activate(item["id"])

    def test_cancelled_campaign_cannot_transition(self) -> None:
        """Cancelled campaign cannot transition."""
        item = self.engine.create(name="Cancelled Campaign")
        self.engine.cancel(item["id"])
        with self.assertRaises(CampaignError):
            self.engine.activate(item["id"])


class CampaignContentLinkingTests(unittest.TestCase):
    """Tests for linking content to campaigns."""

    def setUp(self) -> None:
        self.db = Database(":memory:")
        self.db.open()
        self.db.migrate()
        self.engine = CampaignEngine(self.db)
        # Create a content item
        from geos.domains.content import ContentEngine
        self.content_engine = ContentEngine(self.db)
        self.content = self.content_engine.create_idea("Test Content")

    def tearDown(self) -> None:
        self.db.close()

    def test_add_content_to_campaign(self) -> None:
        """Add content item to campaign."""
        campaign = self.engine.create(name="Content Campaign")
        updated = self.engine.add_content(campaign["id"], self.content["id"])
        content_list = self.engine.list_content(campaign["id"])
        self.assertEqual(len(content_list), 1)
        self.assertEqual(content_list[0]["id"], self.content["id"])

    def test_remove_content_from_campaign(self) -> None:
        """Remove content item from campaign."""
        campaign = self.engine.create(name="Content Campaign")
        self.engine.add_content(campaign["id"], self.content["id"])
        self.engine.remove_content(campaign["id"], self.content["id"])
        content_list = self.engine.list_content(campaign["id"])
        self.assertEqual(len(content_list), 0)

    def test_add_duplicate_content_idempotent(self) -> None:
        """Adding same content twice should be idempotent."""
        campaign = self.engine.create(name="Content Campaign")
        self.engine.add_content(campaign["id"], self.content["id"])
        self.engine.add_content(campaign["id"], self.content["id"])
        content_list = self.engine.list_content(campaign["id"])
        self.assertEqual(len(content_list), 1)


class CampaignMetricsTests(unittest.TestCase):
    """Tests for campaign metrics tracking."""

    def setUp(self) -> None:
        self.db = Database(":memory:")
        self.db.open()
        self.db.migrate()
        self.engine = CampaignEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_record_metric(self) -> None:
        """Record a metric value."""
        campaign = self.engine.create(name="Metrics Campaign")
        self.engine.record_metric(campaign["id"], "impressions", 1000)
        self.engine.record_metric(campaign["id"], "impressions", 2000)
        metrics = self.engine.get_metrics(campaign["id"])
        self.assertIn("impressions", metrics)
        self.assertEqual(metrics["impressions"]["latest"], 2000)
        self.assertEqual(metrics["impressions"]["count"], 2)

    def test_record_spend(self) -> None:
        """Record a spend against budget."""
        campaign = self.engine.create(name="Budget Campaign", budget=1000)
        self.engine.record_spend(campaign["id"], 500, description="Ad spend")
        updated = self.engine.get(campaign["id"])
        self.assertEqual(updated["total_spend"], 500)

    def test_budget_exceeded_raises(self) -> None:
        """Spend exceeding budget should raise CampaignError."""
        campaign = self.engine.create(name="Budget Campaign", budget=100)
        with self.assertRaises(CampaignError):
            self.engine.record_spend(campaign["id"], 200)

    def test_budget_status(self) -> None:
        """Get budget status."""
        campaign = self.engine.create(name="Budget Campaign", budget=1000)
        self.engine.record_spend(campaign["id"], 300)
        status = self.engine.get_budget_status(campaign["id"])
        self.assertEqual(status["budget"], 1000)
        self.assertEqual(status["total_spend"], 300)
        self.assertEqual(status["remaining"], 700)
        self.assertEqual(status["utilization"], 30.0)


class CampaignSummaryTests(unittest.TestCase):
    """Tests for campaign summary."""

    def setUp(self) -> None:
        self.db = Database(":memory:")
        self.db.open()
        self.db.migrate()
        self.engine = CampaignEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_summary(self) -> None:
        """Get campaign summary."""
        campaign = self.engine.create(
            name="Summary Campaign",
            budget=1000,
            target_metrics={"impressions": 10000, "clicks": 500},
        )
        self.engine.record_metric(campaign["id"], "impressions", 5000)
        self.engine.record_metric(campaign["id"], "clicks", 250)
        self.engine.record_spend(campaign["id"], 500)

        summary = self.engine.summary(campaign["id"])
        self.assertEqual(summary["campaign"]["id"], campaign["id"])
        self.assertEqual(summary["content_count"], 0)
        self.assertEqual(summary["social_posts_count"], 0)
        self.assertEqual(summary["experiments_count"], 0)
        self.assertEqual(summary["metrics_count"], 2)


if __name__ == "__main__":
    unittest.main()
