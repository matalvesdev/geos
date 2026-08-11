# SPEC-002 — SQLite Storage & Migrations

- **State**: IMPLEMENTED + TESTED (2026-08-11) · **Status**: ACCEPTED
- **Layer**: Phase 0 Foundation

## Context / Problem
Local-first storage with zero infrastructure, forward migrations, and the ability to migrate to
other providers later (ADR-0002).

## Goals
- SQLite database at `.geos/geos.db` (configurable path), WAL mode, sane busy_timeout.
- Versioned migration system (`schema_version`, `migration_history`), forward-only in bootstrap.
- FTS5 available for knowledge tables.

## Non-goals
- Rollback DDL (bootstrap migrations are additive); distributed writes; shared storage.

## Requirements
R2.1 `connect()` with PRAGMAs (WAL, foreign_keys, busy_timeout). In-memory mode for tests.
R2.2 Migrations as ordered Python lists; `migrate()` applies pending in a transaction and records
     history; `current_version()`; idempotent re-runs.
R2.3 DDL (V1 bootstrap): `schema_version`, `migration_history`, `runs`, `events`, `jobs`,
     `documents`, `document_chunks`, `knowledge_nodes`, `knowledge_edges`, `approvals`.
R2.4 `document_chunks_fts` virtual table (FTS5, content-backed).

## Interfaces
```
Database.open(path=None) -> Database      Database.migrate() -> int (new version)
Database.current_version() -> int         Database.conn -> sqlite3.Connection (context-managed)
```

## Data model (core DDL)
- `runs` — see SPEC-001.
- `events(id, type, payload_json, trace_id, created_at)` — SPEC-004.
- `jobs(id, idempotency_key UNIQUE, kind, payload_json, status, attempts, max_attempts,
  run_after, last_error, trace_id, created_at, updated_at)` — SPEC-005.
- `documents(id, uri UNIQUE, title, doc_type, content_hash, source, metadata_json,
  created_at, updated_at)`; `document_chunks(id, document_id FK, chunk_index, heading,
  position, content, metadata_json)`; FTS5 external-content table — SPEC-010.
- `knowledge_nodes(id, workspace_id, node_type, name, canonical_name, description,
  metadata_json, confidence, source, created_at, updated_at)`;
  `knowledge_edges(id, workspace_id, source_node, target_node, relationship, weight,
  confidence, source, valid_from, valid_to, created_at)` — SPEC-013 (DDL now, engine later).
- `approvals(id, action, agent, risk, status, requested_at, decided_at, decision, decided_by,
  metadata_json)` — SPEC-019 (DDL now, engine later).

## Security
No secrets in DB. Path from config only. WAL files in state dir.

## Failure modes
Locked DB → busy_timeout then clear error. Duplicate migration → error with history hint.

## Tests / Acceptance
`test_migrations.py`: fresh DB → version N; re-run idempotent; history rows recorded; FTS table
queryable. `test_storage.py`: WAL enabled, foreign keys enforced.
