"""Tests for Control Center Phase 5 enhancements."""

from __future__ import annotations

import unittest

from geos.domains.control_center import ControlCenter
from geos.storage.database import Database


class ControlCenterPhase5Tests(unittest.TestCase):
    """Control Center Phase 5 tests."""

    def setUp(self) -> None:
        self.db = Database(":memory:")
        self.db.open()
        self.db.migrate()
        self.engine = ControlCenter(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_rag_debugger(self) -> None:
        """Test RAG debugger."""
        result = self.engine.rag_debugger("test query")
        self.assertIn("query", result)
        self.assertIn("results_count", result)
        self.assertIn("index_stats", result)
        self.assertEqual(result["query"], "test query")

    def test_run_debugger_not_found(self) -> None:
        """Test run debugger with non-existent run."""
        result = self.engine.run_debugger("non-existent-id")
        self.assertIn("error", result)

    def test_self_audit(self) -> None:
        """Test self-audit."""
        result = self.engine.self_audit()
        self.assertIn("checks", result)
        self.assertIn("summary", result)
        self.assertIn("recommendations", result)
        self.assertIsInstance(result["checks"], list)
        self.assertGreater(len(result["checks"]), 0)

    def test_self_audit_score(self) -> None:
        """Test self-audit score calculation."""
        result = self.engine.self_audit()
        score = result["summary"]["score"]
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_list_backups_empty(self) -> None:
        """Test listing backups when none exist."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            backups = self.engine.list_backups(tmpdir)
            self.assertEqual(len(backups), 0)


if __name__ == "__main__":
    unittest.main()
