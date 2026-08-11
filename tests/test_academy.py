"""Tests for Academy Engine (SPEC-036)."""

from __future__ import annotations

import unittest

from geos.domains.academy import AcademyEngine, AcademyError
from geos.storage.database import Database


class AcademyEngineTests(unittest.TestCase):
    """Academy content lifecycle tests."""

    def setUp(self) -> None:
        self.db = Database(":memory:")
        self.db.open()
        self.db.migrate()
        self.engine = AcademyEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_create_content(self) -> None:
        """Create academy content."""
        item = self.engine.create(
            title="Python Basics",
            content_type="course",
            description="Learn Python fundamentals",
            difficulty="beginner",
            duration_minutes=120,
        )
        self.assertEqual(item["title"], "Python Basics")
        self.assertEqual(item["content_type"], "course")
        self.assertEqual(item["status"], "DRAFT")

    def test_create_empty_title_raises(self) -> None:
        """Empty title should raise AcademyError."""
        with self.assertRaises(AcademyError):
            self.engine.create(title="")

    def test_create_invalid_type_raises(self) -> None:
        """Invalid content type should raise AcademyError."""
        with self.assertRaises(AcademyError):
            self.engine.create(title="Test", content_type="invalid")

    def test_publish_content(self) -> None:
        """Publish content."""
        item = self.engine.create(title="Test Course")
        published = self.engine.publish(item["id"])
        self.assertEqual(published["status"], "PUBLISHED")

    def test_archive_content(self) -> None:
        """Archive content."""
        item = self.engine.create(title="Test Course")
        self.engine.publish(item["id"])
        archived = self.engine.archive(item["id"])
        self.assertEqual(archived["status"], "ARCHIVED")

    def test_invalid_transition_raises(self) -> None:
        """Invalid transition should raise AcademyError."""
        item = self.engine.create(title="Test Course")
        with self.assertRaises(AcademyError):
            self.engine.transition(item["id"], "COMPLETED")  # DRAFT → COMPLETED invalid

    def test_create_with_parent(self) -> None:
        """Create content with parent."""
        course = self.engine.create(title="Python Course", content_type="course")
        module = self.engine.create(
            title="Variables", content_type="module", parent_id=course["id"]
        )
        children = self.engine.list_children(course["id"])
        self.assertEqual(len(children), 1)

    def test_enroll_learner(self) -> None:
        """Enroll a learner."""
        item = self.engine.create(title="Test Course")
        self.engine.publish(item["id"])
        enrollment = self.engine.enroll_learner(item["id"], "learner-1")
        self.assertEqual(enrollment["status"], "ENROLLED")

    def test_update_progress(self) -> None:
        """Update learner progress."""
        item = self.engine.create(title="Test Course")
        self.engine.publish(item["id"])
        self.engine.enroll_learner(item["id"], "learner-1")
        updated = self.engine.update_progress(item["id"], "learner-1", 50.0)
        self.assertEqual(updated["progress_pct"], 50.0)
        self.assertEqual(updated["status"], "IN_PROGRESS")

    def test_auto_complete(self) -> None:
        """Auto-complete when progress reaches 100%."""
        item = self.engine.create(title="Test Course")
        self.engine.publish(item["id"])
        self.engine.enroll_learner(item["id"], "learner-1")
        updated = self.engine.update_progress(item["id"], "learner-1", 100.0)
        self.assertEqual(updated["status"], "COMPLETED")

    def test_issue_certification(self) -> None:
        """Issue certification."""
        item = self.engine.create(title="Test Course")
        self.engine.publish(item["id"])
        self.engine.enroll_learner(item["id"], "learner-1")
        self.engine.update_progress(item["id"], "learner-1", 100.0)
        cert = self.engine.issue_certification(item["id"], "learner-1", 95.0)
        self.assertEqual(cert["assessment_score"], 95.0)

    def test_content_analytics(self) -> None:
        """Get content analytics."""
        item = self.engine.create(title="Test Course")
        self.engine.publish(item["id"])
        self.engine.enroll_learner(item["id"], "learner-1")
        self.engine.enroll_learner(item["id"], "learner-2")
        analytics = self.engine.content_analytics(item["id"])
        self.assertEqual(analytics["total_learners"], 2)


if __name__ == "__main__":
    unittest.main()
