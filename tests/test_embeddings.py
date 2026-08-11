"""SPEC-011 embeddings + vector store tests."""

from __future__ import annotations

import json
import unittest
import urllib.error
from unittest import mock

from geos.intelligence.embeddings import (
    EmbeddingError,
    HashEmbeddingProvider,
    OpenAIEmbeddingProvider,
    SqliteVectorStore,
    cosine_similarity,
    provider_from_config,
)
from geos.storage.repos import KnowledgeRepository
from tests.helpers import temp_db


class FakeResponse:
    """Minimal file-like response for mocked urllib calls."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


def _seed_chunk(db, chunk_id: str, content: str, uri: str = "test://a.md",
                title: str = "a") -> str:
    repo = KnowledgeRepository(db)
    doc_id, _, _ = repo.upsert_document(
        uri=uri, title=title, doc_type="markdown", source="test",
        content_hash=f"hash-{chunk_id}", metadata={},
    )
    repo.add_chunks(doc_id, [{
        "chunk_id": chunk_id, "chunk_index": 0, "heading": None,
        "position": 0, "content": content, "metadata": {},
    }])
    return doc_id


class EmbeddingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()
        self.provider = HashEmbeddingProvider(dimension=128)

    def tearDown(self) -> None:
        self.db.close()

    def test_determinism_and_norm(self) -> None:
        a = self.provider.embed_text("origem de crédito bancário")
        b = self.provider.embed_text("origem de crédito bancário")
        self.assertEqual(a, b)
        self.assertEqual(len(a), 128)
        norm = sum(x * x for x in a) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_similar_texts_closer(self) -> None:
        base = self.provider.embed_text("conciliação de crédito bancário")
        similar = self.provider.embed_text("conciliação de crédito bancário e origem")
        different = self.provider.embed_text("receita de bolo de cenoura")
        self.assertGreater(cosine_similarity(base, similar), cosine_similarity(base, different))

    def test_metadata(self) -> None:
        meta = self.provider.metadata()
        self.assertEqual(meta["provider"], "geos.hash")
        self.assertEqual(meta["dimension"], 128)

    def test_vector_store_upsert_search_delete(self) -> None:
        doc_id = _seed_chunk(self.db, "c1", "origem de crédito bancário e conciliação")
        _seed_chunk(self.db, "c2", "receita de bolo de cenoura", uri="test://b.md", title="b")
        store = SqliteVectorStore(self.db, self.provider)
        store.upsert([
            {"chunk_id": "c1", "document_id": doc_id, "content_hash": "h1",
             "content": "origem de crédito bancário e conciliação"},
            {"chunk_id": "c2", "document_id": doc_id, "content_hash": "h2",
             "content": "receita de bolo de cenoura"},
        ])
        hits = store.search(self.provider.embed_text("conciliação de crédito"), limit=1)
        self.assertEqual(hits[0]["chunk_id"], "c1")
        rows = self.db.conn_checked.execute("SELECT COUNT(*) c FROM embeddings").fetchone()["c"]
        self.assertEqual(rows, 2)
        store.delete(["c2"])
        rows = self.db.conn_checked.execute("SELECT COUNT(*) c FROM embeddings").fetchone()["c"]
        self.assertEqual(rows, 1)

    def test_cache_skips_duplicate_embedding(self) -> None:
        doc_id = _seed_chunk(self.db, "c1", "texto idêntico de exemplo")
        _seed_chunk(self.db, "c2", "texto idêntico de exemplo", uri="test://b.md", title="b")
        store = SqliteVectorStore(self.db, self.provider)
        store.upsert([{"chunk_id": "c1", "document_id": doc_id, "content_hash": "same",
                       "content": "texto idêntico de exemplo"}])
        store.upsert([{"chunk_id": "c2", "document_id": doc_id, "content_hash": "same",
                       "content": "texto idêntico de exemplo"}])
        rows = self.db.conn_checked.execute("SELECT COUNT(*) c FROM embeddings").fetchone()["c"]
        self.assertEqual(rows, 2)  # two chunks, same vector via cache
        vectors = self.db.conn_checked.execute("SELECT DISTINCT vector FROM embeddings").fetchall()
        self.assertEqual(len(vectors), 1)

    def test_hybrid_search_protocol(self) -> None:
        doc_id = _seed_chunk(self.db, "c1", "origem de crédito para decisão financeira")
        store = SqliteVectorStore(self.db, self.provider)
        store.upsert([{"chunk_id": "c1", "document_id": doc_id, "content_hash": "h1",
                       "content": "origem de crédito para decisão financeira"}])
        hits = store.hybrid_search(
            "origem de crédito", self.provider.embed_text("origem de crédito"), limit=3
        )
        self.assertGreaterEqual(len(hits), 1)


class OpenAIEmbeddingTests(unittest.TestCase):
    """OpenAI-compatible provider behind the protocol (mock HTTP, no network)."""

    def _provider(self, dimension: int | None = 4, **kwargs) -> OpenAIEmbeddingProvider:
        return OpenAIEmbeddingProvider(api_key="test-key", model="mock-model",
                                       endpoint="https://example.test/v1/embeddings",
                                       dimension=dimension, timeout_s=5, **kwargs)

    def test_embed_batch_parses_response(self) -> None:
        payload = {"data": [{"embedding": [0.1, 0.2, 0.3, 0.4]},
                            {"embedding": [0.5, 0.6, 0.7, 0.8]}]}
        provider = self._provider()
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(payload)) as urlopen:
            vectors = provider.embed_batch(["a", "b"])
        self.assertEqual(len(vectors), 2)
        self.assertEqual(vectors[1][0], 0.5)
        self.assertEqual(provider.dimension(), 4)
        # request carries model + authorization
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        body = json.loads(request.data)
        self.assertEqual(body["model"], "mock-model")

    def test_requires_api_key(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(EmbeddingError):
                OpenAIEmbeddingProvider(api_key=None)

    def test_http_error_raises_embedding_error(self) -> None:
        provider = self._provider()
        error = urllib.error.HTTPError("https://example.test", 401, "unauthorized",
                                       {}, None)
        error.read = lambda: b'{"error": "invalid api key"}'  # type: ignore[method-assign]
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(EmbeddingError) as ctx:
                provider.embed_text("x")
        self.assertIn("401", str(ctx.exception))

    def test_count_mismatch_raises(self) -> None:
        payload = {"data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}]}  # 1 vector, 2 texts
        provider = self._provider()
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(payload)):
            with self.assertRaises(EmbeddingError):
                provider.embed_batch(["a", "b"])

    def test_provider_from_config(self) -> None:
        self.assertIsInstance(provider_from_config(None), HashEmbeddingProvider)
        self.assertIsInstance(provider_from_config({"embeddings": {}}), HashEmbeddingProvider)
        with mock.patch.dict("os.environ", {"GEOS_OPENAI_API_KEY": "env-key"}, clear=True):
            p = provider_from_config({"embeddings": {"provider": "openai",
                                                     "options": {"model": "m"}}})
        self.assertIsInstance(p, OpenAIEmbeddingProvider)
        self.assertEqual(p.metadata()["model"], "m")

    def test_provider_from_config_openai_without_key_raises(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(EmbeddingError):
                provider_from_config({"embeddings": {"provider": "openai"}})


if __name__ == "__main__":
    unittest.main()
