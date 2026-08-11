"""SPEC-010 knowledge tests: ingest, dedup, FTS search."""

from __future__ import annotations

import unittest

from geos.intelligence.knowledge import ingest_directory, search
from tests.helpers import TempDir, temp_db


class KnowledgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()

    def tearDown(self) -> None:
        self.db.close()

    def test_ingest_and_search(self) -> None:
        with TempDir() as tmp:
            (tmp / "docs").mkdir()
            (tmp / "docs" / "origin.md").write_text(
                "# Origem de crédito\n\nA origem de crédito bancário é a informação central do Zetra One.\n",
                encoding="utf-8",
            )
            result = ingest_directory(self.db, tmp / "docs", source="test")
            self.assertEqual(result.files_seen, 1)
            self.assertEqual(result.added, 1)
            self.assertGreater(result.chunks, 0)

            hits = search(self.db, "origem de crédito")
            self.assertGreaterEqual(len(hits), 1)
            self.assertIn("origin.md", hits[0]["uri"])
            self.assertIn("origem", hits[0]["snippet"].lower())
            self.assertIn("Zetra One", hits[0]["snippet"])

    def test_reingest_unchanged_is_noop(self) -> None:
        with TempDir() as tmp:
            (tmp / "docs").mkdir()
            path = tmp / "docs" / "a.md"
            path.write_text("# A\n\nConteúdo fixo aqui.\n", encoding="utf-8")
            first = ingest_directory(self.db, tmp / "docs", source="test")
            second = ingest_directory(self.db, tmp / "docs", source="test")
            self.assertEqual(second.unchanged, 1)
            self.assertEqual(second.added, 0)
            chunks = self.db.conn_checked.execute(
                "SELECT COUNT(*) c FROM document_chunks"
            ).fetchone()["c"]
            self.assertEqual(chunks, first.chunks)

    def test_changed_doc_replaces_chunks(self) -> None:
        with TempDir() as tmp:
            (tmp / "docs").mkdir()
            path = tmp / "docs" / "b.md"
            path.write_text("# B\n\nVersão um com palavras únicas.\n", encoding="utf-8")
            ingest_directory(self.db, tmp / "docs", source="test")
            path.write_text("# B\n\nVersão dois com termos totalmente diferentes.\n", encoding="utf-8")
            result = ingest_directory(self.db, tmp / "docs", source="test")
            self.assertEqual(result.updated, 1)
            hits_old = search(self.db, "palavras únicas")
            self.assertEqual(hits_old, [])
            hits_new = search(self.db, "termos totalmente diferentes")
            self.assertGreaterEqual(len(hits_new), 1)

    def test_empty_query_returns_nothing(self) -> None:
        with TempDir() as tmp:
            (tmp / "docs").mkdir()
            (tmp / "docs" / "x.md").write_text(
                "# X\n\nConteúdo para busca vazia.\n", encoding="utf-8"
            )
            ingest_directory(self.db, tmp / "docs", source="test")
            self.assertEqual(search(self.db, ""), [])
            self.assertEqual(search(self.db, "   "), [])

    def test_doc_type_filter(self) -> None:
        with TempDir() as tmp:
            (tmp / "docs").mkdir()
            (tmp / "docs" / "x.md").write_text("# X\n\nConteúdo único filter test.\n", encoding="utf-8")
            ingest_directory(self.db, tmp / "docs", source="test", doc_type="markdown")
            all_hits = search(self.db, "filter")
            md_hits = search(self.db, "filter", doc_type="markdown")
            other_hits = search(self.db, "filter", doc_type="nonexistent")
            self.assertEqual(len(all_hits), len(md_hits))
            self.assertEqual(other_hits, [])

    def test_node_edge_upsert(self) -> None:
        from geos.storage.repos import RepoFactory

        repo = RepoFactory(self.db).knowledge
        n1 = repo.upsert_node("COMPANY", "Azeetra", confidence=0.9, source="test")
        n2 = repo.upsert_node("PRODUCT", "Zetra One", confidence=0.9, source="test")
        repo.upsert_edge(n1, n2, "builds", weight=1.0, confidence=0.8, source="test")
        nodes = repo.list_nodes()
        self.assertEqual(len(nodes), 2)
        edges = repo.list_edges()
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["relationship"], "builds")

    def test_ingest_missing_dir_raises(self) -> None:
        with TempDir() as tmp:
            with self.assertRaises(ValueError):
                ingest_directory(self.db, tmp / "missing", source="test")


if __name__ == "__main__":
    unittest.main()
