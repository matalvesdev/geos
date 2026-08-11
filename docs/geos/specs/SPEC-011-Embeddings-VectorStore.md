# SPEC-011 — Embeddings & Vector Store

- **State**: IMPLEMENTED + TESTED (2026-08-11) · **Status**: ACCEPTED
- **Layer**: Phase 1 — Knowledge · ADR-0004/0006

## Context / Problem
Hybrid retrieval needs vector similarity. The core must never couple to an embedding vendor
(spec §15–§17); local-first requires a zero-dependency path; unchanged content must never be
re-embedded (content_hash cache).

## Goals
- `EmbeddingProvider` protocol (embed_text / embed_batch / dimension / metadata).
- Local **deterministic** provider (`HashEmbeddingProvider`): character n-gram hashing + L2
  normalization — cheap, reproducible, obviously not "trained"; real providers plug in behind
  the same protocol.
- `VectorStore` protocol (upsert / delete / search / hybrid_search / filter) with a
  SQLite-backed implementation.
- Embedding cache keyed by `content_hash` (SPEC §17): no recomputation on unchanged content.

## Non-goals
- Trained/neural embeddings in bootstrap; approximate nearest neighbor (HNSW); GPU.

## Requirements
R11.1 HashEmbeddingProvider: `dimension` configurable (default 256), n-gram tokens
     (2,3)-grams + words; deterministic for equal input; L2-normalized; metadata() reports
     provider/model/dimension.
R11.2 SqliteVectorStore: upsert entries `{chunk_id, document_id, content_hash, content}` →
     computes embedding once (cache hit skips provider), stores vector JSON in `embeddings`.
R11.3 delete(ids), delete_by_document(document_id) (used on document re-ingest).
R11.4 search(vector, limit, filters): cosine similarity over candidates (SQL + Python scoring,
     honest about linear scan for bootstrap scale); filters: doc_type.
R11.5 hybrid_search delegates to SPEC-012 HybridRetriever.

## Interfaces
```
provider = HashEmbeddingProvider(dimension=256)
store = SqliteVectorStore(db, provider)
store.upsert([{"chunk_id": ..., "document_id": ..., "content_hash": ..., "content": ...}])
hits = store.search(provider.embed_text("consulta"), limit=5)
```

## Data model (migration V2)
`embeddings(id, workspace_id, content_hash, document_id, chunk_id UNIQUE, dimension,
vector JSON, provider, model, created_at)` + index on chunk_id/content_hash.

## Security
No secrets; vectors are content-derived only.

## Tests / Acceptance
`test_embeddings.py`: determinism, dimension, L2 norm; upsert→search finds similar chunk;
delete works; content_hash cache avoids duplicate provider calls (count rows); filter by
doc_type. Ingestion (`geos knowledge ingest`) creates embedding rows for new chunks.
