# SPEC-021 — Research Engine

- **State**: IMPLEMENTED + TESTED (2026-08-11) · **Status**: ACCEPTED
- **Layer**: Phase 1 — Research · ADR-0004

## Context / Problem
The first vertical slice starts with research (spec §55–§56). Bootstrap research is
**deterministic over the local knowledge base**: QUESTION → PLAN → SOURCES → EXTRACTION →
SYNTHESIS → INSIGHT → KNOWLEDGE, with provenance preserved and every claim classified
(FACT/OPINION/ASSUMPTION/INFERENCE per §56). No fabricated facts: synthesis is explicitly
marked as a deterministic mock until a ModelProvider exists.

## Goals
- `ResearchEngine.run(question)`: returns a typed `ResearchReport`.
- Sources come from the local knowledge index (HybridRetriever) — real, with provenance.
- Extractions are direct quotes (snippets) with `classification: SOURCE_QUOTE` and evidence uri.
- Synthesis is a deterministic template marked `mock: True` — never implies causality.
- Outputs persist: `research` row, `insights` rows, INSIGHT knowledge nodes, and a
  `research.completed` event.
- CLI: `geos research run "pergunta"`.

## Non-goals
- Live web research (connectors later); LLM synthesis; competitor monitoring.

## Requirements
R21.1 Pipeline steps recorded in the plan (context/discover/sources/synthesize/insights).
R21.2 Sources = top hybrid hits with score + snippet + uri (provenance kept).
R21.3 Extractions = top-N quotes with classification and evidence.
R21.4 Insights: OBSERVATION (from source titles) + HYPOTHESIS (template, `needs_validation`).
R21.5 Persistence + event `research.completed` with report id.

## Interfaces
```
engine = ResearchEngine(db)
report = engine.run("origem de crédito bancário", sources_limit=5)
report.sources / report.synthesis / report.insights / report.mock
```

## Security
No external calls in bootstrap; queries sanitized.

## Failure modes
Empty knowledge base → sources empty; report still produced with `empty: true` and an
explicit note (never invent sources).

## Tests / Acceptance
`test_research.py`: report structure; sources from ingested docs; synthesis marked mock;
research/insights rows persisted; INSIGHT nodes created; event published; empty corpus
handled gracefully.
