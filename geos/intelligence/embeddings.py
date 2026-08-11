"""Embedding & vector protocols (SPEC-011, ADR-0006). Interfaces only in bootstrap.

Core never couples to a vendor: providers plug in via these protocols.
"""

from __future__ import annotations

from typing import Any, Protocol, Sequence


class EmbeddingProvider(Protocol):
    """embed_text / embed_batch / dimension / metadata (spec §16)."""

    def embed_text(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]: ...
    def dimension(self) -> int: ...
    def metadata(self) -> dict[str, Any]: ...


class VectorStore(Protocol):
    """upsert / delete / search / hybrid_search / filter (spec §15)."""

    def upsert(self, vectors: list[dict[str, Any]]) -> None: ...
    def delete(self, ids: list[str]) -> None: ...
    def search(self, vector: list[float], limit: int = 10, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...
    def hybrid_search(self, query: str, vector: list[float], limit: int = 10,
                      filters: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...


class EmbeddingCache(Protocol):
    """Content-hash keyed cache — never re-embed unchanged content (spec §17)."""

    def get(self, content_hash: str) -> list[float] | None: ...
    def set(self, content_hash: str, vector: list[float]) -> None: ...
