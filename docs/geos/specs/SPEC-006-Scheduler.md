# SPEC-006 — Scheduler

- **State**: IMPLEMENTED + TESTED (2026-08-11) · **Status**: ACCEPTED
- **Layer**: Phase 0 Foundation · ADR-0004

## Context / Problem
Automations fire on cron, interval, event, manual or conditional triggers. Bootstrap needs cron
and interval without third-party dependencies (own minimal cron parser — deterministic first).

## Goals
- `Schedule` dataclass: kind in {cron, interval, event, manual, conditional}.
- Own cron parser for 5-field expressions (`minute hour dom month dow`) supporting `*`, lists,
  ranges, steps, and `*/n`; deterministic `next_after()` (no DST handling).
- `Scheduler` that converts schedules into `run_after` jobs and supports `run_due()`.

## Non-goals
- Timezone/DST correctness beyond a fixed `tz` offset; high-frequency (<1 min) scheduling;
  persistent cron daemon across restarts (jobs are recreated by workflow definitions).

## Requirements
R6.1 `CronExpr.parse("*/15 * * * *")`; `next_after(now)` strictly after now.
R6.2 Interval schedules: `next = last + seconds`.
R6.3 `Scheduler.add(job_kind, schedule, payload)`; `run_due(now)` enqueues due triggers with
     stable idempotency keys (prevents duplicate enqueue when run repeatedly).
R6.4 Schedules are declarative (YAML in workflows; configurable).

## Interfaces
```
cron = CronExpr.parse("0 9 * * 1-5")
next_ = cron.next_after(utc_now())
scheduler = Scheduler(queue)
scheduler.add("workflow.run", Schedule(cron="0 9 * * 1-5"), {"workflow_id": "daily"})
scheduler.run_due(utc_now())
```

## Security
Parsing is strict; invalid expressions raise `CronSyntaxError` with position.

## Failure modes
Malformed cron → error at definition time (fail fast), never silently skipped.

## Tests / Acceptance
`test_cron.py`: stars, lists, ranges, steps, `*/n`, invalid expressions; `next_after` boundaries
(e.g., 23:59). `test_scheduler.py`: interval due logic; idempotent enqueue on repeated `run_due`.
