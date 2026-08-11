"""SPEC-023 SEO engine tests."""

from __future__ import annotations

import unittest

from geos.domains.content import ContentEngine
from geos.domains.seo import SeoEngine
from geos.intelligence.knowledge import ingest_directory
from tests.helpers import TempDir, temp_db


class SeoDocAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()
        self.engine = SeoEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def _ingest(self, tmp, files: dict[str, str]) -> None:
        (tmp / "docs").mkdir(parents=True, exist_ok=True)
        for rel, content in files.items():
            (tmp / "docs" / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp / "docs" / rel).write_text(content, encoding="utf-8")
        ingest_directory(self.db, tmp / "docs", source="site")

    def test_broken_link_detected(self) -> None:
        with TempDir() as tmp:
            self._ingest(tmp, {
                "a.md": "# A\n\nVeja [b](b.md) e [x](nao-existe.md).\n",
                "b.md": "# B\n",
            })
        issues = self.engine.audit_docs()
        broken = [i for i in issues if i.category == "broken_link"]
        self.assertEqual(len(broken), 1)
        self.assertIn("nao-existe.md", broken[0].title)
        self.assertEqual(broken[0].severity, "critical")

    def test_resolves_relative_directories(self) -> None:
        with TempDir() as tmp:
            self._ingest(tmp, {
                "guide/a.md": "# A\n\nVeja [b](../b.md) e [c](sub/c.md).\n",
                "b.md": "# B\n",
                "guide/sub/c.md": "# C\n",
            })
        issues = self.engine.audit_docs()
        self.assertEqual([i for i in issues if i.category == "broken_link"], [])

    def test_orphan_detected_but_referenced_doc_is_not(self) -> None:
        with TempDir() as tmp:
            self._ingest(tmp, {
                "a.md": "# A\n\nVeja [b](b.md).\n",
                "b.md": "# B\n",
            })
        issues = self.engine.audit_docs()
        orphans = [i for i in issues if i.category == "orphan"]
        self.assertEqual(len(orphans), 1)
        self.assertIn("a.md", orphans[0].target or "")

    def test_thin_and_metadata(self) -> None:
        with TempDir() as tmp:
            long_text = "Texto sem heading inicial, mas suficientemente longo " * 30
            self._ingest(tmp, {
                "thin.md": "# Título\n\napenas uma frase curta.\n",
                "noheading.md": long_text,
            })
        issues = self.engine.audit_docs()
        thin = [i for i in issues if i.category == "thin_content"]
        metadata = [i for i in issues if i.category == "metadata"]
        self.assertEqual(len(thin), 1)
        self.assertIn("thin.md", thin[0].target or "")
        self.assertGreaterEqual(len(metadata), 1)

    def test_audit_persists_snapshot(self) -> None:
        with TempDir() as tmp:
            self._ingest(tmp, {"a.md": "# A\n\nVeja [x](nao-existe.md).\n"})
        result = self.engine.run_audit(scopes=("docs",))
        self.assertEqual(result["summary"]["critical"], 1)
        rows = self.db.conn_checked.execute(
            "SELECT COUNT(*) c FROM seo_audits"
        ).fetchone()["c"]
        self.assertEqual(rows, 1)
        issue_rows = self.db.conn_checked.execute(
            "SELECT COUNT(*) c FROM seo_issues"
        ).fetchone()["c"]
        self.assertEqual(issue_rows, result["summary"]["total"])

    def test_links_in_code_fences_ignored(self) -> None:
        """Regression: example links inside ``` fences must not be flagged broken."""
        with TempDir() as tmp:
            self._ingest(tmp, {
                "a.md": "# A\n\n```markdown\nVeja [x](nao-existe.md) num exemplo.\n```\n",
            })
        issues = self.engine.audit_docs()
        self.assertEqual([i for i in issues if i.category == "broken_link"], [])

    def test_self_link_does_not_count_as_reference(self) -> None:
        with TempDir() as tmp:
            self._ingest(tmp, {
                "a.md": "# A\n\n[voltar](a.md)\n",
            })
        issues = self.engine.audit_docs()
        orphans = [i for i in issues if i.category == "orphan"]
        self.assertEqual(len(orphans), 1)
        self.assertIn("a.md", orphans[0].target or "")


class SeoContentAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()
        self.engine = SeoEngine(self.db)
        self.content = ContentEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def _seed_graph_topic(self, name: str) -> None:
        from geos.storage.repos import RepoFactory

        RepoFactory(self.db).knowledge.upsert_node(
            "TOPIC", name, canonical_name=name, source="test",
        )

    def test_content_gap_from_graph_topic(self) -> None:
        self._seed_graph_topic("conciliação bancária")
        self.content.create_idea("origem de crédito")
        issues = self.engine.audit_content()
        gaps = [i for i in issues if i.category == "content_gap"]
        self.assertEqual(len(gaps), 1)
        self.assertIn("conciliação bancária", gaps[0].target or "")
        self.assertIn("geos content create", gaps[0].recommendation or "")

    def test_cannibalization_detected(self) -> None:
        self.content.create_idea("origem de crédito")
        self.content.create_idea("origem de crédito")  # same topic
        issues = self.engine.audit_content()
        cannibal = [i for i in issues if i.category == "cannibalization"]
        self.assertEqual(len(cannibal), 1)

    def test_decay_heuristic(self) -> None:
        item = self.content.create_idea("origem de crédito")
        self.db.conn_checked.execute(
            "UPDATE content SET created_at = ?, updated_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00", item["id"]),
        )
        issues = self.engine.audit_content()
        decay = [i for i in issues if i.category == "decay"]
        self.assertEqual(len(decay), 1)
        self.assertIn("nunca atualizado", decay[0].detail or "")

    def test_fresh_content_no_decay(self) -> None:
        item = self.content.create_idea("origem de crédito")
        self.db.conn_checked.execute(
            "UPDATE content SET created_at = ?, updated_at = ? WHERE id = ?",
            ("2026-08-01T00:00:00+00:00", "2026-08-02T00:00:00+00:00", item["id"]),
        )
        self.content.produce_draft(item["id"])  # body present, not thin
        issues = self.engine.audit_content()
        self.assertEqual([i for i in issues if i.category == "decay"], [])


if __name__ == "__main__":
    unittest.main()
