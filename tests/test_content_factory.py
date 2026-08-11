"""Vertical slice 1: content-factory workflow + scheduler/worker wiring."""

from __future__ import annotations

import unittest
from datetime import datetime

from geos.core.jobs import SqliteJobQueue, Worker
from geos.core.scheduler import Scheduler
from geos.core.workflows import StepStatus, Workflow, WorkflowEngine, WorkflowStatus
from tests.helpers import TempDir, temp_db

CONTENT_FACTORY = """workflow:
  id: content-factory
  trigger: {kind: cron, cron: "0 7 * * 1"}
  steps:
    - id: research
      type: agent
      agent: research.run
      input: {question: "origem de crédito bancário", sources_limit: 3}
    - id: brief
      type: agent
      agent: content.brief
      input: {topic: "$ref steps.research.question"}
    - id: draft
      type: agent
      agent: content.draft
      input: {topic: "$ref steps.brief.topic"}
    - id: social
      type: agent
      agent: social.draft
      input: {title: "$ref steps.draft.title"}
    - id: publish
      type: approval
      approval: {mode: required}
    - id: schedule
      type: task
      task: schedule.record
      input: {title: "$ref steps.draft.title", platform: blog}
"""


class ContentFactoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()

    def tearDown(self) -> None:
        self.db.close()

    def _write(self, tmp) -> None:
        from pathlib import Path

        (tmp / "wf.yaml").write_text(CONTENT_FACTORY, encoding="utf-8")

    def test_blocks_on_approval(self) -> None:
        with TempDir() as tmp:
            self._write(tmp)
            engine = WorkflowEngine(self.db)
            result = engine.run(Workflow.load(tmp / "wf.yaml"))
        self.assertEqual(result.status, WorkflowStatus.WAITING_APPROVAL)
        self.assertEqual(result.step("publish").status, StepStatus.WAITING_APPROVAL)  # type: ignore[union-attr]
        self.assertEqual(result.step("schedule").status, StepStatus.SKIPPED)  # type: ignore[union-attr]

    def test_full_slice_approved(self) -> None:
        with TempDir() as tmp:
            self._write(tmp)
            engine = WorkflowEngine(self.db)
            result = engine.run(Workflow.load(tmp / "wf.yaml"),
                                inputs={"approvals": {"publish": True}})
        self.assertEqual(result.status, WorkflowStatus.SUCCESS)
        for step in result.steps:
            self.assertEqual(step.status, StepStatus.SUCCESS)
        scheduled_events = self.db.conn_checked.execute(
            "SELECT COUNT(*) c FROM events WHERE event_type = 'content.scheduled'"
        ).fetchone()["c"]
        self.assertEqual(scheduled_events, 1)
        research_rows = self.db.conn_checked.execute(
            "SELECT COUNT(*) c FROM research"
        ).fetchone()["c"]
        self.assertEqual(research_rows, 1)

    def test_scheduler_enqueues_workflow_job(self) -> None:
        with TempDir() as tmp:
            self._write(tmp)
            workflow = Workflow.load(tmp / "wf.yaml")
            from geos.core.scheduler import Schedule

            queue = SqliteJobQueue(self.db)
            scheduler = Scheduler(queue)
            schedule = Schedule.from_dict(workflow.trigger, schedule_id=workflow.id)
            scheduler.add(schedule, kind="workflow.run",
                          payload={"workflow_id": workflow.id},
                          now=datetime(2026, 8, 11, 8, 0, 0))
            # cron "0 7 * * 1" -> next Monday 07:00 (2026-08-11 is a Tuesday)
            enqueued = scheduler.run_due(datetime(2026, 8, 17, 7, 0, 30))
            self.assertEqual(enqueued, 1)
            self.assertEqual(scheduler.run_due(datetime(2026, 8, 17, 7, 0, 30)), 0)
            jobs = queue.list()
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0].kind, "workflow.run")
            self.assertEqual(jobs[0].payload["workflow_id"], "content-factory")

    def test_worker_runs_workflow_job(self) -> None:
        with TempDir() as tmp:
            self._write(tmp)
            queue = SqliteJobQueue(self.db)
            queue.enqueue("workflow.run", {"workflow_id": "content-factory"})
            engine = WorkflowEngine(self.db)
            workflow_path = tmp / "wf.yaml"

            def handler(payload, _ctx):
                engine.run(Workflow.load(workflow_path),
                           inputs={"approvals": {"publish": True}})

            worker = Worker(queue)
            worker.register("workflow.run", handler)
            count = worker.run_until_idle()
        self.assertEqual(count, 1)
        runs = self.db.conn_checked.execute(
            "SELECT COUNT(*) c FROM runs WHERE workflow_id = 'content-factory'"
        ).fetchone()["c"]
        self.assertEqual(runs, 1)


if __name__ == "__main__":
    unittest.main()
