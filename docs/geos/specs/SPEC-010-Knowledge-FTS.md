# SPEC-010 — Knowledge: Documents, Chunking, FTS

- **State**: IMPLEMENTED + TESTED (2026-08-11) · **Status**: ACCEPTED
- **Layer**: Knowledge foundation · ADR-0006

## Context / Problem
Zetra's knowledge lives in Markdown docs and the Company Library. GEOS must ingest documents into
a queryable layer (documents → chunks → FTS) with provenance and dedup, laying the base for
hybrid RAG (SPEC-011/012).

## Goals
- Ingest Markdown (and plain text) from a directory tree with deterministic content-hash dedup.
- Chunking by headings/paragraphs with position and heading metadata.
- FTS5 search over chunks with BM25 ordering, snippets and filters.
- Provenance: document source/URI retained on every chunk.

## Non-goals
- Embeddings (SPEC-011); reranking; graph extraction (SPEC-013); binary formats (PDF etc. later).

## Requirements
R10.1 `chunk_markdown(text, uri, max_chars, overlap)` → chunks at heading/paragraph boundaries
     with `heading`, `position`, `index`; token-fallback split at `max_chars`.
R10.2 `ingest_directory(db, path, recursive, source)` → upsert documents by URI; skip unchanged
     (content_hash); insert new chunks; delete chunks for changed docs; return counts.
R10.3 `search(db, query, limit, doc_type=None)` → FTS over `document_chunks_fts` with snippet,
     ordered by rank, returning document title/uri.
R10.4 `KnowledgeRepository` wraps ingest/search (SPEC-003).

## Interfaces
```
result = ingest_directory(db, "zetra-one/docs", source="zetra-one")
hits = search(db, "origem de crédito", limit=5)
```

## Security
FTS queries are parameterized (never interpolated); path traversal guarded (files must resolve
inside the requested root).

## Failure modes
Unparseable file → recorded in per-run summary, ingest continues; FTS corrupt → rebuildable via
re-ingest.

## Tests / Acceptance
`test_chunking.py`: heading/paragraph boundaries; max_chars fallback; metadata. `test_knowledge.py`:
ingest → search finds terms; re-ingest no-op on unchanged; changed doc replaces chunks; snippet
contains match; doc_type filter.
