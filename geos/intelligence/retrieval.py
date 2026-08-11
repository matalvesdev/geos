"""Hybrid retrieval (SPEC-012): FTS + vector + graph boost, configurable weights, rerank,
context with citations. Deterministic and dependency-free."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..storage.database import Database
from ..storage.repos import KnowledgeRepository
from .embeddings import EmbeddingProvider, HashEmbeddingProvider, SqliteVectorStore

_TOKEN_PER_CHAR = 0.25  # rough tokens estimate


@dataclass
class RetrievalConfig:
    fts_weight: float = 0.4
    vector_weight: float = 0.4
    graph_weight: float = 0.2
    limit: int = 10
    doc_type: str | None = None


@dataclass
class RetrievalHit:
    chunk_id: str
    document_id: str
    uri: str
    title: str
    heading: str | None
    snippet: str
    score: float
    provenance: list[str] = field(default_factory=list)
    fts_rank: float | None = None
    vector_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id, "document_id": self.document_id, "uri": self.uri,
            "title": self.title, "heading": self.heading, "snippet": self.snippet,
            "score": round(self.score, 4), "provenance": self.provenance,
        }


@dataclass
class ContextBundle:
    query: str
    hits: list[RetrievalHit]
    citations: list[dict[str, str]]
    tokens_estimate: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "hits": [h.to_dict() for h in self.hits],
            "citations": self.citations,
            "tokens_estimate": self.tokens_estimate,
        }


class HybridRetriever:
    def __init__(self, db: Database, config: RetrievalConfig | None = None,
                 vector_store: SqliteVectorStore | None = None,
                 embedding_provider: EmbeddingProvider | None = None) -> None:
        self._db = db
        self._config = config or RetrievalConfig()
        self._knowledge = KnowledgeRepository(db)
        self._vector_store = vector_store
        if vector_store is None and embedding_provider is None:
            provider = HashEmbeddingProvider()
            self._vector_store = SqliteVectorStore(db, provider)
            self._embedding_provider = provider
        else:
            self._vector_store = vector_store
            self._embedding_provider = embedding_provider or vector_store.provider

    def search(self, query: str, limit: int | None = None, doc_type: str | None = None) -> list[RetrievalHit]:
        limit = limit or self._config.limit
        doc_type = doc_type or self._config.doc_type
        fts = self._knowledge.search(query, limit=limit * 4, doc_type=doc_type)
        vector_hits: list[dict[str, Any]] = []
        try:
            vector = self._embedding_provider.embed_text(query)
            vector_hits = self._vector_store.search(vector, limit=limit * 4,
                                                    filters={"doc_type": doc_type})
        except Exception:  # noqa: BLE001 - vector signal is optional
            vector_hits = []

        merged: dict[str, RetrievalHit] = {}
        if fts:
            # FTS5 bm25() returns negative ranks (more negative = better match).
            # Normalize monotonically in -rank so stronger matches score higher:
            # norm = -rank / max(-rank), i.e. 1.0 for the strongest hit (SPEC-012).
            ranks = sorted(-float(h["rank"]) for h in fts)
            norm_max = max(ranks) or 1.0
            for item in fts:
                norm = (-float(item["rank"])) / norm_max
                hit = RetrievalHit(
                    chunk_id=item["chunk_id"], document_id="", uri=item["uri"],
                    title=item["title"], heading=item.get("heading"),
                    snippet=item["snippet"], score=self._config.fts_weight * norm,
                    provenance=["fts"], fts_rank=float(item["rank"]),
                )
                merged[hit.chunk_id] = hit
        for item in vector_hits:
            chunk_id = item["chunk_id"]
            existing = merged.get(chunk_id)
            if existing is None:
                existing = RetrievalHit(
                    chunk_id=chunk_id, document_id="", uri=item.get("uri", ""),
                    title=item.get("title", ""), heading=item.get("heading"),
                    snippet=item.get("content", "")[:220],
                    score=self._config.vector_weight * float(item.get("score", 0.0)),
                    provenance=["vector"], vector_score=float(item.get("score", 0.0)),
                )
                merged[chunk_id] = existing
            else:
                existing.score += self._config.vector_weight * float(item.get("score", 0.0))
                existing.vector_score = float(item.get("score", 0.0))
                existing.provenance.append("vector")
        # document_id enrichment
        doc_ids = self._knowledge.doc_ids_for_chunks(list(merged.keys()))
        for hit in merged.values():
            hit.document_id = doc_ids.get(hit.chunk_id, "")

        topics = self._match_topics(query)
        if topics and self._config.graph_weight:
            self._apply_graph_boost(merged, topics)

        hits = sorted(merged.values(), key=lambda h: (-h.score, h.chunk_id))
        return hits[:limit]

    def build_context(self, query: str, hits: list[RetrievalHit]) -> ContextBundle:
        citations: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        chars = 0
        for hit in hits:
            key = (hit.uri, hit.chunk_id)
            if key in seen:
                continue
            seen.add(key)
            citations.append(
                {"uri": hit.uri, "chunk_id": hit.chunk_id, "title": hit.title,
                 "heading": hit.heading or "", "score": f"{hit.score:.3f}"}
            )
            chars += len(hit.snippet)
        return ContextBundle(
            query=query, hits=hits, citations=citations,
            tokens_estimate=max(1, int(chars * _TOKEN_PER_CHAR)),
        )

    def _apply_graph_boost(self, merged: dict[str, RetrievalHit], topics: list[str]) -> None:
        from .graph import GraphService

        graph = GraphService(self._db)
        related = set(graph.related_documents(topics))
        for hit in merged.values():
            if hit.uri in related:
                hit.score += self._config.graph_weight
                hit.provenance.append("graph")

    def _match_topics(self, query: str) -> list[str]:
        from .graph import GraphService

        graph = GraphService(self._db)
        query_lower = query.lower()
        topics = []
        for node in graph.nodes_by_type("TOPIC"):
            name = str(node.get("name") or "")
            if name and name.lower() in query_lower:
                topics.append(name)
        return topics[:5]


def tokens_estimate(text: str) -> int:
    return max(1, int(len(text) * _TOKEN_PER_CHAR))
