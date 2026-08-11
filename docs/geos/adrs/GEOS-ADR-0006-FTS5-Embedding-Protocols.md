# GEOS-ADR-0006 — FTS5 Now, Embeddings Behind Protocols

- **Status**: Accepted
- **Date**: 2026-08-11
- **Context**: The knowledge layer needs search in the first vertical slice. SQLite 3.50 ships
  FTS5 (verified). Embeddings require a provider (cloud or local model) and storage (vector
  index) that should not couple the core to a vendor.
- **Decision**:
  1. **FTS5 is the search implementation** for the bootstrap (documents + chunks), with
     BM25-style ranking and deterministic filtering (SPEC-010).
  2. `EmbeddingProvider` (embed_text/embed_batch/dimension/metadata) and `VectorStore`
     (upsert/delete/search/hybrid_search/filter) are defined as **protocols** now; local and
     vendor implementations come later. Hybrid RAG composes FTS + vector + (future) graph behind
     configurable weights.
- **Alternatives**: SQLite FTS4 (rejected: FTS5 is available and superior); vendor vector DB by
  default (rejected: violates local-first).
- **Consequences**: (+): search works today with zero deps; vendor coupling is impossible by
  construction. (−): embedding-based semantic search and hybrid reranking are roadmap items.
