"""SPEC-013 knowledge graph tests."""

from __future__ import annotations

import unittest

from geos.intelligence.graph import GraphService, RuleBasedExtractor
from geos.intelligence.knowledge import ingest_directory
from tests.helpers import TempDir, temp_db


class GraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()

    def tearDown(self) -> None:
        self.db.close()

    def test_extractor_known_entities(self) -> None:
        extractor = RuleBasedExtractor()
        entities = extractor.extract(
            "A origem de crédito bancário é o tema. Azeetra constrói o Zetra One para conciliação."
        )
        types = {t for t, _, _ in entities}
        names = {n.lower() for _, n, _ in entities}
        self.assertIn("TOPIC", types)
        self.assertIn("origem de crédito", names)
        self.assertIn("PRODUCT", types)
        self.assertIn("zetra one", names)

    def test_process_document_creates_edges(self) -> None:
        with TempDir() as tmp:
            (tmp / "docs").mkdir()
            (tmp / "docs" / "x.md").write_text(
                "# Origem de crédito\n\nA origem de crédito exige evidência. Azeetra e Zetra One "
                "endereçam a conciliação bancária.\n",
                encoding="utf-8",
            )
            ingest_directory(self.db, tmp / "docs", source="test")
            doc = self.db.conn_checked.execute(
                "SELECT * FROM documents LIMIT 1"
            ).fetchone()
            from geos.storage.repos import KnowledgeRepository

            chunks = KnowledgeRepository(self.db).chunks_for_document(doc["id"])
            extractor = RuleBasedExtractor()
            result = extractor.process_document(self.db, doc["id"], doc["uri"], doc["title"], chunks)
            self.assertGreater(result.nodes, 0)
            self.assertGreater(result.edges, 0)

        graph = GraphService(self.db)
        stats = graph.stats()
        self.assertGreater(stats["nodes"], 0)
        self.assertIn("CONTENT", stats["by_type"])

    def test_related_documents(self) -> None:
        with TempDir() as tmp:
            (tmp / "docs").mkdir()
            (tmp / "docs" / "x.md").write_text(
                "# Tema\n\nOrigem de crédito e conciliação bancária com evidência.\n",
                encoding="utf-8",
            )
            ingest_directory(self.db, tmp / "docs", source="test")
            doc = self.db.conn_checked.execute("SELECT * FROM documents LIMIT 1").fetchone()
            from geos.storage.repos import KnowledgeRepository

            chunks = KnowledgeRepository(self.db).chunks_for_document(doc["id"])
            RuleBasedExtractor().process_document(self.db, doc["id"], doc["uri"], doc["title"], chunks)

            graph = GraphService(self.db)
            uris = graph.related_documents(["origem de crédito"])
            self.assertGreaterEqual(len(uris), 1)
            self.assertIn("x.md", uris[0])

    def test_extraction_idempotent(self) -> None:
        with TempDir() as tmp:
            (tmp / "docs").mkdir()
            (tmp / "docs" / "x.md").write_text(
                "# T\n\nOrigem de crédito em conciliação.\n", encoding="utf-8"
            )
            ingest_directory(self.db, tmp / "docs", source="test")
            doc = self.db.conn_checked.execute("SELECT * FROM documents LIMIT 1").fetchone()
            from geos.storage.repos import KnowledgeRepository

            chunks = KnowledgeRepository(self.db).chunks_for_document(doc["id"])
            RuleBasedExtractor().process_document(self.db, doc["id"], doc["uri"], doc["title"], chunks)
            RuleBasedExtractor().process_document(self.db, doc["id"], doc["uri"], doc["title"], chunks)
        stats = GraphService(self.db).stats()
        nodes = self.db.conn_checked.execute(
            "SELECT name, COUNT(*) c FROM knowledge_nodes GROUP BY name HAVING c > 1"
        ).fetchall()
        self.assertEqual(nodes, [])


if __name__ == "__main__":
    unittest.main()
