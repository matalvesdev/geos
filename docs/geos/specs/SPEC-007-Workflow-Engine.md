# SPEC-007 — Workflow Engine

- **State**: IMPLEMENTED + TESTED (2026-08-11) · **Status**: ACCEPTED
- **Layer**: Phase 0 Foundation · ADR-0003/0004

## Context / Problem
Automations need a declarative DSL mapping triggers → steps (agents/tasks/approvals) with
conditions, parallelism, retry and timeouts — infra-agnostic (SPEC-005/006).

## Goals
- YAML DSL: `workflow.id`, `trigger` (cron/interval/event/manual), ordered `steps`.
- Step types: `agent` (resolves a registered step handler), `task` (inline callable name),
  `approval` (records an approval request and, in auto mode, allows proceed).
- Step fields: `id`, `type`, `agent`/`task`, `input` (static YAML or `$ref` of previous outputs),
  `condition` (expression over step outputs — safe, evaluated via restricted namespace),
  `retry` (max_attempts), `timeout_s`, `parallel` (list of nested steps for fan-out).
- Every run creates a `runs` row + trace; step outputs JSON-serializable and merged for next step.
- Deterministic mock step handlers included (`echo`, `knowledge.search`,
  `content.draft_proposal`, `social.draft`, `approval.gate`) for the first vertical slice; real
  agents register the same interface.

## Non-goals
- Full BPEL-style orchestration; long-running suspend/resume across processes; human UI.

## Requirements
R7.1 `Workflow.load(path)` validates schema (unknown keys → error).
R7.2 `Engine.run(workflow, inputs, trace_id)` executes steps; `condition` false → step skipped
     (status `SKIPPED`, recorded).
R7.3 Parallel steps run sequentially but outputs are collected in order (deterministic);
     concurrent execution is a later worker concern.
R7.4 Approval steps with `mode: required` → workflow pauses at `WAITING_APPROVAL` unless
     `approve: true` input given (shadow/CI use); `mode: record` → non-blocking record.
R7.5 Retry honored via job-like loop inside engine for transient step failures.
R7.6 Workflows discoverable: `geos workflows list` reads `geos.yaml` `workflows.dir`
     (default `geos/workflows/*.yaml`).

## Interfaces
```
wf = Workflow.load("geos/workflows/daily.yaml")
engine = Engine(registry, bus, queue, approvals)
result = engine.run(wf, inputs={"date": ...})
result.steps[i].status / .output / .duration_ms
```

## Security
`condition` evaluated in a restricted namespace (no imports, no attribute access beyond provided
context). Step names resolved only from the registered registry.

## Failure modes
Unknown agent → validation error at load time. Step timeout → FAILED with error. Condition error →
step FAILED, run FAILED (never silently continues).

## Tests / Acceptance
`test_workflows.py`: happy path with outputs chaining; condition skip; approval required blocks
then proceeds on approve; unknown agent fails fast; parallel fan-out; retry on transient failure;
runs/events persisted.
