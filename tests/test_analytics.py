"""SPEC-035 analytics tests: metric registry, insights, snapshot persistence."""

from __future__ import annotations

import unittest

from geos.domains.analytics import AnalyticsEngine, AnalyticsError, INSIGHT_TYPES
from geos.domains.content import ContentEngine
from tests.helpers import temp_db


class CollectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()
        self.engine = AnalyticsEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def _content_flow(self, status: str = "APPROVED") -> str:
        content = ContentEngine(self.db)
        item = content.create_idea("Analytics de teste", keywords=["analytics"])
        content.write_brief(item["id"])
        content.produce_draft(item["id"])
        content.transition(item["id"], "APPROVED")
        if status == "PUBLISHED":
            content.transition(item["id"], "PUBLISHED")
        return item["id"]

    def test_collect_returns_metrics_and_insights(self) -> None:
        result = self.engine.collect()
        self.assertTrue(result["snapshot_id"])
        self.assertIn("content_total", result["metrics"])
        self.assertEqual(result["metrics"]["content_total"], 0)
        self.assertIsInstance(result["insights"], list)
        types = {i["insight_type"] for i in result["insights"]}
        self.assertTrue(types <= set(INSIGHT_TYPES))

    def test_metrics_reflect_local_state(self) -> None:
        self._content_flow("APPROVED")
        self._content_flow("PUBLISHED")
        result = self.engine.collect()
        m = result["metrics"]
        self.assertEqual(m["content_total"], 2)
        self.assertEqual(m["content_approved"], 1)
        self.assertEqual(m["content_published"], 1)
        self.assertIsInstance(m["content_avg_score"], float)

    def test_failed_metric_does_not_crash_insight_derivation(self) -> None:
        """Regression (review): a metric that evaluates to None must not make
        _derive_insights crash with int(None) (SPEC-035 R4 resilience)."""
        # Simulate a metric failure by feeding a snapshot with None values.
        from geos.domains.analytics import _derive_insights

        metrics = {"social_pending_approval": None, "blog_pending_approval": None,
                   "social_due": None, "seo_issues_critical": None,
                   "social_published": None, "opportunities_open": None,
                   "experiments_running": None, "experiments_completed": None,
                   "workflow_failures": None, "workflow_runs": None}
        insights = _derive_insights(metrics)  # must not raise
        self.assertTrue(insights)
        self.assertEqual(insights[0].insight_type, "OBSERVATION")
        self.assertIn("Sem pendências", insights[0].content)

    def test_pending_approval_drives_observation_insight(self) -> None:
        from geos.domains.blog import BlogEngine

        content_id = self._content_flow("APPROVED")
        post = BlogEngine(self.db).prepare(content_id)
        BlogEngine(self.db).publish(post["id"])  # gated -> APPROVAL_PENDING
        result = self.engine.collect()
        self.assertEqual(result["metrics"]["blog_pending_approval"], 1)
        texts = [i["content"] for i in result["insights"]]
        self.assertTrue(any("blog" in t.lower() and "aprovação" in t.lower()
                            for t in texts))

    def test_social_due_drives_investigation_insight(self) -> None:
        from geos.domains.social import SocialEngine

        content_id = self._content_flow("APPROVED")
        engine = SocialEngine(self.db)
        post = engine.prepare(content_id, channel="x",
                              scheduled_at="2099-01-01T00:00:00+00:00")
        engine.publish(post["id"], approve=True)  # queued -> SCHEDULED
        engine.schedule(post["id"], "2000-01-01T00:00:00+00:00")  # window passed
        result = self.engine.collect()
        self.assertEqual(result["metrics"]["social_due"], 1)
        texts = [i["content"] for i in result["insights"]]
        self.assertTrue(any(i["insight_type"] == "INVESTIGATION"
                            and "vencida" in i["content"] for i in result["insights"]))

    def test_insights_persisted_and_filterable(self) -> None:
        self.engine.collect()
        self.engine.collect()  # history accumulates
        all_insights = self.engine.insights()
        observations = self.engine.insights(insight_type="OBSERVATION")
        self.assertTrue(all_insights)
        self.assertTrue(all(i["insight_type"] == "OBSERVATION"
                            for i in observations))
        self.assertEqual(len(self.engine.latest()["metrics"]) > 0, True)

    def test_metrics_filter_by_domain(self) -> None:
        self.engine.collect()
        content_metrics = self.engine.metrics(domain="content")
        self.assertTrue(content_metrics)
        self.assertTrue(all("content" in name for name in content_metrics))

    def test_metrics_before_any_snapshot_raises(self) -> None:
        with self.assertRaises(AnalyticsError):
            self.engine.metrics()

    def test_empty_operation_yields_clean_observation(self) -> None:
        result = self.engine.collect()
        clean = [i for i in result["insights"]
                 if i["insight_type"] == "OBSERVATION"
                 and "Sem pendências" in i["content"]]
        self.assertEqual(len(clean), 1)


if __name__ == "__main__":
    unittest.main()
