"""SPEC-021 research engine tests."""

from __future__ import annotations

import unittest

from geos.domains.research import ResearchEngine
from geos.intelligence.knowledge import ingest_directory
from tests.helpers import TempDir, temp_db


class ResearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()

    def tearDown(self) -> None:
        self.db.close()

    def _ingest(self) -> None:
        with TempDir() as tmp:
            (tmp / "docs").mkdir()
            (tmp / "docs" / "origem.md").write_text(
                "# Origem de crédito\n\nA origem de crédito bancário exige evidência documental "
                "para a decisão financeira.\n",
                encoding="utf-8",
            )
            ingest_directory(self.db, tmp / "docs", source="test")

    def test_report_structure_with_sources(self) -> None:
        self._ingest()
        engine = ResearchEngine(self.db)
        report = engine.run("origem de crédito bancário")
        self.assertTrue(report.mock)
        self.assertFalse(report.empty)
        self.assertGreaterEqual(len(report.sources), 1)
        self.assertIn("origem.md", report.sources[0].uri)
        self.assertIn("mock", report.synthesis)
        self.assertTrue(any(i["type"] == "OBSERVATION" for i in report.insights))

    def test_persisted_and_events(self) -> None:
        self._ingest()
        report = ResearchEngine(self.db).run("origem de crédito")
        rows = self.db.conn_checked.execute(
            "SELECT COUNT(*) c FROM research WHERE id = ?", (report.id,)
        ).fetchone()["c"]
        self.assertEqual(rows, 1)
        insights = self.db.conn_checked.execute(
            "SELECT COUNT(*) c FROM insights WHERE research_id = ?", (report.id,)
        ).fetchone()["c"]
        self.assertGreaterEqual(insights, 1)
        insight_nodes = self.db.conn_checked.execute(
            "SELECT COUNT(*) c FROM knowledge_nodes WHERE node_type = 'INSIGHT'"
        ).fetchone()["c"]
        self.assertGreaterEqual(insight_nodes, 1)
        events = self.db.conn_checked.execute(
            "SELECT COUNT(*) c FROM events WHERE event_type = 'research.completed'"
        ).fetchone()["c"]
        self.assertGreaterEqual(events, 1)

    def test_empty_corpus_never_invents(self) -> None:
        engine = ResearchEngine(self.db)
        report = engine.run("assunto totalmente desconhecido xyz123")
        self.assertTrue(report.empty)
        self.assertEqual(report.sources, [])
        self.assertIn("nenhuma fonte foi inventada", report.synthesis)

    def test_question_required(self) -> None:
        with self.assertRaises(ValueError):
            ResearchEngine(self.db).run("   ")

    def test_get_and_list(self) -> None:
        self._ingest()
        engine = ResearchEngine(self.db)
        report = engine.run("origem de crédito")
        fetched = engine.get(report.id)
        self.assertEqual(fetched["question"], "origem de crédito")
        self.assertGreaterEqual(len(engine.list()), 1)


if __name__ == "__main__":
    unittest.main()
