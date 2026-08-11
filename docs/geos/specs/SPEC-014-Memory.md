# SPEC-014 — Memory System

- **State**: IMPLEMENTED + TESTED (2026-08-11) · **Status**: ACCEPTED
- **Layer**: Phase 1 — Knowledge

## Context / Problem
Agents and workflows need short-lived, scoped state with policy attributes (spec §32–§33):
source, confidence, retention/TTL, sensitivity, deletion policy. Bootstrap implements the
storage + a working-memory wrapper; specialized memory types (lead/customer/campaign) are
scoped keys on the same store.

## Goals
- `memories` table (migration V2) with scope/key/value, source, confidence, sensitivity,
  retention_seconds, expires_at.
- `MemoryStore`: put/get/list/delete with TTL expiry on read.
- `WorkingMemory`: in-process dict with clear() (no persistence) for short-lived state.

## Non-goals
- Distributed memory; embeddings of memories; per-entity agents in bootstrap.

## Requirements
R14.1 put(scope, key, value, source, confidence, sensitivity="INTERNAL", ttl_seconds=None).
R14.2 get(scope, key): expired entries are deleted and return None.
R14.3 list(scope=None) returns live entries; delete(scope, key).
R14.4 Unique (scope, key); puts overwrite and refresh expires_at.

## Interfaces
```
mem = MemoryStore(db)
mem.put("session", "topic", "origem de crédito", ttl_seconds=3600)
mem.get("session", "topic")
wm = WorkingMemory(); wm["x"] = 1; wm.clear()
```

## Security
Sensitivity defaults INTERNAL; PII/SECRET values must be explicitly marked; no secrets.

## Tests / Acceptance
`test_memory.py`: put/get; TTL expiry; overwrite refresh; list filtering; delete.
