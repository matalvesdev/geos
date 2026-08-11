"""SPEC-001 telemetry tests."""

from __future__ import annotations

import unittest

from geos.core.telemetry import Telemetry
from tests.helpers import temp_db


class TelemetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()

    def tearDown(self) -> None:
        self.db.close()

    def test_run_lifecycle(self) -> None:
        telemetry = Telemetry(self.db)
        ctx = telemetry.start(workflow_id="daily", trace_id="t-1")
        self.assertIsNotNone(ctx.run.id)
        ctx.finish("SUCCESS", model="mock", tokens=10, cost=0.0)
        runs = telemetry.list()
        self.assertEqual(len(runs), 1)
        run = runs[0]
        self.assertEqual(run.workflow_id, "daily")
        self.assertEqual(run.status, "SUCCESS")
        self.assertEqual(run.trace_id, "t-1")
        self.assertEqual(run.model, "mock")

    def test_failed_run_records_error(self) -> None:
        telemetry = Telemetry(self.db)
        ctx = telemetry.start(agent="ResearchAgent")
        ctx.finish("FAILED", error="boom")
        run = telemetry.list()[0]
        self.assertEqual(run.error, "boom")

    def test_list_filter(self) -> None:
        telemetry = Telemetry(self.db)
        telemetry.start(workflow_id="a").finish("SUCCESS")
        telemetry.start(workflow_id="b").finish("FAILED", error="x")
        self.assertEqual(len(telemetry.list(status="SUCCESS")), 1)
        self.assertEqual(len(telemetry.list()), 2)


if __name__ == "__main__":
    unittest.main()
