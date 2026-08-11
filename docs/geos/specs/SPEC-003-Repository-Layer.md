# SPEC-003 — Repository Layer

- **State**: IMPLEMENTED + TESTED (2026-08-11) · **Status**: ACCEPTED
- **Layer**: Phase 0 Foundation

## Context / Problem
No domain may depend on SQLite directly (ADR-0002). Repositories define the persistence contract;
SQLite is one implementation, other providers plug in later.

## Goals
- Typed repositories for the bootstrap entities: Runs, Events, Jobs, Documents/Chunks,
  Knowledge nodes/edges, Approvals.
- CRUD + queries used by CLI and engines; `search` via FTS where applicable.
- Workspace-scoped query helpers (`workspace_id` defaulting).

## Non-goals
- Generic ORM; cross-provider SQL dialect handling beyond bootstrap needs.

## Requirements
R3.1 Repositories constructed with a `Database`; a `RepoFactory` exposes them.
R3.2 `RunRepository`: insert, list (filter by status), get, finish.
R3.3 `EventRepository`: publish, list by type, list by trace.
R3.4 `JobRepository`: enqueue (idempotency), claim_next, complete, fail, deadletter, list.
R3.5 `KnowledgeRepository`: upsert document (by URI) with content_hash dedup; add chunks;
     search via FTS with snippet; node/edge upsert + list.
R3.6 `ApprovalRepository`: request, list pending, decide.

## Interfaces
```
factory = RepoFactory(db)
factory.runs / factory.events / factory.jobs / factory.knowledge / factory.approvals
```

## Security
Parameterized SQL only (no string interpolation of values).

## Failure modes
Constraint violation (duplicate URI / idempotency key) → typed `IntegrityError` wrapper
(`DuplicateKeyError`) that callers map to idempotent success or user error.

## Tests / Acceptance
Repository CRUD tests against in-memory SQLite; duplicate-URI upsert keeps content_hash fresh;
FTS search returns expected chunks.
