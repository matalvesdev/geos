# SPEC-012 — Hybrid RAG & Retrieval

- **State**: IMPLEMENTED + TESTED (2026-08-11) · **Status**: ACCEPTED
- **Layer**: Phase 1 — Knowledge · ADR-0006

## Context / Problem
Single-signal retrieval misses the real intent mix: keywords (FTS), semantics (vectors) and
relations (graph). The spec (§21–§24) requires a configurable pipeline with merge, rerank,
context build and citations — never fixed weights.

## Goals
- `HybridRetriever.search(query)`: FTS5 + vector + graph-adjacency signals merged with
  **configurable weights** (`RetrievalConfig`), heuristic rerank, provenance per hit.
- `build_context(query, hits)`: ordered context with **citations** (document uri, chunk,
  heading, source, score) and a token estimate.
- Graph boost: when the query matches known TOPIC entities, hits on related documents are
  boosted (deterministic, documented heuristic).

## Non-goals
- Model-based rerankers (interface reserved); answer generation (LLM is a later concern).

## Requirements
R12.1 `RetrievalConfig`: fts_weight (0.4), vector_weight (0.4), graph_weight (0.2), limit,
     doc_type filter. Overridable via constructor.
R12.2 Merge by chunk_id; FTS score normalized (1/(1+|bm25|)); vector score = cosine;
     combined = fts_w·fts_norm + vec_w·cos + graph_boost.
R12.3 Each hit carries `provenance: list[str]` (e.g. "fts", "vector", "graph").
R12.4 `ContextBundle`: query, hits, citations (deduped), tokens_estimate (chars/4).
R12.5 Deterministic ordering: score desc, then chunk position asc.

## Interfaces
```
config = RetrievalConfig(fts_weight=0.4, vector_weight=0.4, graph_weight=0.2)
retriever = HybridRetriever(db, config=config)
hits = retriever.search("origem de crédito")
ctx = retriever.build_context("origem de crédito", hits)
```

## Security
Queries sanitized as in SPEC-010; no SQL interpolation.

## Failure modes
No embeddings indexed → vector signal contributes 0 (no crash, provenance notes "vector:empty").

## Tests / Acceptance
`test_retrieval.py`: hybrid merge favors relevant chunk; weights change ordering; provenance
present; context citations dedupe; empty vector corpus doesn't crash.
