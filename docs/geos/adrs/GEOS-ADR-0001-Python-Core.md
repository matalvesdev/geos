# GEOS-ADR-0001 — GEOS Core in Python

- **Status**: Accepted
- **Date**: 2026-08-11
- **Deciders**: Founder (via GEOS master spec §172), GEOS bootstrap
- **Context**: GEOS is a new standalone open-source framework. The product stacks in this workspace
  are Java 21/Spring Boot (Zetra One API) and TypeScript/React (web). The GEOS spec explicitly
  prescribes Python quality standards: type hints, Pydantic/dataclasses, Protocols/interfaces,
  asyncio when useful, clean boundaries, tests, lint/format/static analysis. Python is already
  present in this workspace's doc-engineering tooling.
- **Decision**: The GEOS Core and its CLI are implemented in **Python 3.11+** (runtime here: 3.14),
  with a dependency surface of **stdlib + PyYAML** for the bootstrap. Structured outputs use
  dataclasses/Pydantic-style typed models (stdlib `dataclasses` in bootstrap; Pydantic is an
  optional dependency, never required for the core loop).
- **Alternatives**: TypeScript/Node (rejected: duplicates an existing stack and departs from spec
  prescriptions); Java/Spring Boot (rejected: poor fit for local-first SQLite-first agent tooling).
- **Consequences**: (+): spec-aligned, zero-infra, fast to iterate, natural SQLite integration.
  (−): two runtime languages in the organization; GEOS must never couple to the product's Java/TS
  internals — it interacts via files, git, APIs and adapters only.
