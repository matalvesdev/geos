# GEOS-ADR-0002 — SQLite-First Storage with Repository Abstraction

- **Status**: Accepted
- **Date**: 2026-08-11
- **Context**: GEOS must run with no external infrastructure (no PostgreSQL/Redis/Kafka/Neo4j/
  Qdrant) for the first workflow. In brownfield installations, an existing database must never be
  assumed to be replaceable by SQLite — SQLite is the local-first default, not an imposition.
- **Decision**:
  1. Default storage is **SQLite** at `.geos/geos.db` (isolated mode default in brownfield).
  2. No domain depends on SQLite directly: all persistence goes through **repositories**
     (SPEC-003) defined by interfaces/protocols.
  3. Storage provider (`sqlite` now; `postgres`, object/vector/graph later) is selected via
     `geos.yaml` (`storage.provider`), enabling future `REUSE` of existing infrastructure.
- **Alternatives**: shared PostgreSQL schema in brownfield (allowed via config, not default);
  object storage as default (rejected: premature).
- **Consequences**: (+): zero-infra, portable, testable via in-memory SQLite. (−): concurrency is
  single-writer (WAL + busy_timeout mitigate); migrations must stay forward/backward compatible.
