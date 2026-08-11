"""Academy Engine (SPEC-036): educational content management.

Academy manages tracks, courses, modules, lessons, labs, challenges,
assessments, and certifications. Content flows through: DRAFT → PUBLISHED →
ARCHIVED. Learners progress through: ENROLLED → IN_PROGRESS → COMPLETED.

Every piece of content has prerequisites, estimated duration, and difficulty
level. Certifications are issued upon completion of assessment requirements.
"""

from __future__ import annotations

from typing import Any

from ..core.events import SqliteEventBus
from ..storage.database import Database
from ..storage.repos import NotFoundError, RepoFactory
from ..util import new_id, now_iso, slugify

# Content statuses
CONTENT_STATUSES: dict[str, set[str]] = {
    "DRAFT": {"PUBLISHED", "ARCHIVED"},
    "PUBLISHED": {"ARCHIVED"},
    "ARCHIVED": set(),
}

# Learner progress statuses
PROGRESS_STATUSES: dict[str, set[str]] = {
    "ENROLLED": {"IN_PROGRESS", "COMPLETED", "DROPPED"},
    "IN_PROGRESS": {"COMPLETED", "DROPPED"},
    "COMPLETED": set(),
    "DROPPED": set(),
}

# Content types
CONTENT_TYPES = ("track", "course", "module", "lesson", "lab", "challenge", "assessment")

# Difficulty levels
DIFFICULTY_LEVELS = ("beginner", "intermediate", "advanced", "expert")


class AcademyError(ValueError):
    """Invalid academy operation (bad status, missing required field)."""


class AcademyEngine:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._repo = RepoFactory(db)

    # ---- content lifecycle -------------------------------------------------
    def create(
        self,
        title: str,
        content_type: str = "lesson",
        description: str | None = None,
        difficulty: str = "beginner",
        duration_minutes: int | None = None,
        parent_id: str | None = None,
        prerequisites: list[str] | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create new academy content."""
        title = title.strip()
        if not title:
            raise AcademyError("title is required")
        if content_type not in CONTENT_TYPES:
            raise AcademyError(f"unknown content_type {content_type!r}")
        if difficulty not in DIFFICULTY_LEVELS:
            raise AcademyError(f"unknown difficulty {difficulty!r}")

        # Validate parent exists if provided
        if parent_id:
            self.get(parent_id)

        slug = _unique_slug(self._repo.academy, slugify(title))
        content_id = self._repo.academy.create(
            title=title,
            slug=slug,
            content_type=content_type,
            description=description,
            difficulty=difficulty,
            duration_minutes=duration_minutes,
            parent_id=parent_id,
            prerequisites=prerequisites or [],
            tags=tags or [],
            metadata=metadata or {},
        )

        try:
            SqliteEventBus(self._db).publish(
                "academy.created",
                {"content_id": content_id, "title": title, "type": content_type},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass

        return self.get(content_id)

    def get(self, content_id: str) -> dict[str, Any]:
        """Get academy content by ID."""
        item = self._repo.academy.get(content_id)
        if item is None:
            raise NotFoundError(f"academy content {content_id}")
        return item

    def list(
        self,
        content_type: str | None = None,
        status: str | None = None,
        difficulty: str | None = None,
        parent_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List academy content with filters."""
        return self._repo.academy.list(
            content_type=content_type, status=status,
            difficulty=difficulty, parent_id=parent_id, limit=limit
        )

    def by_slug(self, slug: str) -> dict[str, Any]:
        """Get content by slug."""
        item = self._repo.academy.by_slug(slug)
        if item is None:
            raise NotFoundError(f"academy content with slug {slug}")
        return item

    # ---- lifecycle transitions ---------------------------------------------
    def transition(self, content_id: str, target: str) -> dict[str, Any]:
        """Transition content to new status."""
        item = self.get(content_id)
        target = target.upper()
        allowed = CONTENT_STATUSES.get(item["status"], set())
        if target not in allowed:
            raise AcademyError(
                f"invalid transition {item['status']} → {target} "
                f"(allowed: {sorted(allowed) or 'none'})"
            )

        self._repo.academy.update_status(content_id, target)

        try:
            SqliteEventBus(self._db).publish(
                "academy.status_changed",
                {"content_id": content_id, "from": item["status"], "to": target},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass

        return self.get(content_id)

    def publish(self, content_id: str) -> dict[str, Any]:
        """Publish content."""
        return self.transition(content_id, "PUBLISHED")

    def archive(self, content_id: str) -> dict[str, Any]:
        """Archive content."""
        return self.transition(content_id, "ARCHIVED")

    # ---- hierarchy ---------------------------------------------------------
    def list_children(self, parent_id: str) -> list[dict[str, Any]]:
        """List child content items."""
        self.get(parent_id)  # validate exists
        return self._repo.academy.list(parent_id=parent_id)

    def get_tree(self, content_id: str) -> dict[str, Any]:
        """Get content with its children (recursive)."""
        item = self.get(content_id)
        children = self.list_children(content_id)
        child_trees = [self.get_tree(child["id"]) for child in children]
        return {**item, "children": child_trees}

    # ---- learner progress --------------------------------------------------
    def enroll_learner(self, content_id: str, learner_id: str) -> dict[str, Any]:
        """Enroll a learner in content."""
        self.get(content_id)  # validate exists

        # Check prerequisites
        item = self.get(content_id)
        prerequisites = item.get("prerequisites") or []
        for prereq_id in prerequisites:
            prereq_status = self.get_learner_status(prereq_id, learner_id)
            if prereq_status != "COMPLETED":
                raise AcademyError(
                    f"prerequisite {prereq_id} not completed (status: {prereq_status})"
                )

        enrollment_id = self._repo.academy.enroll_learner(content_id, learner_id)

        try:
            SqliteEventBus(self._db).publish(
                "academy.enrolled",
                {"content_id": content_id, "learner_id": learner_id},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass

        return self._repo.academy.get_enrollment(enrollment_id)

    def get_learner_status(self, content_id: str, learner_id: str) -> str | None:
        """Get learner's status for content."""
        enrollment = self._repo.academy.get_enrollment_by_learner(content_id, learner_id)
        return enrollment["status"] if enrollment else None

    def update_progress(
        self, content_id: str, learner_id: str, progress_pct: float,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Update learner progress."""
        enrollment = self._repo.academy.get_enrollment_by_learner(content_id, learner_id)
        if enrollment is None:
            raise AcademyError(f"learner {learner_id} not enrolled in {content_id}")
        if enrollment["status"] not in ("ENROLLED", "IN_PROGRESS"):
            raise AcademyError(f"cannot update progress for {enrollment['status']} enrollment")

        self._repo.academy.update_progress(enrollment["id"], progress_pct, notes)

        # Auto-transition to IN_PROGRESS if first update
        if enrollment["status"] == "ENROLLED" and progress_pct > 0:
            self._repo.academy.update_enrollment_status(enrollment["id"], "IN_PROGRESS")

        # Auto-complete if 100%
        if progress_pct >= 100:
            self._repo.academy.update_enrollment_status(enrollment["id"], "COMPLETED")
            try:
                SqliteEventBus(self._db).publish(
                    "academy.completed",
                    {"content_id": content_id, "learner_id": learner_id},
                    trace_id=None,
                )
            except Exception:  # noqa: BLE001
                pass

        return self._repo.academy.get_enrollment(enrollment["id"])

    def list_learners(self, content_id: str) -> list[dict[str, Any]]:
        """List all learners for content."""
        self.get(content_id)  # validate exists
        return self._repo.academy.list_learners(content_id)

    # ---- certifications ----------------------------------------------------
    def issue_certification(
        self, content_id: str, learner_id: str,
        assessment_score: float | None = None,
    ) -> dict[str, Any]:
        """Issue a certification for completed content."""
        status = self.get_learner_status(content_id, learner_id)
        if status != "COMPLETED":
            raise AcademyError(f"cannot certify: learner status is {status}")

        cert_id = self._repo.academy.issue_certification(
            content_id, learner_id, assessment_score
        )

        try:
            SqliteEventBus(self._db).publish(
                "academy.certified",
                {"content_id": content_id, "learner_id": learner_id, "cert_id": cert_id},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass

        return self._repo.academy.get_certification(cert_id)

    def list_certifications(self, learner_id: str | None = None) -> list[dict[str, Any]]:
        """List certifications."""
        return self._repo.academy.list_certifications(learner_id=learner_id)

    # ---- analytics ---------------------------------------------------------
    def content_analytics(self, content_id: str) -> dict[str, Any]:
        """Get analytics for content."""
        item = self.get(content_id)
        learners = self.list_learners(content_id)

        total = len(learners)
        enrolled = sum(1 for l in learners if l["status"] == "ENROLLED")
        in_progress = sum(1 for l in learners if l["status"] == "IN_PROGRESS")
        completed = sum(1 for l in learners if l["status"] == "COMPLETED")
        dropped = sum(1 for l in learners if l["status"] == "DROPPED")

        return {
            "content_id": content_id,
            "title": item["title"],
            "total_learners": total,
            "enrolled": enrolled,
            "in_progress": in_progress,
            "completed": completed,
            "dropped": dropped,
            "completion_rate": round(completed / total * 100, 1) if total else 0,
        }

    def learner_summary(self, learner_id: str) -> dict[str, Any]:
        """Get learner's overall summary."""
        enrollments = self._repo.academy.list_learner_enrollments(learner_id)
        certifications = self.list_certifications(learner_id)

        total = len(enrollments)
        completed = sum(1 for e in enrollments if e["status"] == "COMPLETED")

        return {
            "learner_id": learner_id,
            "total_enrollments": total,
            "completed": completed,
            "certifications": len(certifications),
            "enrollments": enrollments,
        }


def _unique_slug(repo, base: str) -> str:
    """Generate a unique slug."""
    candidate = base or "untitled"
    if repo.by_slug(candidate) is None:
        return candidate
    return f"{candidate}-{new_id()[:6]}"
