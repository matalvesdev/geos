"""Knowledge ingestion + FTS search (SPEC-010). Markdown/plain text, hash dedup, provenance."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..storage.database import Database
from ..storage.repos import KnowledgeRepository
from ..util import new_id
from .chunking import chunk_markdown
from .embeddings import EmbeddingProvider, HashEmbeddingProvider, SqliteVectorStore


@dataclass
class IngestResult:
    files_seen: int = 0
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    chunks: int = 0
    embeddings: int = 0
    errors: list[str] = field(default_factory=list)


def ingest_directory(
    db: Database,
    root: str | Path,
    source: str | None = None,
    recursive: bool = True,
    doc_type: str = "markdown",
    embed: bool = True,
    provider: EmbeddingProvider | None = None,
) -> IngestResult:
    """Ingest *.md / *.txt files under root. Deterministic hash dedup per URI.
    When embed=True (default), chunk embeddings are computed once per content_hash
    and stored in the SQLite vector store (SPEC-011/§17 cache).
    `provider` defaults to the local deterministic HashEmbeddingProvider; real
    providers (OpenAI-compatible) plug in behind the same protocol.
    """
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f"ingest root is not a directory: {root}")
    repo = KnowledgeRepository(db)
    vector_store = SqliteVectorStore(db, provider or HashEmbeddingProvider()) if embed else None
    result = IngestResult()
    pattern = "**/*" if recursive else "*"
    files = sorted(
        p for p in root.glob(pattern)
        if p.is_file() and p.suffix.lower() in (".md", ".markdown", ".txt")
        and not any(part.startswith(".") for part in p.parts)
    )
    for path in files:
        result.files_seen += 1
        try:
            rel = path.relative_to(root).as_posix()
            uri = f"{source or 'file'}://{rel}"
            text = path.read_text(encoding="utf-8", errors="replace")
            content_hash = _sha256(text)
            doc_id, changed, created = repo.upsert_document(
                uri=uri, title=path.stem, doc_type=doc_type, source=source or "file",
                content_hash=content_hash, metadata={"relative_path": rel},
            )
            if not changed:
                result.unchanged += 1
                continue
            chunks = chunk_markdown(text, uri=uri)
            for chunk in chunks:
                chunk.chunk_id = new_id()
            repo.add_chunks(doc_id, [_chunk_row(c) for c in chunks])
            result.chunks += len(chunks)
            if vector_store is not None:
                if not created:
                    vector_store.delete_by_document(doc_id)  # purge stale vectors
                result.embeddings += vector_store.upsert(
                    [
                        {"chunk_id": c.chunk_id, "document_id": doc_id,
                         "content_hash": _sha256(c.content), "content": c.content}
                        for c in chunks
                    ]
                )
            if created:
                result.added += 1
            else:
                result.updated += 1
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the ingest
            result.errors.append(f"{path}: {type(exc).__name__}: {exc}")
    return result


def reindex_embeddings(db: Database, provider: EmbeddingProvider | None = None) -> int:
    """Rebuild embeddings for all ingested documents (SPEC-011). Idempotent."""
    repo = KnowledgeRepository(db)
    store = SqliteVectorStore(db, provider or HashEmbeddingProvider())
    total = 0
    for doc in repo.list_documents():
        store.delete_by_document(doc["id"])
        chunks = repo.chunks_for_document(doc["id"])
        total += store.upsert(
            [
                {"chunk_id": c["chunk_id"], "document_id": doc["id"],
                 "content_hash": _sha256(c["content"]), "content": c["content"]}
                for c in chunks
            ]
        )
    return total


def search(
    db: Database,
    query: str,
    limit: int = 10,
    doc_type: str | None = None,
) -> list[dict[str, Any]]:
    if not query or not query.strip():
        return []
    return KnowledgeRepository(db).search(query, limit=limit, doc_type=doc_type)


def _chunk_row(chunk: Any) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "chunk_index": chunk.chunk_index,
        "heading": chunk.heading,
        "position": chunk.position,
        "content": chunk.content,
        "metadata": chunk.metadata or {},
    }


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
