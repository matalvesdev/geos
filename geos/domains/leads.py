"""Lead Intelligence Engine (SPEC-026/027/028): lead lifecycle management.

Leads flow through: CAPTURED → QUALIFIED → ENGAGED → MEETING_SCHEDULED →
OPPORTUNITY_CREATED → WON / LOST.

Scoring is deterministic and explainable (SPEC-027): FIT (demographic fit),
INTENT (behavioral signals), ENGAGEMENT (interaction depth), RELATIONSHIP
(strength of connection). Each component has breakdown + confidence.

Qualification (SPEC-028) uses BANT (Budget, Authority, Need, Timeline)
methodology with status transitions and validation.
"""

from __future__ import annotations

from typing import Any

from ..core.events import SqliteEventBus
from ..storage.database import Database
from ..storage.repos import NotFoundError, RepoFactory
from ..util import new_id, now_iso, slugify

# Deterministic lead statuses (lifecycle).
LEAD_STATUSES: dict[str, set[str]] = {
    "CAPTURED": {"QUALIFIED", "DISQUALIFIED", "ARCHIVED"},
    "QUALIFIED": {"ENGAGED", "DISQUALIFIED", "ARCHIVED"},
    "ENGAGED": {"MEETING_SCHEDULED", "QUALIFIED", "DISQUALIFIED", "ARCHIVED"},
    "MEETING_SCHEDULED": {"OPPORTUNITY_CREATED", "ENGAGED", "DISQUALIFIED", "ARCHIVED"},
    "OPPORTUNITY_CREATED": {"WON", "LOST", "ARCHIVED"},
    "WON": set(),
    "LOST": set(),
    "DISQUALIFIED": set(),
    "ARCHIVED": set(),
}

# Lead sources
LEAD_SOURCES = (
    "website", "content_download", "webinar", "demo_request",
    "referral", "social_media", "event", "cold_outreach",
    "inbound_email", "partner", "manual", "research",
)

# Qualification methodologies
QUALIFICATION_METHODS = ("BANT", "MEDDIC", "GPCTBA", "CHAMP", "ANTICIPATE")

# Disqualification reasons
DISQUALIFICATION_REASONS = (
    "no_budget", "no_authority", "no_need", "bad_timing",
    "competitor_selected", "not_ideal_fit", "unresponsive", "other",
)


class LeadError(ValueError):
    """Invalid lead operation (bad transition, missing required field)."""


class LeadEngine:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._repo = RepoFactory(db)

    # ---- lifecycle ---------------------------------------------------------
    def capture(
        self,
        email: str,
        name: str | None = None,
        company: str | None = None,
        source: str = "manual",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Capture a new lead (CAPTURED status)."""
        email = email.strip().lower()
        if not email:
            raise LeadError("email is required")
        if source not in LEAD_SOURCES:
            raise LeadError(f"unknown source {source!r}")

        # Check for existing lead with same email
        existing = self._repo.leads.by_email(email)
        if existing is not None:
            raise LeadError(f"lead with email {email} already exists ({existing['id']})")

        lead_id = self._repo.leads.create(
            email=email,
            name=name,
            company=company,
            source=source,
            tags=tags or [],
            metadata=metadata or {},
        )

        try:
            SqliteEventBus(self._db).publish(
                "lead.captured",
                {"lead_id": lead_id, "email": email, "source": source},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass

        return self.get(lead_id)

    def get(self, lead_id: str) -> dict[str, Any]:
        """Get a lead by ID."""
        item = self._repo.leads.get(lead_id)
        if item is None:
            raise NotFoundError(f"lead {lead_id}")
        return item

    def list(
        self,
        status: str | None = None,
        source: str | None = None,
        company: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List leads with optional filters."""
        return self._repo.leads.list(
            status=status, source=source, company=company, limit=limit
        )

    def by_email(self, email: str) -> dict[str, Any] | None:
        """Get a lead by email."""
        return self._repo.leads.by_email(email)

    # ---- lifecycle transitions ---------------------------------------------
    def transition(self, lead_id: str, target: str) -> dict[str, Any]:
        """Transition lead to a new status."""
        item = self.get(lead_id)
        target = target.upper()
        allowed = LEAD_STATUSES.get(item["status"], set())
        if target not in allowed:
            raise LeadError(
                f"invalid transition {item['status']} → {target} "
                f"(allowed: {sorted(allowed) or 'none'})"
            )

        self._repo.leads.update_status(lead_id, target)

        try:
            SqliteEventBus(self._db).publish(
                "lead.status_changed",
                {"lead_id": lead_id, "from": item["status"], "to": target},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass

        return self.get(lead_id)

    def qualify(self, lead_id: str, method: str = "BANT", **criteria: Any) -> dict[str, Any]:
        """Qualify a lead using specified methodology."""
        item = self.get(lead_id)
        if item["status"] not in ("CAPTURED", "QUALIFIED"):
            raise LeadError(f"cannot qualify lead in status {item['status']}")

        if method not in QUALIFICATION_METHODS:
            raise LeadError(f"unknown qualification method {method!r}")

        # Store qualification criteria
        self._repo.leads.update_qualification(lead_id, method, criteria)

        # Transition to QUALIFIED
        if item["status"] == "CAPTURED":
            self.transition(lead_id, "QUALIFIED")

        return self.get(lead_id)

    def disqualify(self, lead_id: str, reason: str = "other", notes: str | None = None) -> dict[str, Any]:
        """Disqualify a lead."""
        item = self.get(lead_id)
        if item["status"] in ("WON", "LOST", "DISQUALIFIED", "ARCHIVED"):
            raise LeadError(f"cannot disqualify lead in status {item['status']}")

        self._repo.leads.disqualify(lead_id, reason, notes)
        self._repo.leads.update_status(lead_id, "DISQUALIFIED")

        try:
            SqliteEventBus(self._db).publish(
                "lead.disqualified",
                {"lead_id": lead_id, "reason": reason},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass

        return self.get(lead_id)

    # ---- scoring (SPEC-027: deterministic, explainable) --------------------
    def score(self, lead_id: str) -> dict[str, Any]:
        """Compute deterministic lead score with breakdown."""
        item = self.get(lead_id)

        # Compute components
        fit_score = self._compute_fit(item)
        intent_score = self._compute_intent(item)
        engagement_score = self._compute_engagement(item)
        relationship_score = self._compute_relationship(item)

        components = {
            "fit": fit_score,
            "intent": intent_score,
            "engagement": engagement_score,
            "relationship": relationship_score,
        }

        # Weighted composite (deterministic)
        weights = {"fit": 0.3, "intent": 0.3, "engagement": 0.25, "relationship": 0.15}
        composite = sum(components[k] * weights[k] for k in components)

        breakdown = {
            "method": "weighted_average",
            "formula": "Score = Fit×0.3 + Intent×0.3 + Engagement×0.25 + Relationship×0.15",
            "components": components,
            "weights": weights,
            "score": round(composite, 4),
            "confidence": self._compute_confidence(item),
        }

        self._repo.leads.update_score(lead_id, composite, breakdown)
        return {"score": round(composite, 4), "breakdown": breakdown}

    def _compute_fit(self, item: dict[str, Any]) -> float:
        """Compute FIT score (demographic fit)."""
        score = 0.5  # neutral default
        company = item.get("company") or ""
        if company:
            score += 0.2  # has company
        tags = item.get("tags") or []
        if "ideal_customer" in tags:
            score += 0.3
        return min(1.0, score)

    def _compute_intent(self, item: dict[str, Any]) -> float:
        """Compute INTENT score (behavioral signals)."""
        score = 0.3  # base
        source = item.get("source") or ""
        high_intent_sources = {"demo_request", "webinar", "content_download"}
        if source in high_intent_sources:
            score += 0.4
        elif source in {"website", "inbound_email"}:
            score += 0.2
        return min(1.0, score)

    def _compute_engagement(self, item: dict[str, Any]) -> float:
        """Compute ENGAGEMENT score (interaction depth)."""
        interactions = item.get("interaction_count") or 0
        return min(1.0, 0.2 + (interactions * 0.1))

    def _compute_relationship(self, item: dict[str, Any]) -> float:
        """Compute RELATIONSHIP score (connection strength)."""
        score = 0.3  # base
        if item.get("owner_id"):
            score += 0.3  # assigned to someone
        referrals = item.get("referral_count") or 0
        score += min(0.4, referrals * 0.2)
        return min(1.0, score)

    def _compute_confidence(self, item: dict[str, Any]) -> float:
        """Compute confidence in the score."""
        has_company = bool(item.get("company"))
        has_source = bool(item.get("source"))
        interactions = item.get("interaction_count") or 0

        confidence = 0.3
        if has_company:
            confidence += 0.2
        if has_source:
            confidence += 0.2
        if interactions > 0:
            confidence += 0.2
        return min(0.9, confidence)

    # ---- interactions ------------------------------------------------------
    def record_interaction(
        self,
        lead_id: str,
        interaction_type: str,
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record an interaction with a lead."""
        self.get(lead_id)  # validate exists
        self._repo.leads.record_interaction(
            lead_id=lead_id,
            interaction_type=interaction_type,
            summary=summary,
            metadata=metadata,
        )

        # Increment interaction count
        self._repo.leads.increment_interactions(lead_id)

        try:
            SqliteEventBus(self._db).publish(
                "lead.interaction",
                {"lead_id": lead_id, "type": interaction_type},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass

        return self.get(lead_id)

    def list_interactions(self, lead_id: str) -> list[dict[str, Any]]:
        """List all interactions for a lead."""
        self.get(lead_id)  # validate exists
        return self._repo.leads.list_interactions(lead_id)

    # ---- summary -----------------------------------------------------------
    def summary(self, lead_id: str) -> dict[str, Any]:
        """Get comprehensive lead summary."""
        item = self.get(lead_id)
        interactions = self.list_interactions(lead_id)
        score_result = self.score(lead_id)

        return {
            "lead": item,
            "interaction_count": len(interactions),
            "score": score_result["score"],
            "score_breakdown": score_result["breakdown"],
        }
