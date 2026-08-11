"""SPEC-005 job system tests."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from geos.core.jobs import PermanentError, RetryPolicy, SqliteJobQueue, TransientError, Worker
from tests.helpers import temp_db


class JobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()
        self.queue = SqliteJobQueue(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_successful_job(self) -> None:
        worker = Worker(self.queue)
        seen: list[str] = []
        worker.register("echo", lambda payload, ctx: seen.append(payload["msg"]))
        self.queue.enqueue("echo", {"msg": "hi"})
        job = worker.run_once()
        self.assertIsNotNone(job)
        self.assertEqual(seen, ["hi"])
        self.assertEqual(self.queue.list()[0].status, "SUCCESS")

    def test_idempotency_duplicate_returns_existing(self) -> None:
        worker = Worker(self.queue)
        worker.register("echo", lambda payload, ctx: None)
        first = self.queue.enqueue("echo", {"m": 1}, idempotency_key="k1")
        second = self.queue.enqueue("echo", {"m": 2}, idempotency_key="k1")
        self.assertEqual(first.id, second.id)
        worker.run_until_idle()
        rows = self.db.conn_checked.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"]
        self.assertEqual(rows, 1)

    def test_transient_error_retries_with_backoff(self) -> None:
        policy = RetryPolicy(max_attempts=3, jitter=False)
        worker = Worker(self.queue, retry_policy=policy)
        calls = {"n": 0}

        def flaky(_p: object, _c: object) -> None:
            calls["n"] += 1
            raise TransientError("temporary")

        worker.register("flaky", flaky)
        self.queue.enqueue("flaky", {})
        worker.run_once()
        job = self.queue.list()[0]
        self.assertEqual(job.status, "RETRYING")
        self.assertEqual(job.attempts, 1)
        self.assertIsNotNone(job.run_after)

    def test_permanent_error_dead_letters(self) -> None:
        worker = Worker(self.queue)
        worker.register("boom", lambda _p, _c: (_ for _ in ()).throw(PermanentError("nope")))
        self.queue.enqueue("boom", {}, max_attempts=3)
        worker.run_once()
        job = self.queue.list()[0]
        self.assertEqual(job.status, "FAILED")

    def test_exhausted_retries_dead(self) -> None:
        policy = RetryPolicy(max_attempts=3, backoff_base=1.0, backoff_max_seconds=1.0)
        worker = Worker(self.queue, retry_policy=policy)
        worker.register("flaky", lambda _p, _c: (_ for _ in ()).throw(TransientError("x")))
        self.queue.enqueue("flaky", {})
        now = datetime(2026, 8, 11, 10, 0, 0, tzinfo=timezone.utc)
        for _ in range(3):
            worker.run_once(now=now.isoformat())
            now = now + timedelta(seconds=5)
        job = self.queue.list()[0]
        self.assertEqual(job.status, "DEAD")
        self.assertEqual(job.attempts, 3)

    def test_run_after_not_claimed_early(self) -> None:
        later = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        self.queue.enqueue("echo", {}, run_after=later)
        worker = Worker(self.queue)
        self.assertIsNone(worker.run_once())
        self.assertEqual(self.queue.list()[0].status, "PENDING")

    def test_worker_missing_handler_dead(self) -> None:
        self.queue.enqueue("no-such-handler", {})
        worker = Worker(self.queue)
        worker.run_once()
        self.assertEqual(self.queue.list()[0].status, "DEAD")


if __name__ == "__main__":
    unittest.main()
