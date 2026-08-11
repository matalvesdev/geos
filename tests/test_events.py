"""SPEC-004 event bus tests."""

from __future__ import annotations

import unittest

from geos.core.events import SqliteEventBus
from tests.helpers import temp_db


class EventBusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()
        self.bus = SqliteEventBus(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_publish_persists_and_dispatches(self) -> None:
        received: list[str] = []
        self.bus.subscribe("lead.created", lambda e: received.append(e.payload["id"]))
        event = self.bus.publish("lead.created", {"id": "L-1"}, trace_id="t1")
        self.assertEqual(received, ["L-1"])
        row = self.db.conn_checked.execute(
            "SELECT COUNT(*) c FROM events WHERE event_type='lead.created'"
        ).fetchone()["c"]
        self.assertEqual(row, 1)
        self.assertEqual(event.trace_id, "t1")

    def test_unsubscribe_stops_delivery(self) -> None:
        calls: list[int] = []

        def handler(_e: object) -> None:
            calls.append(1)

        self.bus.subscribe("docs.updated", handler)
        self.bus.publish("docs.updated", {})
        self.bus.unsubscribe("docs.updated", handler)
        self.bus.publish("docs.updated", {})
        self.assertEqual(len(calls), 1)

    def test_wildcard_subscription(self) -> None:
        received: list[str] = []
        self.bus.subscribe("*", lambda e: received.append(e.event_type))
        self.bus.publish("a.b", {})
        self.bus.publish("c.d", {})
        self.assertEqual(set(received), {"a.b", "c.d"})

    def test_handler_exception_does_not_break_bus(self) -> None:
        def boom(_e: object) -> None:
            raise RuntimeError("handler bug")

        seen: list[str] = []
        self.bus.subscribe("x.y", boom)
        self.bus.subscribe("x.y", lambda e: seen.append(e.event_type))
        self.bus.publish("x.y", {})
        self.assertEqual(seen, ["x.y"])


if __name__ == "__main__":
    unittest.main()
