# SPEC-005 — Job System

- **State**: IMPLEMENTED + TESTED (2026-08-11) · **Status**: ACCEPTED
- **Layer**: Phase 0 Foundation · ADR-0003

## Context / Problem
Work must be queued, retried, timed out and dead-lettered, with idempotency — deterministically
and locally.

## Goals
- `JobQueue` (protocol) + in-process SQLite-backed implementation.
- Job statuses: PENDING → RUNNING → SUCCESS | FAILED | RETRYING | CANCELLED | WAITING_APPROVAL
  (WAITING_APPROVAL reserved for approval engine, SPEC-019).
- `idempotency_key` uniqueness prevents duplicate execution (posts, emails, meetings,
  experiments, artifacts — spec §51).
- `Worker` pulls due jobs, executes handlers, applies retry policy (max attempts, exponential
  backoff with jitter) and dead-letters terminal failures.

## Non-goals
- Cross-process workers; priority queues; distributed locking (single-writer SQLite).

## Requirements
R5.1 `enqueue(kind, payload, idempotency_key=None, run_after=None, max_attempts=3)`.
R5.2 Duplicate `idempotency_key` → returns existing job (no double execution).
R5.3 `Worker.register(kind, handler)`; `worker.run_once()` and `worker.run_until_idle()`.
R5.4 Retry on `TransientError` only; permanent errors fail immediately.
R5.5 Jobs past `max_attempts` → DEAD status with `last_error`.

## Interfaces
```
queue.enqueue(...); worker = Worker(queue, retry_backoff_base=2)
worker.register("social.publish", fn)
worker.run_until_idle(timeout_s=…)
```

## Security
Handlers resolved from a registry (no arbitrary code execution from payloads).

## Failure modes
Transient → retried with backoff; permanent → dead-lettered with error trace; never infinite.

## Tests / Acceptance
`test_jobs.py`: enqueue→run; idempotency duplicate; retry counting; backoff; permanent failure →
DEAD; run_after not executed early.
