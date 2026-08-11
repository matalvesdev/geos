# SPEC-013 — Knowledge Graph (SQLite)

- **State**: IMPLEMENTED + TESTED (2026-08-11) · **Status**: ACCEPTED
- **Layer**: Phase 1 — Knowledge · ADR-0002

## Context / Problem
The graph (nodes/edges in SQLite, spec §26–§31) should surface relations that plain search
misses: CONTENT → discusses → TOPIC; PRODUCT → solves → PROBLEM; TOPIC co-occurrence. Bootstrap
extraction is **deterministic and rule-based** (ADR-0004); recall is intentionally modest and
confidence/provenance are always recorded.

## Goals
- `knowledge_nodes` / `knowledge_edges` engine on SQLite (tables exist since V1; engine now).
- `RuleBasedExtractor`: entity dictionary (configurable) + deterministic patterns; classifies
  entity type (COMPANY/PRODUCT/TOPIC/PROBLEM/…), confidence, source (document uri).
- `GraphService`: upsert nodes/edges, neighbors, related documents by topic, stats.
- CLI: `geos graph extract` (over ingested docs) and `geos graph inspect`.

## Non-goals
- LLM entity extraction (later); temporal validity beyond columns (valid_from/valid_to exist);
  traversal beyond 1-hop.

## Requirements
R13.1 Extractor input: entity dictionary `{name: node_type}` (defaults seeded + config
     override), patterns for capitalized phrases, TOPIC keyword list, PROBLEM phrase patterns.
R13.2 Extracted entities → `upsert_node` (canonical name = slug) with confidence + source.
R13.3 Edges: CONTENT(doc) → discusses → TOPIC (when topic appears in chunk);
     TOPIC → relates_to → TOPIC (co-occurrence ≥ 2 chunks, weight = co-occurrence);
     PRODUCT → solves → PROBLEM (dictionary-driven).
R13.4 `related_documents(topics)`: uris of documents discussing any of the topics.
R13.5 `neighbors(node_id)`, `stats()` (counts by type).

## Interfaces
```
extractor = RuleBasedExtractor(entities=settings_entities)
result = extractor.process_document(db, document_id, uri, title, chunks)
graph = GraphService(db)
graph.related_documents(["origem de crédito"]) -> [uris]
graph.stats() -> {"nodes": n, "edges": m, "by_type": {...}}
```

## Security
Only documents/entities already in the workspace are processed; no web crawling.

## Failure modes
Dictionary entity duplicated in text → upsert is idempotent (update, not duplicate).

## Tests / Acceptance
`test_graph.py`: known entity extracted with confidence; CONTENT→TOPIC edges created;
co-occurrence edge weight; related_documents; idempotent re-extraction; stats.
