"""SPEC-025 social scheduler tests: per-channel posts, limits, approval-gated publish."""

from __future__ import annotations

import unittest

from geos.domains.content import ContentEngine
from geos.domains.social import (CHANNELS, SocialEngine, SocialError,
                                 build_post_text, get_adapter, register_adapter,
                                 render_social_post)
from tests.helpers import TempDir, temp_db


def _approved_content(db, topic: str = "Cash application na prática") -> str:
    engine = ContentEngine(db)
    item = engine.create_idea(topic, keywords=["cash application", "finanças"])
    engine.write_brief(item["id"], cta="Leia o artigo completo")
    engine.produce_draft(item["id"])
    engine.transition(item["id"], "APPROVED")
    return item["id"]


class BuildPostTextTests(unittest.TestCase):
    def test_known_channel_limits_are_deterministic(self) -> None:
        self.assertEqual(CHANNELS["x"]["char_limit"], 280)
        self.assertEqual(CHANNELS["linkedin"]["char_limit"], 3000)
        self.assertEqual(CHANNELS["bluesky"]["char_limit"], 300)
        self.assertEqual(CHANNELS["instagram"]["char_limit"], 2200)

    def test_build_never_exceeds_channel_limit(self) -> None:
        content = {
            "title": "Título", "body": "# Intro\n\n" + ("palavra " * 200),
            "keywords": ["cash application"], "cta": "Leia mais", "slug": "titulo",
        }
        for channel in CHANNELS:
            payload = build_post_text(content, channel)
            self.assertLessEqual(payload["chars"], CHANNELS[channel]["char_limit"],
                                 f"{channel} deve respeitar o limite")
            self.assertIn("palavra", payload["text"])

    def test_build_truncates_honestly_and_marks_it(self) -> None:
        content = {"title": "T", "body": "# H\n\n" + ("x" * 500), "keywords": [],
                   "cta": "", "slug": "t"}
        payload = build_post_text(content, "x")
        self.assertTrue(payload["truncated"])
        self.assertLessEqual(payload["chars"], 280)
        self.assertTrue(payload["text"].endswith("…"))

    def test_build_never_exceeds_limit_with_hook_and_cta_near_budget(self) -> None:
        """Regression (review): the old per-part floor of 20 chars could push the
        final text over the channel limit; the final safety net must hold."""
        # hook consumes most of the budget; cta + hashtags still need space
        content = {"title": "T", "body": "# H\n\n" + ("h" * 240) + "\n\n" + ("e" * 200),
                   "keywords": ["x" * 10], "cta": "Leia o artigo completo",
                   "slug": "t"}
        for channel in CHANNELS:
            payload = build_post_text(content, channel)
            self.assertLessEqual(payload["chars"], CHANNELS[channel]["char_limit"],
                                 f"{channel}: final text must respect the limit")

    def test_hashtags_slugified_and_capped(self) -> None:
        content = {"title": "T", "body": "# H\n\ncorpo", "keywords": [
            "Cash Application", "cash application", "finanças corporativas",
            "automação", "contabilidade", "ERPs"], "cta": "", "slug": "t"}
        payload = build_post_text(content, "x")
        self.assertEqual(payload["hashtags"], ["cash-application",
                                               "financas-corporativas",
                                               "automacao", "contabilidade",
                                               "erps"])  # max 5, dedup
        self.assertNotIn("#", payload["text"],
                         "hashtags render from the field, not embedded in text")

    def test_render_includes_provenance_and_hashtags_once(self) -> None:
        """Regression: hashtags render from the `hashtags` field exactly once
        (duplicate-hashtag bug found in the CLI smoke test)."""
        post = {"id": "p1", "channel": "x", "slug": "x-ola", "content_id": "c1",
                "text": "Olá mundo", "hashtags": ["geos", "growth"]}
        rendered = render_social_post(post)
        self.assertIn("Olá mundo", rendered)
        self.assertEqual(rendered.count("#geos"), 1, "hashtags must not duplicate")
        self.assertEqual(rendered.count("#growth"), 1)
        self.assertIn("SPEC-025", rendered)
        self.assertIn("c1", rendered)


class PrepareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()
        self.engine = SocialEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_unknown_channel_rejected(self) -> None:
        content_id = _approved_content(self.db)
        with self.assertRaises(SocialError):
            self.engine.prepare(content_id, channel="tiktok")

    def test_prepare_requires_approved_or_scheduled(self) -> None:
        item = ContentEngine(self.db).create_idea("Tópico")
        with self.assertRaises(SocialError):
            self.engine.prepare(item["id"], channel="x")  # IDEA not ready

    def test_prepare_requires_draft_body(self) -> None:
        content_id = _approved_content(self.db)
        self.db.conn_checked.execute("UPDATE content SET body = '' WHERE id = ?",
                                     (content_id,))
        with self.assertRaises(SocialError):
            self.engine.prepare(content_id, channel="x")

    def test_prepare_creates_draft_post(self) -> None:
        content_id = _approved_content(self.db)
        post = self.engine.prepare(content_id, channel="x")
        self.assertEqual(post["status"], "DRAFT")
        self.assertEqual(post["channel"], "x")
        self.assertEqual(post["content_id"], content_id)
        self.assertTrue(post["text"])
        self.assertIn("cash-application", post["hashtags"])
        self.assertLessEqual(len(post["text"]), 280)

    def test_prepare_duplicate_content_channel_rejected(self) -> None:
        content_id = _approved_content(self.db)
        self.engine.prepare(content_id, channel="x")
        with self.assertRaises(SocialError):
            self.engine.prepare(content_id, channel="x")
        # but a different channel is fine
        self.engine.prepare(content_id, channel="linkedin")

    def test_reprepare_after_failure_reuses_row(self) -> None:
        """Regression (review): FAILED posts may be re-prepared without hitting
        the unique (content_id, channel) index (raw IntegrityError)."""
        content_id = _approved_content(self.db)
        post = self.engine.prepare(content_id, channel="x")
        # simulate an adapter failure → FAILED
        from geos.domains.social import register_adapter

        class Boom:
            name = "boom"

            def publish(self, _post):
                raise OSError("api down")

        register_adapter("boom", Boom)
        try:
            self.engine._repo.social.update(post["id"], adapter="boom")
            with self.assertRaises(SocialError):
                self.engine.publish(post["id"], approve=True)
        finally:
            from geos.domains.social import _ADAPTERS

            _ADAPTERS.pop("boom", None)
        self.assertEqual(self.engine.get(post["id"])["status"], "FAILED")
        # re-prepare must succeed and reuse the same row (no IntegrityError)
        again = self.engine.prepare(content_id, channel="x")
        self.assertEqual(again["id"], post["id"])
        self.assertEqual(again["status"], "DRAFT")

    def test_prepare_with_scheduled_at(self) -> None:
        content_id = _approved_content(self.db)
        post = self.engine.prepare(content_id, channel="bluesky",
                                   scheduled_at="2099-01-01T09:00:00+00:00")
        self.assertEqual(post["status"], "DRAFT")
        self.assertEqual(post["scheduled_at"], "2099-01-01T09:00:00+00:00")


class PublishTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()
        self.engine = SocialEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_publish_without_approval_is_gated(self) -> None:
        content_id = _approved_content(self.db)
        post = self.engine.prepare(content_id, channel="x")
        with TempDir() as tmp:
            result = SocialEngine(self.db, publish_dir=str(tmp)).publish(post["id"])
            self.assertEqual(result["status"], "APPROVAL_PENDING")
            self.assertTrue(result["approval_id"])
            self.assertFalse(list(tmp.glob("*.txt")))
            pending = SocialEngine(self.db)._repo.approvals.list_pending()
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0].action, "social.publish")

    def test_repeated_gated_publish_reuses_pending_approval(self) -> None:
        content_id = _approved_content(self.db)
        with TempDir() as tmp:
            engine = SocialEngine(self.db, publish_dir=str(tmp))
            post = engine.prepare(content_id, channel="x")
            first = engine.publish(post["id"])
            second = engine.publish(post["id"])
            self.assertEqual(first["approval_id"], second["approval_id"])
            pending = SocialEngine(self.db)._repo.approvals.list_pending()
            self.assertEqual(len(pending), 1)

    def test_approval_decided_only_after_successful_publish(self) -> None:
        content_id = _approved_content(self.db)
        post = self.engine.prepare(content_id, channel="x")

        class Boom:
            name = "boom"

            def publish(self, _post):
                raise OSError("api down")

        register_adapter("boom", Boom)
        try:
            self.engine._repo.social.update(post["id"], adapter="boom")
            with self.assertRaises(SocialError):
                self.engine.publish(post["id"], approve=True)
        finally:
            from geos.domains.social import _ADAPTERS

            _ADAPTERS.pop("boom", None)
        failed = self.engine.get(post["id"])
        self.assertEqual(failed["status"], "FAILED")
        approval = SocialEngine(self.db)._repo.approvals.get(failed["approval_id"])
        self.assertEqual(approval.status, "PENDING",  # type: ignore[union-attr]
                         "decision must not precede a successful write")

    def test_publish_approved_writes_post_file(self) -> None:
        content_id = _approved_content(self.db)
        with TempDir() as tmp:
            engine = SocialEngine(self.db, publish_dir=str(tmp))
            post = engine.prepare(content_id, channel="x")
            published = engine.publish(post["id"], approve=True, decided_by="editor")
            self.assertEqual(published["status"], "PUBLISHED")
            self.assertTrue(published["published_at"])
            target = tmp / f"x-{post['slug']}.txt"
            self.assertTrue(target.is_file())
            text = target.read_text(encoding="utf-8")
            self.assertIn("#cash-application", text)
            self.assertIn("SPEC-025", text)

    def test_publish_approved_records_approval_decision(self) -> None:
        content_id = _approved_content(self.db)
        with TempDir() as tmp:
            engine = SocialEngine(self.db, publish_dir=str(tmp))
            post = engine.prepare(content_id, channel="x")
            published = engine.publish(post["id"], approve=True, decided_by="editor")
            approval = SocialEngine(self.db)._repo.approvals.get(
                published["approval_id"])
            self.assertIsNotNone(approval)
            self.assertEqual(approval.decision, "approve")  # type: ignore[union-attr]
            self.assertEqual(approval.decided_by, "editor")  # type: ignore[union-attr]

    def test_scheduled_future_post_queued_not_written(self) -> None:
        content_id = _approved_content(self.db)
        with TempDir() as tmp:
            engine = SocialEngine(self.db, publish_dir=str(tmp))
            post = engine.prepare(content_id, channel="x",
                                  scheduled_at="2099-01-01T09:00:00+00:00")
            result = engine.publish(post["id"], approve=True)
            self.assertEqual(result["status"], "SCHEDULED")
            self.assertFalse(list(tmp.glob("*.txt")),
                             "nada externo antes do horário (SPEC-025 R4)")
            self.assertEqual(len(engine.due()), 0)  # not due yet

    def test_due_lists_expired_scheduled_posts(self) -> None:
        """Future-scheduled post is queued; once the time passes it becomes due,
        and a new approved publish performs the external write."""
        content_id = _approved_content(self.db)
        with TempDir() as tmp:
            engine = SocialEngine(self.db, publish_dir=str(tmp))
            post = engine.prepare(content_id, channel="x",
                                  scheduled_at="2099-01-01T00:00:00+00:00")
            engine.publish(post["id"], approve=True)  # queued (SCHEDULED)
            self.assertEqual(len(engine.due()), 0)
            # time passes: the window arrives
            engine.schedule(post["id"], "2000-01-01T00:00:00+00:00")
            due = engine.due()
            self.assertEqual(len(due), 1)
            self.assertEqual(due[0]["id"], post["id"])
            published = engine.publish(post["id"], approve=True)
            self.assertEqual(published["status"], "PUBLISHED")
            self.assertTrue(list(tmp.glob("*.txt")))

    def test_publish_twice_fails(self) -> None:
        content_id = _approved_content(self.db)
        with TempDir() as tmp:
            engine = SocialEngine(self.db, publish_dir=str(tmp))
            post = engine.prepare(content_id, channel="x")
            engine.publish(post["id"], approve=True)
            with self.assertRaises(SocialError):
                engine.publish(post["id"], approve=True)

    def test_schedule_after_publish_fails(self) -> None:
        content_id = _approved_content(self.db)
        with TempDir() as tmp:
            engine = SocialEngine(self.db, publish_dir=str(tmp))
            post = engine.prepare(content_id, channel="x")
            engine.publish(post["id"], approve=True)
            with self.assertRaises(SocialError):
                engine.schedule(post["id"], "2099-01-01T09:00:00+00:00")


class AdapterTests(unittest.TestCase):
    def test_local_adapter_default(self) -> None:
        self.assertEqual(get_adapter("local").name, "local")
        with self.assertRaises(SocialError):
            get_adapter("twitter_api")  # not registered yet

    def test_registry_extension(self) -> None:
        class Stub:
            name = "stub"

            def publish(self, post):  # noqa: ANN001
                from geos.domains.social import SocialPublishResult

                return SocialPublishResult(path="/stub", url="https://example.com/p")

        register_adapter("stub", Stub)
        try:
            self.assertEqual(get_adapter("stub").name, "stub")
        finally:
            from geos.domains.social import _ADAPTERS

            _ADAPTERS.pop("stub", None)

    def test_local_adapter_writes_into_configured_dir(self) -> None:
        with TempDir() as tmp:
            from geos.domains.social import LocalSocialAdapter

            adapter = LocalSocialAdapter(str(tmp / "posts"))
            result = adapter.publish(
                {"id": "p1", "slug": "ola-mundo", "channel": "x",
                 "text": "Olá mundo", "hashtags": ["geos"], "content_id": "c1"})
            self.assertTrue((tmp / "posts" / "x-ola-mundo.txt").is_file())
            self.assertEqual(result.path, str(tmp / "posts" / "x-ola-mundo.txt"))


if __name__ == "__main__":
    unittest.main()
