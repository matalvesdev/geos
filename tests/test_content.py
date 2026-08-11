"""SPEC-022 Content Engine tests."""

from __future__ import annotations

import unittest

from geos.domains.content import ContentEngine, ContentError
from tests.helpers import temp_db


class ContentEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()
        self.engine = ContentEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_create_idea_scores_and_persists(self) -> None:
        item = self.engine.create_idea(
            "origem de crédito bancário", content_type="blog_post",
            keywords=["origem de crédito", "conciliação"],
        )
        self.assertEqual(item["status"], "IDEA")
        self.assertEqual(item["content_type"], "blog_post")
        self.assertIsNotNone(item["score"])
        self.assertGreaterEqual(item["score"], 0.0)
        self.assertLessEqual(item["score"], 1.0)
        self.assertIn("search_potential", item["score_breakdown"])
        self.assertTrue(item["mock"])
        # persisted and retrievable
        fetched = self.engine.get(item["id"])
        self.assertEqual(fetched["title"], item["title"])

    def test_invalid_content_type_rejected(self) -> None:
        with self.assertRaises(ContentError):
            self.engine.create_idea("tema", content_type="nope")

    def test_duplicate_topic_lowers_novelty(self) -> None:
        a = self.engine.create_idea("conciliação de crédito")
        first = a["score_breakdown"]["novelty"]
        b = self.engine.create_idea("conciliação de crédito")
        second = b["score_breakdown"]["novelty"]
        self.assertGreater(first, second)  # 1/1 vs 1/2

    def test_pipeline_transitions_validated(self) -> None:
        item = self.engine.create_idea("origem de crédito")
        # invalid jumps are rejected
        with self.assertRaises(ContentError):
            self.engine.transition(item["id"], "PUBLISHED")
        # legal flow
        briefed = self.engine.write_brief(item["id"], audience="finops",
                                          cta="Agendar demo")
        self.assertEqual(briefed["status"], "BRIEFED")
        self.assertIn("Brief determinístico", briefed["brief"])
        drafted = self.engine.produce_draft(item["id"])
        self.assertEqual(drafted["status"], "DRAFTED")
        self.assertIn("# ", drafted["body"])
        self.assertEqual(drafted["version"], 2)  # draft snapshot bumped version
        approved = self.engine.transition(item["id"], "APPROVED")
        self.assertEqual(approved["status"], "APPROVED")
        published = self.engine.transition(item["id"], "PUBLISHED")
        self.assertEqual(published["status"], "PUBLISHED")
        # archived from published
        self.engine.transition(item["id"], "ARCHIVED")

    def test_versions_snapshotted(self) -> None:
        item = self.engine.create_idea("evidência documental")
        self.engine.write_brief(item["id"])
        self.engine.produce_draft(item["id"])
        versions = self.engine._content.versions(item["id"])
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["version"], 1)

    def test_repurpose_creates_variant(self) -> None:
        item = self.engine.create_idea("origem de crédito")
        self.engine.write_brief(item["id"])
        self.engine.produce_draft(item["id"])
        variant = self.engine.repurpose(item["id"], "social_post")
        self.assertEqual(variant["content_type"], "social_post")
        self.assertEqual(variant["status"], "DRAFTED")
        self.assertIn("repurposed", variant["body"])
        self.assertIn(f"repurposed-from:{item['id']}", variant["sources"])

    def test_score_explainable(self) -> None:
        item = self.engine.create_idea("crédito não identificado")
        result = self.engine.score(item["id"])
        self.assertEqual(len(result["breakdown"]), 9)
        self.assertAlmostEqual(
            result["score"],
            sum(result["breakdown"].values()) / len(result["breakdown"]),
            places=4,
        )

    def test_empty_keywords_list_ok(self) -> None:
        item = self.engine.create_idea("fluxo de conciliação")
        self.assertEqual(item.get("keywords"), [])

    def test_write_brief_only_from_idea(self) -> None:
        """Regression: write_brief must not rewind non-IDEA statuses."""
        item = self.engine.create_idea("origem de crédito")
        self.engine.write_brief(item["id"])
        self.engine.produce_draft(item["id"])
        with self.assertRaises(ContentError):
            self.engine.write_brief(item["id"])

    def test_topic_count_accurate_via_sql(self) -> None:
        self.engine.create_idea("conciliação de crédito")
        self.engine.create_idea("conciliação de crédito")
        self.engine.create_idea("Conciliação de Crédito")  # case-insensitive
        self.assertEqual(self.engine._topic_count("conciliação de crédito"), 3)


if __name__ == "__main__":
    unittest.main()
