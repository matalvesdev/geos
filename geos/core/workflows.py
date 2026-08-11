"""Workflow engine (SPEC-007). Declarative YAML DSL with agents/tasks/approvals.

Infrastructure-agnostic: runs through step handlers; jobs/scheduler reuse the same
primitives (ADR-0003).
"""

from __future__ import annotations

import ast
import operator
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import yaml

from ..storage.database import Database
from ..storage.repos import Event, RepoFactory
from ..util import new_id, now_iso
from .events import SqliteEventBus
from .jobs import PermanentError, TransientError
from .telemetry import Telemetry


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    WAITING_APPROVAL = "WAITING_APPROVAL"


class WorkflowStatus(str, Enum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    WAITING_APPROVAL = "WAITING_APPROVAL"


class WorkflowLoadError(ValueError):
    """Invalid workflow definition (fails fast at load time, SPEC-007 R7.1)."""


@dataclass
class StepResult:
    id: str
    step_type: str
    status: StepStatus = StepStatus.PENDING
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0
    retries: int = 0


@dataclass
class WorkflowResult:
    workflow_id: str
    status: WorkflowStatus
    trace_id: str
    steps: list[StepResult]
    started_at: str = field(default_factory=now_iso)
    finished_at: str | None = None
    run_id: str | None = None

    def step(self, step_id: str) -> StepResult | None:
        return next((s for s in self.steps if s.id == step_id), None)


@dataclass
class StepDef:
    id: str
    step_type: str  # agent | task | approval
    agent: str | None = None
    task: str | None = None
    input: dict[str, Any] = field(default_factory=dict)
    condition: str | None = None
    retry: int = 0
    timeout_s: int | None = None
    approval_mode: str = "record"  # record | required
    parallel: list["StepDef"] = field(default_factory=list)

    @property
    def handler_name(self) -> str:
        return self.agent or self.task or self.id


@dataclass
class Workflow:
    id: str
    trigger: dict[str, Any]
    steps: list[StepDef]
    description: str | None = None
    source_path: Path | None = None

    @classmethod
    def load(cls, path: str | Path) -> "Workflow":
        path = Path(path)
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise WorkflowLoadError(f"invalid YAML in {path}: {exc}") from exc
        if not isinstance(raw, dict) or "workflow" not in raw:
            raise WorkflowLoadError(f"{path} must contain a 'workflow:' mapping")
        wf = raw["workflow"]
        if not isinstance(wf, dict):
            raise WorkflowLoadError("'workflow:' must be a mapping")
        wf_id = wf.get("id")
        if not wf_id:
            raise WorkflowLoadError("workflow requires an 'id'")
        trigger = wf.get("trigger") or {}
        if not isinstance(trigger, dict):
            raise WorkflowLoadError("'trigger' must be a mapping")
        steps_raw = wf.get("steps")
        if not isinstance(steps_raw, list) or not steps_raw:
            raise WorkflowLoadError("workflow requires a non-empty 'steps' list")
        steps = [_parse_step(s, i, path) for i, s in enumerate(steps_raw)]
        return cls(
            id=str(wf_id), trigger=trigger, steps=steps,
            description=wf.get("description"), source_path=path,
        )


def _parse_step(raw: Any, index: int, path: Path) -> StepDef:
    if not isinstance(raw, dict):
        raise WorkflowLoadError(f"step #{index} in {path} must be a mapping")
    unknown = set(raw) - {
        "id", "type", "agent", "task", "input", "condition", "retry", "timeout_s",
        "approval", "parallel",
    }
    if unknown:
        raise WorkflowLoadError(f"step #{index} in {path} has unknown key(s): {sorted(unknown)}")
    step_type = raw.get("type")
    if step_type not in ("agent", "task", "approval"):
        raise WorkflowLoadError(
            f"step #{index} in {path}: 'type' must be agent|task|approval, got {step_type!r}"
        )
    step_id = raw.get("id") or f"step{index}"
    parallel_raw = raw.get("parallel") or []
    parallel = (
        [_parse_step(p, index, path) for p in parallel_raw] if isinstance(parallel_raw, list) else []
    )
    approval_cfg = raw.get("approval") or {}
    mode = "record"
    if isinstance(approval_cfg, dict):
        mode = str(approval_cfg.get("mode") or mode)
    elif isinstance(approval_cfg, str):
        mode = approval_cfg
    return StepDef(
        id=str(step_id), step_type=step_type, agent=raw.get("agent"), task=raw.get("task"),
        input=dict(raw.get("input") or {}), condition=raw.get("condition"),
        retry=int(raw.get("retry") or 0),
        timeout_s=int(raw["timeout_s"]) if raw.get("timeout_s") is not None else None,
        approval_mode=mode, parallel=parallel,
    )

StepHandler = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any] | None]


class WorkflowEngine:
    """Executes workflows. Handlers are closures bound to db/bus/queue (registry, no eval)."""

    def __init__(
        self,
        db: Database,
        handlers: dict[str, StepHandler] | None = None,
        workspace_id: str = "default",
    ) -> None:
        self._db = db
        self._repo = RepoFactory(db)
        self._telemetry = Telemetry(db, workspace_id=workspace_id)
        self._handlers = dict(default_handlers(db))
        if handlers:
            self._handlers.update(handlers)

    def run(self, workflow: Workflow, inputs: dict[str, Any] | None = None,
            trace_id: str | None = None) -> WorkflowResult:
        inputs = inputs or {}
        ctx = self._telemetry.start(
            workflow_id=workflow.id, trace_id=trace_id or new_id(),
        )
        trace_id = ctx.run.trace_id
        steps = [StepResult(id=s.id, step_type=s.step_type) for s in workflow.steps]
        result = WorkflowResult(
            workflow_id=workflow.id, status=WorkflowStatus.RUNNING,
            trace_id=trace_id, steps=steps, started_at=now_iso(),
            run_id=ctx.run.id,
        )
        context: dict[str, Any] = {"inputs": inputs, "steps": {}, "trace_id": trace_id}
        decisions = inputs.get("approvals") or {}

        for step_def, step_result in zip(workflow.steps, steps):
            if result.status != WorkflowStatus.RUNNING:
                step_result.status = StepStatus.SKIPPED
                continue
            if step_def.condition:
                try:
                    condition_ok = evaluate_condition(step_def.condition, context)
                except ConditionError as exc:
                    step_result.status = StepStatus.FAILED
                    step_result.error = f"condition error: {exc}"
                    context["steps"][step_def.id] = {
                        "status": "FAILED", "error": step_result.error,
                    }
                    continue
                if not condition_ok:
                    step_result.status = StepStatus.SKIPPED
                    context["steps"][step_def.id] = {"status": "SKIPPED"}
                    continue
            if step_def.step_type == "approval":
                self._run_approval_step(step_def, step_result, result, context, decisions)
                context["steps"][step_def.id] = {
                    "status": step_result.status.value, "output": step_result.output,
                }
                if step_result.status == StepStatus.WAITING_APPROVAL:
                    result.status = WorkflowStatus.WAITING_APPROVAL
                    self._repo.events.insert(Event(
                        event_type="approval.required",
                        payload={"workflow_id": workflow.id, "step": step_def.id},
                        trace_id=trace_id,
                    ))
                continue
            self._run_regular_step(step_def, step_result, context, trace_id)

        finished = all(
            s.status in (StepStatus.SUCCESS, StepStatus.SKIPPED) for s in steps
        )
        result.finished_at = now_iso()
        if result.status == WorkflowStatus.RUNNING:
            result.status = WorkflowStatus.SUCCESS if finished else WorkflowStatus.FAILED
        ctx.finish(result.status.value, error=self._first_error(steps))
        return result

    # ---- step execution -----------------------------------------------------
    def _run_regular_step(self, step: StepDef, step_result: StepResult,
                          context: dict[str, Any], trace_id: str) -> None:
        handler = self._handlers.get(step.handler_name)
        if handler is None:
            step_result.status = StepStatus.FAILED
            step_result.error = f"no handler registered for {step.handler_name!r}"
            context["steps"][step.id] = {"status": "FAILED", "error": step_result.error}
            return
        step_input = _resolve_input(step.input, context)
        started = time.monotonic()
        last_error: str | None = None
        for attempt in range(step.retry + 1):
            step_result.retries = attempt
            try:
                out = handler(step_input, {"trace_id": trace_id, "step": step.id})
                step_result.output = dict(out or {})
                step_result.status = StepStatus.SUCCESS
                step_result.duration_ms = int((time.monotonic() - started) * 1000)
                context["steps"][step.id] = {
                    "status": "SUCCESS", "output": step_result.output,
                }
                if step.timeout_s and step_result.duration_ms > step.timeout_s * 1000:
                    step_result.status = StepStatus.FAILED
                    step_result.error = f"timeout after {step.timeout_s}s"
                    context["steps"][step.id] = {"status": "FAILED", "error": step_result.error}
                return
            except TransientError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                time.sleep(min(2 ** attempt, 10) / 100)
            except PermanentError as exc:
                step_result.status = StepStatus.FAILED
                step_result.error = f"{type(exc).__name__}: {exc}"
                context["steps"][step.id] = {"status": "FAILED", "error": step_result.error}
                return
            except Exception as exc:  # noqa: BLE001 - record and fail step
                step_result.status = StepStatus.FAILED
                step_result.error = f"{type(exc).__name__}: {exc}"
                context["steps"][step.id] = {"status": "FAILED", "error": step_result.error}
                return
        step_result.status = StepStatus.FAILED
        step_result.error = last_error or "exhausted retries"
        context["steps"][step.id] = {"status": "FAILED", "error": step_result.error}

    def _run_approval_step(self, step: StepDef, step_result: StepResult,
                           result: WorkflowResult, context: dict[str, Any],
                           decisions: dict[str, Any]) -> None:
        decision = decisions.get(step.id)
        if step.approval_mode == "required" and decision is None:
            step_result.status = StepStatus.WAITING_APPROVAL
            self._repo.approvals.request(
                action=step.id, agent=None,
                risk="HUMAN_APPROVAL_REQUIRED",
                metadata={"workflow_id": result.workflow_id, "trace_id": result.trace_id},
            )
            step_result.output = {"approval_required": True}
            return
        if step.approval_mode == "required" and decision is True:
            step_result.status = StepStatus.SUCCESS
            step_result.output = {"approved": True}
            return
        if step.approval_mode == "required" and decision is False:
            step_result.status = StepStatus.REJECTED
            step_result.output = {"approved": False}
            return
        # record mode: non-blocking audit row (decided by system)
        approval = self._repo.approvals.request(
            action=step.id, risk="RECORDED",
            metadata={"workflow_id": result.workflow_id, "trace_id": result.trace_id},
        )
        self._repo.approvals.decide(approval.id, "recorded", "system")
        step_result.status = StepStatus.SUCCESS
        step_result.output = {"approval_id": approval.id, "recorded": True}

    # ---- helpers ------------------------------------------------------------
    @staticmethod
    def _first_error(steps: list[StepResult]) -> str | None:
        for s in steps:
            if s.error:
                return s.error
        return None


def _resolve_input(step_input: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Support $ref lookups like input: {topic: "$ref steps.research.summary.topic"}."""
    resolved: dict[str, Any] = {}
    for key, value in step_input.items():
        if isinstance(value, str) and value.startswith("$ref "):
            resolved[key] = _resolve_ref(value[5:], context)
        else:
            resolved[key] = value
    return resolved


class ConditionError(ValueError):
    """Condition could not be evaluated (malformed or unsupported construct)."""


# Restricted AST evaluator for workflow `condition:` expressions (SPEC-007 R7.6).
# No calls, no imports, no dunder access, no attribute chains beyond dict lookups.
_ALLOWED_BINOPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}

_ALLOWED_CMPOPS: dict[type[ast.cmpop], Callable[[Any, Any], bool]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


def evaluate_condition(expression: str, context: dict[str, Any]) -> bool:
    """Evaluate a condition expression in a restricted, deterministic namespace.

    Supported: literals, names (from context), attribute access on context dicts,
    comparisons, and/or/not, arithmetic (+ - * // %). Anything else raises
    ConditionError (which fails the step — never silently skips, SPEC-007).
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ConditionError(f"invalid expression: {exc}") from exc
    try:
        value = _ConditionEvaluator(context).visit(tree.body)
    except ConditionError:
        raise
    except Exception as exc:  # noqa: BLE001 - runtime evaluation errors are condition errors
        raise ConditionError(f"evaluation failed: {exc}") from exc
    return bool(value)


class _ConditionEvaluator:
    def __init__(self, context: dict[str, Any]) -> None:
        self._ctx = context

    def visit(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in self._ctx:
                raise ConditionError(f"unknown name {node.id!r}")
            return self._ctx[node.id]
        if isinstance(node, ast.Attribute):
            base = self.visit(node.value)
            if isinstance(base, dict):
                return base.get(node.attr)
            return None
        if isinstance(node, ast.Compare):
            left = self.visit(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = self.visit(comparator)
                cmp_fn = _ALLOWED_CMPOPS.get(type(op))
                if cmp_fn is None:
                    raise ConditionError(f"unsupported comparison {type(op).__name__}")
                if not cmp_fn(left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(self.visit(v) for v in node.values)
            if isinstance(node.op, ast.Or):
                return any(self.visit(v) for v in node.values)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not self.visit(node.operand)
        if isinstance(node, ast.BinOp):
            op_fn = _ALLOWED_BINOPS.get(type(node.op))
            if op_fn is None:
                raise ConditionError(f"unsupported operator {type(node.op).__name__}")
            return op_fn(self.visit(node.left), self.visit(node.right))
        raise ConditionError(f"unsupported construct {type(node).__name__}")


def _resolve_ref(path: str, context: dict[str, Any]) -> Any:
    parts = [p for p in path.split(".") if p]
    if not parts:
        return None
    if parts[0] == "steps" and len(parts) >= 2:
        step_entry = context.get("steps", {}).get(parts[1]) or {}
        rest = parts[2:]
        if not rest:
            return step_entry.get("output")
        return _deep_get(step_entry.get("output"), rest)
    if parts[0] == "inputs":
        return _deep_get(context.get("inputs"), parts[1:])
    return _deep_get(context, parts)


def _deep_get(node: Any, keys: list[str]) -> Any:
    for key in keys:
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            return None
    return node


# --- default deterministic step handlers (first vertical slice mocks, SPEC-007) ------
def default_handlers(db: Database) -> dict[str, StepHandler]:
    from ..intelligence.knowledge import search  # local import to avoid cycles

    def handle_echo(inputs: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        return {"echo": inputs.get("message", inputs)}

    def handle_knowledge_search(inputs: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        hits = search(db, query=str(inputs.get("query", "")), limit=int(inputs.get("limit", 5)))
        return {"hits": hits, "count": len(hits)}

    def handle_research_summary(inputs: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        topic = str(inputs.get("topic", "undefined"))
        return {
            "topic": topic,
            "summary": f"[mock-research] Síntese determinística sobre: {topic}",
            "signals": ["signal-1", "signal-2"],
            "mock": True,
        }

    def handle_content_draft(inputs: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        # Persists through the ContentEngine: idea → brief → draft (SPEC-022).
        # Idempotent per topic: reuses the most recent unarchived draft of the
        # same topic so scheduled runs don't accumulate duplicate ideas.
        from ..domains.content import ContentEngine

        topic = str(inputs.get("topic", "undefined"))
        engine = ContentEngine(db)
        item_id: str | None = None
        for candidate in engine.list(limit=50):
            if (candidate.get("topic") or "").strip().lower() == topic.strip().lower() \
                    and candidate["status"] in ("IDEA", "BRIEFED", "DRAFTED"):
                item_id = candidate["id"]
                break
        if item_id is None:
            created = engine.create_idea(
                topic=topic, content_type=str(inputs.get("content_type", "blog_post")),
                keywords=[str(k) for k in (inputs.get("keywords") or [])],
                source_workflow=ctx.get("trace_id"),
            )
            item_id = created["id"]
        current = engine.get(item_id)
        if current["status"] == "IDEA":
            engine.write_brief(item_id, audience=inputs.get("audience"),
                               objective=inputs.get("objective"),
                               cta=inputs.get("cta"))
        engine.produce_draft(item_id)
        record = engine.get(item_id)
        return {
            "content_id": record["id"], "title": record["title"],
            "slug": record["slug"], "brief": record["brief"],
            "status": record["status"], "score": record.get("score"),
            "mock": True,
        }

    def handle_content_ideate(inputs: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from ..domains.content import ContentEngine

        topic = str(inputs.get("topic", "undefined"))
        item = ContentEngine(db).create_idea(
            topic=topic, content_type=str(inputs.get("content_type", "blog_post")),
            keywords=[str(k) for k in (inputs.get("keywords") or [])],
        )
        return {"content_id": item["id"], "title": item["title"],
                "status": item["status"], "score": item.get("score"),
                "breakdown": item.get("score_breakdown"), "mock": True}

    def handle_social_draft(inputs: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        title = str(inputs.get("title", "conteúdo"))
        return {
            "platform": "linkedin",
            "copy": f"[mock-social] Aprendizado sobre: {title}",
            "mock": True,
        }

    def handle_brand_review(inputs: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        return {
            "approved": True,
            "notes": "brand-review mock determinístico (sem alegações de resultado)",
            "mock": True,
        }

    def handle_approval_gate(inputs: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        # Record-only gate used as a task when explicit approval steps are not needed.
        return {"gated": True, "step": ctx.get("step")}

    def handle_research_run(inputs: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        from ..domains.research import ResearchEngine

        engine = ResearchEngine(db)
        report = engine.run(
            str(inputs.get("question", "")),
            sources_limit=int(inputs.get("sources_limit", 5)),
            trace_id=ctx.get("trace_id"),
        )
        return {
            "research_id": report.id, "question": report.question,
            "synthesis": report.synthesis, "sources_count": len(report.sources),
            "insights": report.insights, "mock": report.mock,
        }

    def handle_content_brief(inputs: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        topic = str(inputs.get("topic", "undefined"))
        return {
            "topic": topic,
            "audience": "financial operations practitioners",
            "funnel_stage": "consideration",
            "objective": "educate",
            "outline": [
                f"O problema: {topic}",
                "Processo e evidência",
                "Como aplicar na operação",
                "Próximos passos",
            ],
            "cta": "Falar com especialista",
            "hypothesis": f"Conteúdo sobre '{topic}' gera interesse mensurável (a validar)",
            "mock": True,
        }

    def handle_schedule_record(inputs: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        from ..core.events import EventTypes

        title = str(inputs.get("title", ""))
        platform = str(inputs.get("platform", "blog"))
        SqliteEventBus(db).publish(
            EventTypes.CONTENT_SCHEDULED,
            {"title": title, "platform": platform, "status": "SCHEDULED"},
            trace_id=ctx.get("trace_id"),
        )
        return {"scheduled": True, "title": title, "platform": platform,
                "status": "SCHEDULED", "scheduled_at": now_iso()}

    return {
        "echo": handle_echo,
        "knowledge.search": handle_knowledge_search,
        "research.summary": handle_research_summary,
        "research.run": handle_research_run,
        "content.brief": handle_content_brief,
        "content.ideate": handle_content_ideate,
        "content.draft": handle_content_draft,
        "social.draft": handle_social_draft,
        "brand.review": handle_brand_review,
        "approval.gate": handle_approval_gate,
        "schedule.record": handle_schedule_record,
    }
