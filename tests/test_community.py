"""Tests for Community Engine (SPEC-037)."""

from __future__ import annotations

import unittest

from geos.domains.community import CommunityEngine, CommunityError
from geos.storage.database import Database


class CommunityEngineTests(unittest.TestCase):
    """Community member and thread tests."""

    def setUp(self) -> None:
        self.db = Database(":memory:")
        self.db.open()
        self.db.migrate()
        self.engine = CommunityEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_add_member(self) -> None:
        """Add a community member."""
        member = self.engine.add_member(
            name="John Doe", email="john@example.com", platform="discord"
        )
        self.assertEqual(member["name"], "John Doe")
        self.assertEqual(member["platform"], "discord")

    def test_add_empty_name_raises(self) -> None:
        """Empty name should raise CommunityError."""
        with self.assertRaises(CommunityError):
            self.engine.add_member(name="")

    def test_create_thread(self) -> None:
        """Create a thread."""
        member = self.engine.add_member(name="John")
        thread = self.engine.create_thread(
            channel="general", title="Hello World", author_id=member["id"]
        )
        self.assertEqual(thread["title"], "Hello World")
        self.assertEqual(thread["status"], "open")

    def test_add_reply(self) -> None:
        """Add a reply to a thread."""
        member = self.engine.add_member(name="John")
        thread = self.engine.create_thread(channel="general", title="Question")
        reply = self.engine.add_reply(thread["id"], member["id"], "Answer here")
        self.assertEqual(reply["content"], "Answer here")

    def test_resolve_thread(self) -> None:
        """Resolve a thread."""
        thread = self.engine.create_thread(channel="general", title="Issue")
        resolved = self.engine.resolve_thread(thread["id"])
        self.assertEqual(resolved["status"], "resolved")

    def test_channel_analytics(self) -> None:
        """Get channel analytics."""
        self.engine.create_thread(channel="general", title="T1")
        self.engine.create_thread(channel="general", title="T2")
        analytics = self.engine.channel_analytics("general")
        self.assertEqual(analytics["total_threads"], 2)

    def test_community_overview(self) -> None:
        """Get community overview."""
        self.engine.add_member(name="John")
        self.engine.add_member(name="Jane")
        self.engine.create_thread(channel="general", title="T1")
        overview = self.engine.community_overview()
        self.assertEqual(overview["total_members"], 2)
        self.assertEqual(overview["total_threads"], 1)


if __name__ == "__main__":
    unittest.main()
