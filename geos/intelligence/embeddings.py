"""Embedding & vector protocols (SPEC-011, ADR-0006) + local deterministic implementations.

HashEmbeddingProvider: character n-gram hashing, L2-normalized, fully deterministic —
cheap and reproducible for local retrieval experiments. Real providers (OpenAI,
sentence-transformers, …) plug in behind the same protocol. Content-hash cache
(SPEC §17) lives in SqliteVectorStore.upsert.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Protocol, Sequence

from ..storage.database import Database
from ..storage.repos import EmbeddingRepository

_WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


class EmbeddingProvider(Protocol):
    def embed_text(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]: ...
    def dimension(self) -> int: ...
    def metadata(self) -> dict[str, Any]: ...


class VectorStore(Protocol):
    def upsert(self, vectors: list[dict[str, Any]]) -> None: ...
    def delete(self, ids: list[str]) -> None: ...
    def search(self, vector: list[float], limit: int = 10, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...
    def hybrid_search(self, query: str, vector: list[float], limit: int = 10,
                      filters: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...


class HashEmbeddingProvider:
    """Deterministic local embeddings via hashed character n-grams (ADR-0004)."""

    def __init__(self, dimension: int = 256, ngrams: tuple[int, ...] = (2, 3),
                 seed: int = 0) -> None:
        if dimension < 16:
            raise ValueError("dimension must be >= 16")
        self._dimension = dimension
        self._ngrams = ngrams
        self._seed = seed

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        lowered = text.lower()
        words = _WORD_RE.findall(lowered)
        if not words:
            return vector
        for word in words:
            vector[self._hash(word) % self._dimension] += 1.0
            for n in self._ngrams:
                if len(word) < n:
                    continue
                for i in range(len(word) - n + 1):
                    vector[self._hash(word[i : i + n]) % self._dimension] += 1.0
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]

    def dimension(self) -> int:
        return self._dimension

    def metadata(self) -> dict[str, Any]:
        return {"provider": "geos.hash", "model": "n-gram", "dimension": self._dimension,
                "ngrams": list(self._ngrams)}

    def _hash(self, token: str) -> int:
        return int(hashlib.md5(f"{self._seed}:{token}".encode("utf-8")).hexdigest()[:8], 16)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class SqliteVectorStore:
    """SQLite-backed vector store: JSON vectors + Python cosine scoring (bootstrap scale)."""

    _CACHE_MAX = 10_000  # content-hash cache bound (bootstrap: keeps memory in check)

    def __init__(self, db: Database, provider: EmbeddingProvider) -> None:
        self._db = db
        self._provider = provider
        self._repo = EmbeddingRepository(db)
        self._cache: dict[str, list[float]] = {}

    @property
    def provider(self) -> EmbeddingProvider:
        return self._provider

    def upsert(self, vectors: list[dict[str, Any]]) -> int:
        """vectors: [{chunk_id, document_id, content_hash, content}]. Cache by hash."""
        inserted = 0
        for entry in vectors:
            content_hash = entry.get("content_hash", "")
            if not content_hash:
                content_hash = hashlib.sha256(
                    str(entry.get("content", "")).encode("utf-8")
                ).hexdigest()
            cached = self._cache.get(content_hash)
            if cached is None:
                existing = self._repo.by_content_hash(content_hash)
                if existing:
                    cached = _parse_vector(existing[0].get("vector", ""))
                if cached is None:
                    cached = self._provider.embed_text(str(entry.get("content", "")))
                    if len(self._cache) >= self._CACHE_MAX:
                        self._cache.clear()
                    self._cache[content_hash] = cached
            self._repo.upsert(
                chunk_id=str(entry["chunk_id"]), document_id=str(entry["document_id"]),
                content_hash=content_hash, vector=cached,
                provider=self._provider.metadata()["provider"],
                model=self._provider.metadata().get("model"),
            )
            inserted += 1
        return inserted

    def delete(self, chunk_ids: list[str]) -> int:
        return self._repo.delete_by_chunk_ids(chunk_ids)

    def delete_by_document(self, document_id: str) -> int:
        return self._repo.delete_by_document(document_id)

    def search(self, vector: list[float], limit: int = 10,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        doc_type = (filters or {}).get("doc_type")
        candidates = self._repo.candidates(doc_type=doc_type)
        scored = []
        for item in candidates:
            score = cosine_similarity(vector, item.get("vector") or [])
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], pair[1].get("chunk_id", "")))
        hits = []
        for score, item in scored[:limit]:
            hit = {
                "score": round(score, 4), "chunk_id": item["chunk_id"],
                "content": item.get("content", ""), "heading": item.get("heading"),
                "uri": item.get("uri"), "title": item.get("title"),
                "doc_type": item.get("doc_type"),
            }
            hits.append(hit)
        return hits

    def hybrid_search(self, query: str, vector: list[float], limit: int = 10,
                      filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        from .retrieval import HybridRetriever, RetrievalConfig

        retriever = HybridRetriever(self._db, config=RetrievalConfig(limit=limit),
                                    vector_store=self)
        return [h.to_dict() for h in retriever.search(query, limit=limit,
                                                      doc_type=(filters or {}).get("doc_type"))]


def _parse_vector(raw: Any) -> list[float] | None:
    import json

    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return [float(x) for x in parsed] if isinstance(parsed, list) else None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
