"""SPEC-024 blog publisher tests: prepare, front matter, approval-gated publish."""

from __future__ import annotations

import unittest

from geos.domains.blog import (BlogEngine, BlogError, LocalMarkdownAdapter,
                               get_adapter, register_adapter, render_markdown)
from geos.domains.content import ContentEngine
from tests.helpers import TempDir, temp_db


def _approved_content(db, topic: str = "Como fazer cash application") -> str:
    engine = ContentEngine(db)
    item = engine.create_idea(topic, keywords=["cash application"])
    engine.write_brief(item["id"])
    engine.produce_draft(item["id"])
    engine.transition(item["id"], "APPROVED")
    return item["id"]


class PrepareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()
        self.engine = BlogEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_prepare_requires_approved_or_scheduled(self) -> None:
        item = ContentEngine(self.db).create_idea("Tópico")
        with self.assertRaises(BlogError):
            self.engine.prepare(item["id"])  # IDEA is not prepare-ready

    def test_prepare_requires_draft_body(self) -> None:
        # Simulate malformed data: APPROVED content whose body was wiped.
        content_id = _approved_content(self.db)
        self.db.conn_checked.execute("UPDATE content SET body = '' WHERE id = ?",
                                     (content_id,))
        with self.assertRaises(BlogError):
            self.engine.prepare(content_id)

    def test_prepare_creates_draft_post_with_front_matter(self) -> None:
        content_id = _approved_content(self.db)
        post = self.engine.prepare(content_id)
        self.assertEqual(post["status"], "DRAFT")
        self.assertEqual(post["content_id"], content_id)
        fm = post["front_matter"]
        self.assertEqual(fm["title"], "Como fazer cash application")
        self.assertEqual(fm["slug"], "como-fazer-cash-application")
        self.assertEqual(fm["mock"], True)  # honest provenance (SPEC-024 R2)
        self.assertEqual(fm["content_id"], content_id)
        self.assertIn("cash application", fm["keywords"])
        self.assertTrue(post["body"])

    def test_prepare_duplicate_slug_rejected(self) -> None:
        content_id = _approved_content(self.db)
        self.engine.prepare(content_id)
        with self.assertRaises(BlogError):
            self.engine.prepare(content_id)

    def test_render_markdown_has_front_matter_and_provenance(self) -> None:
        content_id = _approved_content(self.db)
        post = self.engine.prepare(content_id)
        rendered = render_markdown(post)
        self.assertTrue(rendered.startswith("---\n"))
        self.assertIn("title: ", rendered)
        self.assertIn(f"slug: \"{post['slug']}\"", rendered)
        self.assertIn("Proveniência", rendered)
        self.assertIn(post["id"], rendered)

    def test_body_has_real_newlines_not_literal_backslash_n(self) -> None:
        """Regression: draft builders must emit real newlines so markdown renders."""
        content_id = _approved_content(self.db)
        post = self.engine.prepare(content_id)
        rendered = render_markdown(post)
        self.assertNotIn(chr(92) + "n", rendered,
                         "literal backslash-n leaks into published markdown")
        # markdown structural elements land on their own lines
        for token in ("# Como fazer cash application", "## Contexto",
                      "## Estrutura"):
            self.assertIn(token, rendered)


class PublishTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()
        self.engine = BlogEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_publish_without_approval_is_gated(self) -> None:
        content_id = _approved_content(self.db)
        post = self.engine.prepare(content_id)
        with TempDir() as tmp:
            result = BlogEngine(self.db, publish_dir=str(tmp)).publish(post["id"])
            self.assertEqual(result["status"], "APPROVAL_PENDING")
            self.assertTrue(result["approval_id"])
            # nothing written
            self.assertFalse(list(tmp.glob("*.md")))
            # a pending approval exists
            pending = BlogEngine(self.db)._repo.approvals.list_pending()
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0].action, "blog.publish")

    def test_repeated_gated_publish_reuses_pending_approval(self) -> None:
        """Regression: gated publish must not spam the approval queue."""
        content_id = _approved_content(self.db)
        with TempDir() as tmp:
            engine = BlogEngine(self.db, publish_dir=str(tmp))
            post = engine.prepare(content_id)
            first = engine.publish(post["id"])
            second = engine.publish(post["id"])  # still not approved
            self.assertEqual(first["approval_id"], second["approval_id"],
                             "one pending approval reused across gated calls")
            pending = BlogEngine(self.db)._repo.approvals.list_pending()
            self.assertEqual(len(pending), 1)

    def test_approval_decided_only_after_successful_publish(self) -> None:
        """Regression: failed adapter → post FAILED, approval stays PENDING."""
        from geos.domains.blog import BlogPublishResult, get_adapter, register_adapter

        content_id = _approved_content(self.db)
        post = self.engine.prepare(content_id)

        class Boom:
            name = "boom"

            def publish(self, _post):
                raise OSError("disk full")

        register_adapter("boom", Boom)
        try:
            self.engine._repo.blog.update(post["id"], adapter="boom")
            with self.assertRaises(BlogError):
                self.engine.publish(post["id"], approve=True)
        finally:
            from geos.domains.blog import _ADAPTERS

            _ADAPTERS.pop("boom", None)
        failed = self.engine.get(post["id"])
        self.assertEqual(failed["status"], "FAILED")
        approval = BlogEngine(self.db)._repo.approvals.get(failed["approval_id"])
        self.assertEqual(approval.status, "PENDING",  # type: ignore[union-attr]
                         "decision must not precede a successful write")

    def test_publish_approved_writes_markdown(self) -> None:
        content_id = _approved_content(self.db)
        with TempDir() as tmp:
            engine = BlogEngine(self.db, publish_dir=str(tmp))
            post = engine.prepare(content_id)
            published = engine.publish(post["id"], approve=True, decided_by="editor")
            self.assertEqual(published["status"], "PUBLISHED")
            self.assertTrue(published["published_at"])
            target = tmp / f"{post['slug']}.md"
            self.assertTrue(target.is_file())
            text = target.read_text(encoding="utf-8")
            self.assertIn(f"slug: \"{post['slug']}\"", text)
            self.assertIn("# Como fazer cash application", text)

    def test_publish_approved_records_approval_decision(self) -> None:
        content_id = _approved_content(self.db)
        with TempDir() as tmp:
            engine = BlogEngine(self.db, publish_dir=str(tmp))
            post = engine.prepare(content_id)
            published = engine.publish(post["id"], approve=True, decided_by="editor")
            approval = BlogEngine(self.db)._repo.approvals.get(
                published["approval_id"])
            self.assertIsNotNone(approval)
            self.assertEqual(approval.decision, "approve")  # type: ignore[union-attr]
            self.assertEqual(approval.decided_by, "editor")  # type: ignore[union-attr]

    def test_publish_twice_fails(self) -> None:
        content_id = _approved_content(self.db)
        with TempDir() as tmp:
            engine = BlogEngine(self.db, publish_dir=str(tmp))
            post = engine.prepare(content_id)
            engine.publish(post["id"], approve=True)
            with self.assertRaises(BlogError):
                engine.publish(post["id"], approve=True)


class AdapterTests(unittest.TestCase):
    def test_local_adapter_default(self) -> None:
        self.assertEqual(get_adapter("local").name, "local")
        with self.assertRaises(BlogError):
            get_adapter("wordpress")  # not registered yet

    def test_registry_extension(self) -> None:
        class Stub:
            name = "stub"

            def publish(self, post):  # noqa: ANN001
                from geos.domains.blog import BlogPublishResult

                return BlogPublishResult(path="/stub", url="https://example.com/x")

        register_adapter("stub", Stub)
        try:
            self.assertEqual(get_adapter("stub").name, "stub")
        finally:
            from geos.domains.blog import _ADAPTERS

            _ADAPTERS.pop("stub", None)

    def test_local_adapter_writes_into_configured_dir(self) -> None:
        with TempDir() as tmp:
            adapter = LocalMarkdownAdapter(str(tmp / "posts"))
            result = adapter.publish(
                {"id": "p1", "slug": "ola-mundo", "title": "Olá Mundo",
                 "body": "# Olá\n\ncorpo", "front_matter": {"title": "Olá Mundo",
                                                            "slug": "ola-mundo"},
                 "content_id": "c1"})
            self.assertTrue((tmp / "posts" / "ola-mundo.md").is_file())
            self.assertEqual(result.path, str(tmp / "posts" / "ola-mundo.md"))


if __name__ == "__main__":
    unittest.main()
