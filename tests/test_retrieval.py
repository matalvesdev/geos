"""SPEC-012 hybrid retrieval tests."""

from __future__ import annotations

import unittest

from geos.intelligence.knowledge import ingest_directory
from geos.intelligence.retrieval import HybridRetriever, RetrievalConfig
from tests.helpers import TempDir, temp_db


class RetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()

    def tearDown(self) -> None:
        self.db.close()

    def _ingest_fixture(self) -> None:
        with TempDir() as tmp:
            (tmp / "docs").mkdir()
            (tmp / "docs" / "origem.md").write_text(
                "# Origem de crédito\n\nA origem de crédito bancário é essencial para a decisão financeira.\n"
                "Conciliação com evidência documental é o processo central.\n",
                encoding="utf-8",
            )
            (tmp / "docs" / "cake.md").write_text(
                "# Bolo\n\nReceita de bolo de cenoura com chocolate.\n",
                encoding="utf-8",
            )
            ingest_directory(self.db, tmp / "docs", source="test")

    def test_hybrid_finds_relevant(self) -> None:
        self._ingest_fixture()
        retriever = HybridRetriever(self.db, config=RetrievalConfig(limit=5))
        hits = retriever.search("origem de crédito bancário")
        self.assertGreaterEqual(len(hits), 1)
        top = hits[0]
        self.assertIn("origem.md", top.uri)
        self.assertIn("fts", top.provenance)
        self.assertGreater(top.score, 0)

    def test_weights_change_ordering(self) -> None:
        self._ingest_fixture()
        fts_heavy = HybridRetriever(self.db, config=RetrievalConfig(
            fts_weight=1.0, vector_weight=0.0, graph_weight=0.0, limit=5)).search("origem de crédito")
        self.assertTrue(any("fts" in h.provenance for h in fts_heavy))

    def test_build_context_citations(self) -> None:
        self._ingest_fixture()
        retriever = HybridRetriever(self.db, config=RetrievalConfig(limit=3))
        hits = retriever.search("origem de crédito")
        ctx = retriever.build_context("origem de crédito", hits)
        self.assertGreaterEqual(len(ctx.citations), 1)
        self.assertIn("uri", ctx.citations[0])
        self.assertGreater(ctx.tokens_estimate, 0)

    def test_empty_vector_corpus_does_not_crash(self) -> None:
        with TempDir() as tmp:
            (tmp / "docs").mkdir()
            (tmp / "docs" / "a.md").write_text("# A\n\nConteúdo sem vetores ainda.\n", encoding="utf-8")
            ingest_directory(self.db, tmp / "docs", source="test", embed=False)
        retriever = HybridRetriever(self.db)
        hits = retriever.search("qualquer coisa")
        self.assertIsInstance(hits, list)

    def test_doc_type_filter(self) -> None:
        self._ingest_fixture()
        retriever = HybridRetriever(self.db, config=RetrievalConfig(limit=5))
        hits = retriever.search("origem de crédito", doc_type="markdown")
        self.assertGreaterEqual(len(hits), 1)

    def test_fts_rank_direction_more_negative_is_better(self) -> None:
        """Regression: FTS5 bm25() ranks are negative (more negative = stronger match).
        Normalization must not use abs() (which would invert the ranking)."""
        self._ingest_fixture()
        retriever = HybridRetriever(
            self.db, config=RetrievalConfig(fts_weight=1.0, vector_weight=0.0,
                                            graph_weight=0.0, limit=5),
        )

        # Fake FTS results in FTS5 semantics: strong match rank=-10, weak match rank=-2.
        def fake_search(query, limit=10, doc_type=None):
            return [
                {"chunk_id": "strong", "uri": "file://strong.md", "title": "Strong",
                 "heading": None, "snippet": "match forte", "rank": -10.0},
                {"chunk_id": "weak", "uri": "file://weak.md", "title": "Weak",
                 "heading": None, "snippet": "match fraco", "rank": -2.0},
            ]

        retriever._knowledge.search = fake_search  # type: ignore[method-assign]
        hits = retriever.search("origem de crédito")
        # Corpus vector hits (score 0.0 with vector_weight=0) sort below the fake
        # FTS hits; the ordering of the two FTS hits is what the regression checks.
        by_chunk = {h.chunk_id: h for h in hits}
        self.assertIn("strong", by_chunk)
        self.assertIn("weak", by_chunk)
        self.assertGreater(by_chunk["strong"].score, by_chunk["weak"].score,
                           "stronger (more negative) bm25 rank must score higher")
        self.assertEqual(hits[0].chunk_id, "strong")

    def test_vector_store_exposes_provider(self) -> None:
        from geos.intelligence.embeddings import HashEmbeddingProvider, SqliteVectorStore

        store = SqliteVectorStore(self.db, HashEmbeddingProvider())
        self.assertIsNotNone(store.provider)
        self.assertEqual(store.provider.dimension(), 256)


if __name__ == "__main__":
    unittest.main()
