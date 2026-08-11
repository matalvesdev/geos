"""Email/Nurture Engine (SPEC-033): email sequences and lead nurturing.

Email sequences are triggered by events (lead captured, meeting completed, etc.)
and enroll leads in automated nurture flows. Each sequence has steps with delays
and content references.

IMPORTANT: No cold-outreach/spam (spec §139, §220). All email requires consent.
The suppression list ensures opted-out emails are never contacted.
"""

from __future__ import annotations

from typing import Any

from ..core.events import SqliteEventBus
from ..storage.database import Database
from ..storage.repos import NotFoundError, RepoFactory
from ..util import new_id, now_iso

# Trigger events for sequences
TRIGGER_EVENTS = (
    "lead_captured", "lead_qualified", "meeting_completed",
    "deal_created", "deal_won", "deal_lost",
    "manual", "content_downloaded", "webinar_attended",
)

# Sequence statuses
SEQUENCE_STATUSES = {"DRAFT", "ACTIVE", "PAUSED", "ARCHIVED"}


class EmailError(ValueError):
    """Invalid email operation (bad status, suppressed email)."""


class EmailNurtureEngine:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._repo = RepoFactory(db)

    # ---- sequences ---------------------------------------------------------
    def create_sequence(
        self,
        name: str,
        trigger_event: str,
        description: str | None = None,
        steps: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a new email sequence."""
        name = name.strip()
        if not name:
            raise EmailError("name is required")
        if trigger_event not in TRIGGER_EVENTS:
            raise EmailError(f"unknown trigger_event {trigger_event!r}")

        seq_id = self._repo.email.create_sequence(
            name=name,
            trigger_event=trigger_event,
            description=description,
            steps=steps,
        )

        return self.get_sequence(seq_id)

    def get_sequence(self, sequence_id: str) -> dict[str, Any]:
        """Get a sequence by ID."""
        item = self._repo.email.get_sequence(sequence_id)
        if item is None:
            raise NotFoundError(f"email sequence {sequence_id}")
        return item

    def list_sequences(self, status: str | None = None) -> list[dict[str, Any]]:
        """List sequences with optional status filter."""
        return self._repo.email.list_sequences(status=status)

    def activate_sequence(self, sequence_id: str) -> dict[str, Any]:
        """Activate a DRAFT sequence."""
        item = self.get_sequence(sequence_id)
        if item["status"] != "DRAFT":
            raise EmailError(f"cannot activate sequence in status {item['status']}")
        self._repo.email.update_sequence_status(sequence_id, "ACTIVE")
        return self.get_sequence(sequence_id)

    def pause_sequence(self, sequence_id: str) -> dict[str, Any]:
        """Pause an ACTIVE sequence."""
        item = self.get_sequence(sequence_id)
        if item["status"] != "ACTIVE":
            raise EmailError(f"cannot pause sequence in status {item['status']}")
        self._repo.email.update_sequence_status(sequence_id, "PAUSED")
        return self.get_sequence(sequence_id)

    # ---- enrollments -------------------------------------------------------
    def enroll_lead(self, sequence_id: str, lead_id: str) -> dict[str, Any]:
        """Enroll a lead in a sequence."""
        sequence = self.get_sequence(sequence_id)
        if sequence["status"] != "ACTIVE":
            raise EmailError(f"cannot enroll in {sequence['status']} sequence")

        # Check lead exists
        lead = self._repo.leads.get(lead_id)
        if lead is None:
            raise NotFoundError(f"lead {lead_id}")

        # Check suppression list
        if self._repo.email.is_suppressed(lead["email"]):
            raise EmailError(f"email {lead['email']} is suppressed")

        # Check for existing enrollment
        existing = self._repo.email.list_enrollments(
            sequence_id=sequence_id, lead_id=lead_id
        )
        active_existing = [e for e in existing if e["status"] == "ACTIVE"]
        if active_existing:
            raise EmailError(f"lead {lead_id} already enrolled in sequence {sequence_id}")

        enrollment_id = self._repo.email.enroll_lead(sequence_id, lead_id)

        try:
            SqliteEventBus(self._db).publish(
                "email.enrolled",
                {"enrollment_id": enrollment_id, "sequence_id": sequence_id, "lead_id": lead_id},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass

        return self.get_enrollment(enrollment_id)

    def get_enrollment(self, enrollment_id: str) -> dict[str, Any]:
        """Get an enrollment by ID."""
        rows = self._repo.email.list_enrollments()
        for row in rows:
            if row["id"] == enrollment_id:
                return row
        raise NotFoundError(f"enrollment {enrollment_id}")

    def list_enrollments(
        self, sequence_id: str | None = None, lead_id: str | None = None
    ) -> list[dict[str, Any]]:
        """List enrollments with optional filters."""
        return self._repo.email.list_enrollments(
            sequence_id=sequence_id, lead_id=lead_id
        )

    def advance_enrollment(self, enrollment_id: str) -> dict[str, Any]:
        """Advance an enrollment to the next step."""
        enrollment = self.get_enrollment(enrollment_id)
        if enrollment["status"] != "ACTIVE":
            raise EmailError(f"cannot advance {enrollment['status']} enrollment")

        sequence = self.get_sequence(enrollment["sequence_id"])
        steps = sequence.get("steps") or []
        current_step = enrollment.get("current_step") or 0

        if current_step >= len(steps) - 1:
            # Sequence complete
            self._repo.email.complete_enrollment(enrollment_id)
            return self.get_enrollment(enrollment_id)

        # Advance to next step
        self._repo.email.update_enrollment_step(enrollment_id, current_step + 1)
        return self.get_enrollment(enrollment_id)

    # ---- suppression -------------------------------------------------------
    def suppress_email(self, email: str, reason: str = "unsubscribed", source: str | None = None) -> dict[str, Any]:
        """Add an email to the suppression list."""
        suppression_id = self._repo.email.add_to_suppression(email, reason, source)

        try:
            SqliteEventBus(self._db).publish(
                "email.suppressed",
                {"email": email, "reason": reason},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass

        return {"id": suppression_id, "email": email.lower(), "reason": reason}

    def is_suppressed(self, email: str) -> bool:
        """Check if an email is suppressed."""
        return self._repo.email.is_suppressed(email)

    def list_suppressions(self) -> list[dict[str, Any]]:
        """List all suppressed emails."""
        return self._repo.email.list_suppressions()

    # ---- analytics ---------------------------------------------------------
    def sequence_analytics(self, sequence_id: str) -> dict[str, Any]:
        """Get analytics for a sequence."""
        sequence = self.get_sequence(sequence_id)
        enrollments = self.list_enrollments(sequence_id=sequence_id)

        total = len(enrollments)
        active = sum(1 for e in enrollments if e["status"] == "ACTIVE")
        completed = sum(1 for e in enrollments if e["status"] == "COMPLETED")

        return {
            "sequence_id": sequence_id,
            "name": sequence["name"],
            "total_enrollments": total,
            "active": active,
            "completed": completed,
            "completion_rate": round(completed / total * 100, 1) if total else 0,
        }
