"""SPEC-014 memory tests."""

from __future__ import annotations

import unittest

from geos.intelligence.memory import MemoryStore, WorkingMemory
from tests.helpers import temp_db


class MemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()
        self.mem = MemoryStore(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_put_get(self) -> None:
        self.mem.put("session", "topic", "origem de crédito", source="workflow", confidence=0.9)
        self.assertEqual(self.mem.get("session", "topic"), "origem de crédito")

    def test_ttl_expiry(self) -> None:
        self.mem.put("session", "temp", "valor", ttl_seconds=1)
        self.assertEqual(self.mem.get("session", "temp"), "valor")
        self.mem.put("session", "expired", "x", ttl_seconds=-1)
        self.assertIsNone(self.mem.get("session", "expired"))

    def test_overwrite_refreshes(self) -> None:
        self.mem.put("agent", "k", "a")
        self.mem.put("agent", "k", "b")
        self.assertEqual(self.mem.get("agent", "k"), "b")

    def test_list_and_delete(self) -> None:
        self.mem.put("session", "a", 1)
        self.mem.put("session", "b", 2)
        self.mem.put("agent", "c", 3)
        self.assertEqual(len(self.mem.list("session")), 2)
        self.assertEqual(len(self.mem.list()), 3)
        self.assertTrue(self.mem.delete("session", "a"))
        self.assertFalse(self.mem.delete("session", "a"))
        self.assertEqual(len(self.mem.list("session")), 1)

    def test_working_memory(self) -> None:
        wm = WorkingMemory()
        wm["x"] = 1
        self.assertEqual(wm.get("x"), 1)
        self.assertIn("x", wm)
        wm.clear()
        self.assertNotIn("x", wm)


if __name__ == "__main__":
    unittest.main()
