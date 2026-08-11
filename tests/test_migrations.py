"""SPEC-002 migration + storage tests."""

from __future__ import annotations

import unittest

from geos.storage.database import Database
from geos.storage.migrations import MAX_VERSION
from tests.helpers import TempDir


class MigrationTests(unittest.TestCase):
    def test_fresh_db_migrates_to_max(self) -> None:
        db = Database(None)
        db.open()
        self.assertEqual(db.current_version(), 0)
        version = db.migrate()
        self.assertEqual(version, MAX_VERSION)
        db.close()

    def test_migrate_is_idempotent(self) -> None:
        db = Database(None)
        db.open()
        db.migrate()
        db.migrate()
        self.assertEqual(db.current_version(), MAX_VERSION)
        rows = db.conn_checked.execute(
            "SELECT COUNT(*) c FROM migration_history"
        ).fetchone()["c"]
        self.assertEqual(rows, len(__import__("geos.storage.migrations", fromlist=["MIGRATIONS"]).MIGRATIONS))
        db.close()

    def test_tables_exist(self) -> None:
        db = Database(None)
        db.open()
        db.migrate()
        conn = db.conn_checked
        for table in ("runs", "events", "jobs", "documents", "document_chunks",
                      "knowledge_nodes", "knowledge_edges", "approvals", "audit_log"):
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            self.assertIsNotNone(row, f"missing table {table}")
        fts = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='document_chunks_fts'"
        ).fetchone()
        self.assertIsNotNone(fts, "missing FTS5 virtual table")
        db.close()

    def test_fk_enforced(self) -> None:
        db = Database(None)
        db.open()
        db.migrate()
        with self.assertRaises(Exception):
            with db.conn_checked:
                db.conn_checked.execute(
                    "INSERT INTO document_chunks (chunk_id, document_id, chunk_index, position, content)"
                    " VALUES ('x', 'no-such-doc', 0, 0, 'y')"
                )
        db.close()

    def test_file_db_creates_dirs(self) -> None:
        with TempDir() as tmp:
            db = Database(tmp / "nested" / "state" / "geos.db")
            db.open()
            db.migrate()
            self.assertTrue((tmp / "nested" / "state" / "geos.db").is_file())
            db.close()


if __name__ == "__main__":
    unittest.main()
