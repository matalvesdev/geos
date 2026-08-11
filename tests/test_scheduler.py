"""SPEC-006 scheduler tests."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from geos.core.jobs import SqliteJobQueue
from geos.core.scheduler import Schedule, Scheduler
from tests.helpers import temp_db


class SchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()
        self.queue = SqliteJobQueue(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_interval_due_enqueues_with_idempotency(self) -> None:
        scheduler = Scheduler(self.queue)
        schedule = Schedule(kind="interval", seconds=60, schedule_id="poll")
        scheduler.add(schedule, kind="market.scan", payload={"n": 1},
                      now=datetime(2026, 8, 11, 10, 0, 0))
        now = datetime(2026, 8, 11, 10, 0, 0)
        self.assertEqual(scheduler.run_due(now), 1)  # interval fires immediately
        # second call before due: still 1 (idempotency prevents duplicates)
        self.assertEqual(scheduler.run_due(now + timedelta(seconds=10)), 0)
        jobs = self.queue.list()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].kind, "market.scan")
        self.assertIsNotNone(jobs[0].idempotency_key)

    def test_interval_advances_next_run(self) -> None:
        scheduler = Scheduler(self.queue)
        base = datetime(2026, 8, 11, 10, 0, 0)
        scheduler.add(Schedule(kind="interval", seconds=60, schedule_id="a"),
                      kind="k", payload={}, now=base)
        scheduler.run_due(base)
        scheduler.run_due(base)
        self.assertEqual(len(self.queue.list()), 1)  # not yet due again

    def test_cron_schedule_next_run(self) -> None:
        scheduler = Scheduler(self.queue)
        scheduler.add(Schedule(kind="cron", cron="0 9 * * *", schedule_id="daily"),
                      kind="workflow.run", payload={"workflow_id": "daily"},
                      now=datetime(2026, 8, 11, 8, 30, 0))
        scheduler.run_due(datetime(2026, 8, 11, 9, 0, 30))
        jobs = self.queue.list()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].payload["workflow_id"], "daily")


if __name__ == "__main__":
    unittest.main()
