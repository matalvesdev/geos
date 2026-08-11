"""SPEC-007 workflow engine tests."""

from __future__ import annotations

import unittest
from pathlib import Path

from geos.core.jobs import TransientError
from geos.core.workflows import (
    StepStatus,
    Workflow,
    WorkflowEngine,
    WorkflowLoadError,
    WorkflowStatus,
)
from tests.helpers import TempDir, temp_db


def _write_workflow(tmp: Path, body: str) -> Path:
    path = tmp / "wf.yaml"
    path.write_text(body, encoding="utf-8")
    return path


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()
        self.engine = WorkflowEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_simple_run_with_output_chaining(self) -> None:
        with TempDir() as tmp:
            path = _write_workflow(
                tmp,
                """workflow:
  id: demo
  trigger: {kind: manual}
  steps:
    - id: research
      type: agent
      agent: research.summary
      input: {topic: "conciliação"}
    - id: brief
      type: agent
      agent: content.draft
      input: {topic: "$ref steps.research.topic"}
""",
            )
            result = self.engine.run(Workflow.load(path))
        self.assertEqual(result.status, WorkflowStatus.SUCCESS)
        brief = result.step("brief")
        self.assertIsNotNone(brief)
        self.assertEqual(brief.status, StepStatus.SUCCESS)  # type: ignore[union-attr]
        self.assertIn("conciliação", brief.output["title"])  # type: ignore[index, union-attr]
        self.assertIsNotNone(result.run_id)

    def test_condition_attribute_chain(self) -> None:
        with TempDir() as tmp:
            path = _write_workflow(
                tmp,
                """workflow:
  id: condchain
  trigger: {kind: manual}
  steps:
    - id: research
      type: agent
      agent: research.summary
      input: {topic: x}
    - id: gated
      type: agent
      agent: echo
      condition: "steps.research.status == 'SUCCESS'"
      input: {message: ok}
""",
            )
            result = self.engine.run(Workflow.load(path))
        self.assertEqual(result.status, WorkflowStatus.SUCCESS)
        self.assertEqual(result.step("gated").status, StepStatus.SUCCESS)  # type: ignore[union-attr]

    def test_malformed_condition_fails_step(self) -> None:
        # SPEC-007: condition errors fail the step — never silently skip.
        with TempDir() as tmp:
            path = _write_workflow(
                tmp,
                """workflow:
  id: badcond
  trigger: {kind: manual}
  steps:
    - id: s1
      type: agent
      agent: echo
      condition: "__import__('os')"
      input: {message: x}
""",
            )
            result = self.engine.run(Workflow.load(path))
        self.assertEqual(result.step("s1").status, StepStatus.FAILED)  # type: ignore[union-attr]
        self.assertEqual(result.status, WorkflowStatus.FAILED)

    def test_condition_skip(self) -> None:
        with TempDir() as tmp:
            path = _write_workflow(
                tmp,
                """workflow:
  id: cond
  trigger: {kind: manual}
  steps:
    - id: research
      type: agent
      agent: research.summary
      input: {topic: "x"}
    - id: skipped
      type: agent
      agent: echo
      condition: "inputs.flag == True"
      input: {message: "nope"}
""",
            )
            result = self.engine.run(Workflow.load(path), inputs={"flag": False})
        self.assertEqual(result.status, WorkflowStatus.SUCCESS)
        self.assertEqual(result.step("skipped").status, StepStatus.SKIPPED)  # type: ignore[union-attr]

    def test_approval_required_blocks_then_proceeds(self) -> None:
        with TempDir() as tmp:
            path = _write_workflow(
                tmp,
                """workflow:
  id: gated
  trigger: {kind: manual}
  steps:
    - id: draft
      type: agent
      agent: content.draft
      input: {topic: "t"}
    - id: publish
      type: approval
      approval: {mode: required}
    - id: social
      type: agent
      agent: social.draft
      input: {title: "$ref steps.draft.title"}
""",
            )
            blocked = self.engine.run(Workflow.load(path))
            self.assertEqual(blocked.status, WorkflowStatus.WAITING_APPROVAL)
            self.assertEqual(blocked.step("publish").status, StepStatus.WAITING_APPROVAL)  # type: ignore[union-attr]
            self.assertEqual(blocked.step("social").status, StepStatus.SKIPPED)  # type: ignore[union-attr]
            approvals = self.db.conn_checked.execute(
                "SELECT COUNT(*) c FROM approvals WHERE status='PENDING'"
            ).fetchone()["c"]
            self.assertEqual(approvals, 1)

            approved = self.engine.run(Workflow.load(path), inputs={"approvals": {"publish": True}})
            self.assertEqual(approved.status, WorkflowStatus.SUCCESS)
            self.assertEqual(approved.step("publish").status, StepStatus.SUCCESS)  # type: ignore[union-attr]

    def test_approval_rejected(self) -> None:
        with TempDir() as tmp:
            path = _write_workflow(
                tmp,
                """workflow:
  id: gated2
  trigger: {kind: manual}
  steps:
    - id: publish
      type: approval
      approval: {mode: required}
""",
            )
            result = self.engine.run(Workflow.load(path), inputs={"approvals": {"publish": False}})
        self.assertEqual(result.step("publish").status, StepStatus.REJECTED)  # type: ignore[union-attr]

    def test_unknown_agent_fails_fast(self) -> None:
        with TempDir() as tmp:
            path = _write_workflow(
                tmp,
                """workflow:
  id: bad
  trigger: {kind: manual}
  steps:
    - id: s1
      type: agent
      agent: no.such.handler
""",
            )
            result = self.engine.run(Workflow.load(path))
        self.assertEqual(result.step("s1").status, StepStatus.FAILED)  # type: ignore[union-attr]
        self.assertEqual(result.status, WorkflowStatus.FAILED)

    def test_unknown_yaml_key_rejected_at_load(self) -> None:
        with TempDir() as tmp:
            path = _write_workflow(
                tmp,
                """workflow:
  id: bad
  trigger: {kind: manual}
  steps:
    - id: s1
      type: agent
      agent: echo
      bogus_key: 1
""",
            )
            with self.assertRaises(WorkflowLoadError):
                Workflow.load(path)

    def test_retry_on_transient(self) -> None:
        with TempDir() as tmp:
            path = _write_workflow(
                tmp,
                """workflow:
  id: retry
  trigger: {kind: manual}
  steps:
    - id: flaky
      type: task
      task: flaky-task
      retry: 2
""",
            )
            calls = {"n": 0}

            def flaky(_p: object, _c: object) -> dict[str, object]:
                calls["n"] += 1
                if calls["n"] < 2:
                    raise TransientError("temporary")
                return {"ok": True}

            engine = WorkflowEngine(self.db, handlers={"flaky-task": flaky})
            result = engine.run(Workflow.load(path))
        self.assertEqual(result.status, WorkflowStatus.SUCCESS)
        self.assertEqual(calls["n"], 2)

    def test_runs_and_events_persisted(self) -> None:
        with TempDir() as tmp:
            path = _write_workflow(
                tmp,
                """workflow:
  id: persisted
  trigger: {kind: manual}
  steps:
    - id: s1
      type: agent
      agent: echo
      input: {message: hello}
""",
            )
            self.engine.run(Workflow.load(path))
        runs = self.db.conn_checked.execute("SELECT COUNT(*) c FROM runs").fetchone()["c"]
        self.assertEqual(runs, 1)
        run = self.db.conn_checked.execute("SELECT * FROM runs").fetchone()
        self.assertEqual(run["workflow_id"], "persisted")
        self.assertEqual(run["status"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
