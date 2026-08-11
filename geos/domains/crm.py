"""CRM Engine (SPEC-029): deal pipeline and activity management.

Deals flow through configurable stages: PROSPECTING → QUALIFICATION → PROPOSAL →
NEGOTIATION → CLOSED_WON / CLOSED_LOST. Each stage has probability and ordering.

Activities track interactions with deals and leads (calls, emails, meetings, tasks).
The CRM uses SQLite as internal fallback; HubSpot/Salesforce/Pipedrive adapters
are planned for future phases behind the same protocol.
"""

from __future__ import annotations

from typing import Any

from ..core.events import SqliteEventBus
from ..storage.database import Database
from ..storage.repos import NotFoundError, RepoFactory
from ..util import new_id, now_iso

# Default pipeline stages
DEFAULT_STAGES = [
    {"name": "PROSPECTING", "order": 1, "probability": 0.1, "is_won": False, "is_lost": False},
    {"name": "QUALIFICATION", "order": 2, "probability": 0.2, "is_won": False, "is_lost": False},
    {"name": "PROPOSAL", "order": 3, "probability": 0.4, "is_won": False, "is_lost": False},
    {"name": "NEGOTIATION", "order": 4, "probability": 0.6, "is_won": False, "is_lost": False},
    {"name": "CONTRACT", "order": 5, "probability": 0.8, "is_won": False, "is_lost": False},
    {"name": "CLOSED_WON", "order": 6, "probability": 1.0, "is_won": True, "is_lost": False},
    {"name": "CLOSED_LOST", "order": 7, "probability": 0.0, "is_won": False, "is_lost": True},
]

# Deal statuses
DEAL_STATUSES = {"OPEN", "WON", "LOST", "ARCHIVED"}

# Activity types
ACTIVITY_TYPES = (
    "call", "email", "meeting", "task", "note", "demo", "follow_up",
)

# Stage transitions (valid moves)
STAGE_TRANSITIONS: dict[str, set[str]] = {
    "PROSPECTING": {"QUALIFICATION", "CLOSED_LOST"},
    "QUALIFICATION": {"PROSPECTING", "PROPOSAL", "CLOSED_LOST"},
    "PROPOSAL": {"QUALIFICATION", "NEGOTIATION", "CLOSED_LOST"},
    "NEGOTIATION": {"PROPOSAL", "CONTRACT", "CLOSED_LOST"},
    "CONTRACT": {"NEGOTIATION", "CLOSED_WON", "CLOSED_LOST"},
    "CLOSED_WON": set(),
    "CLOSED_LOST": set(),
}


class CRMError(ValueError):
    """Invalid CRM operation (bad transition, missing required field)."""


class CRMEngine:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._repo = RepoFactory(db)

    # ---- pipeline setup ----------------------------------------------------
    def ensure_default_pipeline(self) -> None:
        """Ensure default pipeline stages exist."""
        existing = self._repo.crm.list_stages()
        if not existing:
            for stage in DEFAULT_STAGES:
                self._repo.crm.create_stage(**stage)

    # ---- deal lifecycle ----------------------------------------------------
    def create_deal(
        self,
        name: str,
        lead_id: str | None = None,
        value: float | None = None,
        currency: str = "BRL",
        expected_close_date: str | None = None,
        owner_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new deal in PROSPECTING stage."""
        name = name.strip()
        if not name:
            raise CRMError("name is required")

        # Validate lead exists if provided
        if lead_id:
            self._repo.leads.get(lead_id)  # raises NotFoundError if missing

        self.ensure_default_pipeline()

        deal_id = self._repo.crm.create_deal(
            name=name,
            lead_id=lead_id,
            value=value,
            currency=currency,
            expected_close_date=expected_close_date,
            owner_id=owner_id,
            tags=tags or [],
            metadata=metadata or {},
        )

        try:
            SqliteEventBus(self._db).publish(
                "deal.created",
                {"deal_id": deal_id, "name": name, "lead_id": lead_id},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass

        return self.get_deal(deal_id)

    def get_deal(self, deal_id: str) -> dict[str, Any]:
        """Get a deal by ID."""
        item = self._repo.crm.get_deal(deal_id)
        if item is None:
            raise NotFoundError(f"deal {deal_id}")
        return item

    def list_deals(
        self,
        status: str | None = None,
        stage: str | None = None,
        owner_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List deals with optional filters."""
        return self._repo.crm.list_deals(
            status=status, stage=stage, owner_id=owner_id, limit=limit
        )

    def transition_deal(self, deal_id: str, target_stage: str) -> dict[str, Any]:
        """Transition deal to a new stage."""
        item = self.get_deal(deal_id)
        current_stage = item["stage"]
        target_stage = target_stage.upper()

        allowed = STAGE_TRANSITIONS.get(current_stage, set())
        if target_stage not in allowed:
            raise CRMError(
                f"invalid stage transition {current_stage} → {target_stage} "
                f"(allowed: {sorted(allowed) or 'none'})"
            )

        # Get probability from stage
        stages = self._repo.crm.list_stages()
        stage_info = next((s for s in stages if s["name"] == target_stage), None)
        probability = stage_info["probability"] if stage_info else 0

        self._repo.crm.update_deal_stage(deal_id, target_stage, probability)

        # Check if terminal
        if stage_info and (stage_info.get("is_won") or stage_info.get("is_lost")):
            status = "WON" if stage_info["is_won"] else "LOST"
            self._repo.crm.update_deal_status(deal_id, status)

        try:
            SqliteEventBus(self._db).publish(
                "deal.stage_changed",
                {"deal_id": deal_id, "from": current_stage, "to": target_stage},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass

        return self.get_deal(deal_id)

    def update_deal(self, deal_id: str, **fields: Any) -> dict[str, Any]:
        """Update deal fields."""
        self.get_deal(deal_id)  # validate exists
        self._repo.crm.update_deal(deal_id, **fields)
        return self.get_deal(deal_id)

    # ---- activities --------------------------------------------------------
    def create_activity(
        self,
        activity_type: str,
        deal_id: str | None = None,
        lead_id: str | None = None,
        subject: str | None = None,
        description: str | None = None,
        due_date: str | None = None,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        """Create an activity."""
        if activity_type not in ACTIVITY_TYPES:
            raise CRMError(f"unknown activity_type {activity_type!r}")

        if deal_id:
            self.get_deal(deal_id)  # validate exists
        if lead_id:
            self._repo.leads.get(lead_id)  # validate exists

        activity_id = self._repo.crm.create_activity(
            activity_type=activity_type,
            deal_id=deal_id,
            lead_id=lead_id,
            subject=subject,
            description=description,
            due_date=due_date,
            owner_id=owner_id,
        )

        return self.get_activity(activity_id)

    def get_activity(self, activity_id: str) -> dict[str, Any]:
        """Get an activity by ID."""
        item = self._repo.crm.get_activity(activity_id)
        if item is None:
            raise NotFoundError(f"activity {activity_id}")
        return item

    def list_activities(
        self,
        deal_id: str | None = None,
        lead_id: str | None = None,
        activity_type: str | None = None,
        completed: bool | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List activities with optional filters."""
        return self._repo.crm.list_activities(
            deal_id=deal_id, lead_id=lead_id,
            activity_type=activity_type, completed=completed, limit=limit
        )

    def complete_activity(self, activity_id: str, notes: str | None = None) -> dict[str, Any]:
        """Mark an activity as completed."""
        self.get_activity(activity_id)  # validate exists
        self._repo.crm.complete_activity(activity_id, notes)
        return self.get_activity(activity_id)

    # ---- pipeline analytics ------------------------------------------------
    def pipeline_summary(self) -> dict[str, Any]:
        """Get pipeline summary with deals per stage and total value."""
        deals = self.list_deals(status="OPEN")
        stages = self._repo.crm.list_stages()

        pipeline: dict[str, dict[str, Any]] = {}
        total_value = 0
        weighted_value = 0

        for stage in stages:
            pipeline[stage["name"]] = {
                "count": 0,
                "value": 0,
                "weighted_value": 0,
                "probability": stage["probability"],
            }

        for deal in deals:
            stage = deal["stage"]
            value = deal.get("value") or 0
            probability = deal.get("probability") or 0
            if stage in pipeline:
                pipeline[stage]["count"] += 1
                pipeline[stage]["value"] += value
                pipeline[stage]["weighted_value"] += value * probability
            total_value += value
            weighted_value += value * probability

        return {
            "stages": pipeline,
            "total_deals": len(deals),
            "total_value": total_value,
            "weighted_value": weighted_value,
        }

    def deal_summary(self, deal_id: str) -> dict[str, Any]:
        """Get comprehensive deal summary."""
        deal = self.get_deal(deal_id)
        activities = self.list_activities(deal_id=deal_id)

        return {
            "deal": deal,
            "activity_count": len(activities),
            "activities": activities[:10],  # last 10
        }
