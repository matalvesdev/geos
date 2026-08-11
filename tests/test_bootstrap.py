"""Tests: SPEC-103 bootstrap, SPEC-106 plan, automations, SPEC-038 control center."""

from __future__ import annotations

import unittest
from pathlib import Path

from geos.core.automations import (AutomationRegistry, default_automations,
                                   register_default_automations, run_automations)
from geos.discovery.bootstrap import bootstrap_workspace
from geos.domains.control_center import ControlCenter
from tests.helpers import TempDir, temp_db


class BootstrapTests(unittest.TestCase):
    def test_bootstrap_creates_working_workspace(self) -> None:
        with TempDir() as root:
            result = bootstrap_workspace(root)
            self.assertEqual(result["workflows"], 4)
            self.assertEqual(result["example_docs"], 3)
            self.assertTrue((root / "workflows" / "hello.yaml").is_file())
            self.assertTrue((root / "examples" / "docs" / "README.md").is_file())
            self.assertTrue(result["content_id"])
            # knowledge ingested (searchable)
            from geos.config import Settings

            settings = Settings.from_path(result["config"], root=str(root))
            from geos.storage.database import Database
            from geos.intelligence.knowledge import search

            db = Database(settings.db_path)
            db.open()
            try:
                hits = search(db, "cash application")
                self.assertTrue(hits)
            finally:
                db.close()
            # automations persisted
            registry = AutomationRegistry(root / ".geos" / "automations.json")
            ids = {e.id for e in registry.list()}
            self.assertIn("social-worker", ids)
            self.assertIn("analytics-collect", ids)

    def test_bootstrap_is_idempotent(self) -> None:
        with TempDir() as root:
            first = bootstrap_workspace(root)
            second = bootstrap_workspace(root)
            self.assertEqual(first["content_id"], second["content_id"])
            self.assertEqual(second["workflows"], 0, "no re-copy on rerun")
            self.assertEqual(second["example_docs"], 0, "no re-write on rerun")


class AutomationRegistryTests(unittest.TestCase):
    def test_defaults_registered_once(self) -> None:
        with TempDir() as tmp:
            registry = AutomationRegistry(tmp / "automations.json")
            added1 = register_default_automations(registry)
            added2 = register_default_automations(registry)
            self.assertEqual(len(added1), 5)
            self.assertEqual(added2, [], "idempotent registration")
            self.assertEqual(len(registry.list()), 5)
            # survives reload
            registry2 = AutomationRegistry(tmp / "automations.json")
            self.assertEqual(len(registry2.list()), 5)

    def test_remove(self) -> None:
        with TempDir() as tmp:
            registry = AutomationRegistry(tmp / "automations.json")
            register_default_automations(registry)
            self.assertTrue(registry.remove("social-worker"))
            self.assertFalse(registry.remove("social-worker"))
            self.assertIsNone(registry.get("social-worker"))

    def test_default_automations_have_5_field_cron(self) -> None:
        for entry in default_automations():
            self.assertEqual(len(entry.cron.split()), 5, entry.id)


class AutomationRunTests(unittest.TestCase):
    def test_run_automations_executes_internal_handlers(self) -> None:
        db = temp_db()
        try:
            with TempDir() as tmp:
                registry = AutomationRegistry(tmp / "automations.json")
                # analytics-collect whose window has already passed → fires now
                entry = default_automations()[2]  # analytics-collect
                entry.next_run = "2000-01-01T00:00:00+00:00"
                registry.add(entry)
                enqueued, processed = run_automations(registry, db)
                self.assertEqual(enqueued, 1)
                self.assertEqual(processed, 1)
                # a snapshot was created by the handler
                from geos.storage.repos import RepoFactory

                self.assertIsNotNone(
                    RepoFactory(db).analytics.latest_snapshot())
                # next_run was advanced and persisted
                self.assertIsNotNone(registry.get("analytics-collect").next_run)  # type: ignore[union-attr]
        finally:
            db.close()

    def test_run_automations_skips_future_schedules(self) -> None:
        db = temp_db()
        try:
            with TempDir() as tmp:
                registry = AutomationRegistry(tmp / "automations.json")
                registry.add(default_automations()[2])  # fresh, next_run=None
                enqueued, processed = run_automations(registry, db)
                self.assertEqual(enqueued, 0, "cron with future window must not fire")
                self.assertEqual(processed, 0)
        finally:
            db.close()

    def test_fresh_automation_becomes_alive_after_first_run(self) -> None:
        """Regression (review): a fresh entry with next_run=None must persist its
        first next-run on the first invocation, or it would never fire again."""
        db = temp_db()
        try:
            with TempDir() as tmp:
                registry = AutomationRegistry(tmp / "automations.json")
                registry.add(default_automations()[2])  # analytics-collect
                run_automations(registry, db)  # run 1: persists next_run, no fire
                entry = registry.get("analytics-collect")
                self.assertIsNotNone(entry.next_run,  # type: ignore[union-attr]
                                     "first next_run must be persisted")
                # force the persisted window into the past, then run 2 fires
                entry.next_run = "2000-01-01T00:00:00+00:00"  # type: ignore[union-attr]
                registry.add(entry)
                enqueued, processed = run_automations(registry, db)
                self.assertEqual(enqueued, 1)
                self.assertEqual(processed, 1)
                from geos.storage.repos import RepoFactory

                self.assertIsNotNone(
                    RepoFactory(db).analytics.latest_snapshot())
        finally:
            db.close()

    def test_social_worker_handler_respects_approval(self) -> None:
        from geos.core.jobs import Worker
        from geos.core.automations import register_internal_handlers
        from geos.core.jobs import SqliteJobQueue
        from geos.domains.content import ContentEngine
        from geos.domains.social import SocialEngine

        db = temp_db()
        try:
            # content -> social post gated (approval PENDING)
            content = ContentEngine(db)
            item = content.create_idea("Post social", keywords=["geos"])
            content.write_brief(item["id"])
            content.produce_draft(item["id"])
            content.transition(item["id"], "APPROVED")
            with TempDir() as tmp:
                engine = SocialEngine(db, publish_dir=str(tmp))
                post = engine.prepare(item["id"], channel="x")
                engine.publish(post["id"])  # APPROVAL_PENDING, no decision
                # enqueue a social.worker job and run it
                queue = SqliteJobQueue(db)
                queue.enqueue("social.worker", {}, idempotency_key="w1")
                worker = Worker(queue)
                register_internal_handlers(worker, db)
                worker.run_once()
                # still nothing written (no approval decision)
                self.assertFalse(list(tmp.glob("*.txt")))
        finally:
            db.close()


class ControlCenterTests(unittest.TestCase):
    def test_build_generates_self_contained_html(self) -> None:
        db = temp_db()
        try:
            with TempDir() as tmp:
                path = ControlCenter(db).build(tmp / "cc.html")
                text = path.read_text(encoding="utf-8")
                self.assertIn("GEOS", text)
                self.assertIn("Control", text)
                self.assertIn("SPEC-038", text)
                self.assertIn("<style>", text)
                self.assertNotIn("<script", text, "no JS: pure CSS dashboard")
        finally:
            db.close()

    def test_build_with_analytics_snapshot_shows_metrics(self) -> None:
        from geos.domains.analytics import AnalyticsEngine

        db = temp_db()
        try:
            AnalyticsEngine(db).collect()
            with TempDir() as tmp:
                text = ControlCenter(db).build(tmp / "cc.html").read_text(
                    encoding="utf-8")
                self.assertIn("content_total", text)
                self.assertIn("Insights", text)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
