"""Embedding & vector protocols (SPEC-011, ADR-0006) + local deterministic implementations.

HashEmbeddingProvider: character n-gram hashing, L2-normalized, fully deterministic —
cheap and reproducible for local retrieval experiments. Real providers (OpenAI,
sentence-transformers, …) plug in behind the same protocol. Content-hash cache
(SPEC §17) lives in SqliteVectorStore.upsert.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.request
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


class EmbeddingError(Exception):
    """Raised when an embedding provider fails (network, auth, malformed response)."""


class OpenAIEmbeddingProvider:
    """OpenAI-compatible embeddings behind the EmbeddingProvider protocol (SPEC-011).

    stdlib `urllib` only — no SDK dependency. The endpoint is configurable, so any
    OpenAI-compatible API works (OpenAI, Azure OpenAI, local vLLM/Ollama, ...).
    API key comes from the constructor or the GEOS_OPENAI_API_KEY / OPENAI_API_KEY
    env vars. Deterministic metadata (provider/model/dimension) is recorded per
    embedding row so retrieval provenance stays intact.
    """

    def __init__(self, api_key: str | None = None, model: str = "text-embedding-3-small",
                 endpoint: str = "https://api.openai.com/v1/embeddings",
                 dimension: int | None = None, timeout_s: int = 30) -> None:
        self._api_key = (api_key or os.environ.get("GEOS_OPENAI_API_KEY")
                         or os.environ.get("OPENAI_API_KEY"))
        if not self._api_key:
            raise EmbeddingError(
                "OpenAIEmbeddingProvider requires an API key "
                "(constructor or GEOS_OPENAI_API_KEY/OPENAI_API_KEY env vars)"
            )
        self._model = model
        self._endpoint = endpoint
        self._dimension = dimension
        self._timeout_s = timeout_s
        self._observed_dimension = dimension

    def embed_text(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        body: dict[str, Any] = {"model": self._model, "input": [str(t) for t in texts]}
        if self._dimension:
            body["dimensions"] = self._dimension
        request = urllib.request.Request(
            self._endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self._api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
            raise EmbeddingError(f"embedding HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # URLError does not cover socket.timeout / http.client.IncompleteRead /
            # ConnectionResetError (OSError subclasses) — all become typed errors.
            reason = getattr(exc, "reason", exc)
            raise EmbeddingError(f"embedding network error: {reason}") from exc
        except json.JSONDecodeError as exc:
            raise EmbeddingError(f"embedding response is not valid JSON: {exc}") from exc
        vectors: list[list[float]] = []
        for item in payload.get("data") or []:
            vector = [float(x) for x in (item.get("embedding") or [])]
            if not vector:
                raise EmbeddingError("embedding response item missing vector")
            vectors.append(vector)
            if self._observed_dimension is None:
                self._observed_dimension = len(vector)
        if len(vectors) != len(texts):
            raise EmbeddingError(
                f"embedding response mismatch: got {len(vectors)} vectors for {len(texts)} texts"
            )
        return vectors

    def dimension(self) -> int:
        return self._observed_dimension or self._dimension or 1536

    def metadata(self) -> dict[str, Any]:
        return {"provider": "openai", "model": self._model,
                "dimension": self.dimension(), "endpoint": self._endpoint}


def provider_from_config(knowledge_cfg: dict[str, Any] | None) -> EmbeddingProvider:
    """Build the embedding provider from the `knowledge.embeddings` config section.

    provider: "hash" (default, deterministic local) | "openai" (OpenAI-compatible
    API; key via env GEOS_OPENAI_API_KEY/OPENAI_API_KEY). Options pass through to the
    provider constructor.
    """
    cfg = dict((knowledge_cfg or {}).get("embeddings") or {})
    kind = str(cfg.get("provider", "hash")).lower()
    options = dict(cfg.get("options") or {})
    if kind == "openai":
        return OpenAIEmbeddingProvider(**options)
    return HashEmbeddingProvider()


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
