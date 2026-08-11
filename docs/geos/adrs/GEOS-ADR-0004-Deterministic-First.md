# GEOS-ADR-0004 — Deterministic First, LLM Last

- **Status**: Accepted
- **Date**: 2026-08-11
- **Context**: The master spec (§43) mandates deterministic logic for anything traditional code
  solves better (dates, slugs, validation, scoring, deduplication, scheduling, calculations,
  schema parsing, rate limiting), reserving LLMs for reasoning, synthesis, qualitative analysis,
  writing, planning and complex classification.
- **Decision**: All bootstrap implementations that can be deterministic **are** deterministic:
  cron parsing (own parser, SPEC-006), FTS search (SQLite FTS5, SPEC-010), idempotency keys,
  chunking, capability detection heuristics (SPEC-009), mode detection (SPEC-008), slug/ID
  generation. LLM boundaries appear only where reasoning is required, always behind
  `ModelProvider` (planned).
- **Alternatives**: LLM-based mode detection (rejected: unnecessary cost, nondeterministic);
  third-party cron lib (rejected: single tiny parser is sufficient and dependency-free).
- **Consequences**: (+): cheap, fast, testable, auditable. (−): heuristic detectors may need
  iteration as real-world codebases vary — evidence and confidence are recorded, never hidden.
