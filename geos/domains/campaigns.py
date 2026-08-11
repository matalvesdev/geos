"""Campaigns Engine (SPEC-040): coordinated growth campaigns.

Campaigns orchestrate content, social, blog, and experiments toward a specific
growth goal. Each campaign has a hypothesis, target audience, timeline, budget,
and measurable KPIs. Lifecycle: PLANNED → ACTIVE → PAUSED → COMPLETED / CANCELLED.

Every campaign links to content items, social posts, and optionally experiments.
Metrics are tracked per-campaign for measurement and learning.
"""

from __future__ import annotations

from typing import Any

from ..core.events import SqliteEventBus
from ..storage.database import Database
from ..storage.repos import NotFoundError, RepoFactory
from ..util import new_id, now_iso, slugify

# Deterministic campaign statuses (lifecycle).
CAMPAIGN_STATUSES: dict[str, set[str]] = {
    "PLANNED": {"ACTIVE", "CANCELLED"},
    "ACTIVE": {"PAUSED", "COMPLETED", "CANCELLED"},
    "PAUSED": {"ACTIVE", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}

# Campaign types
CAMPAIGN_TYPES = (
    "content_distribution",
    "lead_generation",
    "brand_awareness",
    "product_launch",
    "community_building",
    "education",
    "retention",
    "event",
)


class CampaignError(ValueError):
    """Invalid campaign operation (bad status, missing required field)."""


class CampaignEngine:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._repo = RepoFactory(db)

    # ---- lifecycle ---------------------------------------------------------
    def create(
        self,
        name: str,
        campaign_type: str = "content_distribution",
        hypothesis: str | None = None,
        objective: str | None = None,
        audience: str | None = None,
        budget: float | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        target_metrics: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new campaign (PLANNED status)."""
        name = name.strip()
        if not name:
            raise CampaignError("name is required")
        if campaign_type not in CAMPAIGN_TYPES:
            raise CampaignError(f"unknown campaign_type {campaign_type!r}")

        slug = _unique_slug(self._repo.campaigns, slugify(name))
        campaign_id = self._repo.campaigns.create(
            name=name,
            slug=slug,
            campaign_type=campaign_type,
            hypothesis=hypothesis,
            objective=objective,
            audience=audience,
            budget=budget,
            start_date=start_date,
            end_date=end_date,
            target_metrics=target_metrics or {},
            tags=tags or [],
        )

        try:
            SqliteEventBus(self._db).publish(
                "campaign.created",
                {"campaign_id": campaign_id, "name": name, "type": campaign_type},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001 - telemetry must not fail creation
            pass

        return self.get(campaign_id)

    def get(self, campaign_id: str) -> dict[str, Any]:
        """Get a campaign by ID."""
        item = self._repo.campaigns.get(campaign_id)
        if item is None:
            raise NotFoundError(f"campaign {campaign_id}")
        return item

    def list(
        self,
        status: str | None = None,
        campaign_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List campaigns with optional filters."""
        return self._repo.campaigns.list(
            status=status, campaign_type=campaign_type, limit=limit
        )

    # ---- lifecycle transitions ---------------------------------------------
    def transition(self, campaign_id: str, target: str) -> dict[str, Any]:
        """Transition campaign to a new status."""
        item = self.get(campaign_id)
        target = target.upper()
        allowed = CAMPAIGN_STATUSES.get(item["status"], set())
        if target not in allowed:
            raise CampaignError(
                f"invalid transition {item['status']} → {target} "
                f"(allowed: {sorted(allowed) or 'none'})"
            )

        self._repo.campaigns.update_status(campaign_id, target)

        try:
            SqliteEventBus(self._db).publish(
                "campaign.status_changed",
                {"campaign_id": campaign_id, "from": item["status"], "to": target},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass

        return self.get(campaign_id)

    def activate(self, campaign_id: str) -> dict[str, Any]:
        """Activate a PLANNED campaign."""
        return self.transition(campaign_id, "ACTIVE")

    def pause(self, campaign_id: str) -> dict[str, Any]:
        """Pause an ACTIVE campaign."""
        return self.transition(campaign_id, "PAUSED")

    def complete(self, campaign_id: str, result: str | None = None) -> dict[str, Any]:
        """Complete an ACTIVE/PAUSED campaign."""
        item = self.transition(campaign_id, "COMPLETED")
        if result:
            self._repo.campaigns.update(campaign_id, result=result)
            item = self.get(campaign_id)
        return item

    def cancel(self, campaign_id: str, reason: str | None = None) -> dict[str, Any]:
        """Cancel a campaign."""
        item = self.transition(campaign_id, "CANCELLED")
        if reason:
            self._repo.campaigns.update(campaign_id, cancel_reason=reason)
            item = self.get(campaign_id)
        return item

    # ---- content linking ---------------------------------------------------
    def add_content(self, campaign_id: str, content_id: str) -> dict[str, Any]:
        """Link a content item to a campaign."""
        self.get(campaign_id)  # validate exists
        self._repo.content.get(content_id)  # validate exists
        self._repo.campaigns.add_content(campaign_id, content_id)
        return self.get(campaign_id)

    def remove_content(self, campaign_id: str, content_id: str) -> dict[str, Any]:
        """Unlink a content item from a campaign."""
        self.get(campaign_id)  # validate exists
        self._repo.campaigns.remove_content(campaign_id, content_id)
        return self.get(campaign_id)

    def list_content(self, campaign_id: str) -> list[dict[str, Any]]:
        """List all content items linked to a campaign."""
        self.get(campaign_id)  # validate exists
        return self._repo.campaigns.list_content(campaign_id)

    # ---- social linking ----------------------------------------------------
    def add_social_post(self, campaign_id: str, post_id: str) -> dict[str, Any]:
        """Link a social post to a campaign."""
        self.get(campaign_id)  # validate exists
        self._repo.social.get(post_id)  # validate exists
        self._repo.campaigns.add_social_post(campaign_id, post_id)
        return self.get(campaign_id)

    def remove_social_post(self, campaign_id: str, post_id: str) -> dict[str, Any]:
        """Unlink a social post from a campaign."""
        self.get(campaign_id)  # validate exists
        self._repo.campaigns.remove_social_post(campaign_id, post_id)
        return self.get(campaign_id)

    def list_social_posts(self, campaign_id: str) -> list[dict[str, Any]]:
        """List all social posts linked to a campaign."""
        self.get(campaign_id)  # validate exists
        return self._repo.campaigns.list_social_posts(campaign_id)

    # ---- experiment linking ------------------------------------------------
    def add_experiment(self, campaign_id: str, experiment_id: str) -> dict[str, Any]:
        """Link an experiment to a campaign."""
        self.get(campaign_id)  # validate exists
        self._repo.experiments.get(experiment_id)  # validate exists
        self._repo.campaigns.add_experiment(campaign_id, experiment_id)
        return self.get(campaign_id)

    def remove_experiment(self, campaign_id: str, experiment_id: str) -> dict[str, Any]:
        """Unlink an experiment from a campaign."""
        self.get(campaign_id)  # validate exists
        self._repo.campaigns.remove_experiment(campaign_id, experiment_id)
        return self.get(campaign_id)

    def list_experiments(self, campaign_id: str) -> list[dict[str, Any]]:
        """List all experiments linked to a campaign."""
        self.get(campaign_id)  # validate exists
        return self._repo.campaigns.list_experiments(campaign_id)

    # ---- metrics tracking --------------------------------------------------
    def record_metric(
        self,
        campaign_id: str,
        metric_name: str,
        value: float,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Record a metric value for a campaign."""
        self.get(campaign_id)  # validate exists
        self._repo.campaigns.record_metric(
            campaign_id=campaign_id,
            metric_name=metric_name,
            value=value,
            source=source,
        )
        return self.get(campaign_id)

    def get_metrics(self, campaign_id: str) -> dict[str, Any]:
        """Get all metrics for a campaign."""
        self.get(campaign_id)  # validate exists
        return self._repo.campaigns.get_metrics(campaign_id)

    def get_metric_summary(self, campaign_id: str) -> dict[str, Any]:
        """Get a summary of campaign metrics vs targets."""
        item = self.get(campaign_id)
        metrics = self.get_metrics(campaign_id)
        target_metrics = item.get("target_metrics") or {}

        summary: dict[str, Any] = {
            "campaign_id": campaign_id,
            "status": item["status"],
            "metrics": {},
        }

        for metric_name, target_value in target_metrics.items():
            current = metrics.get(metric_name, {}).get("latest", 0)
            summary["metrics"][metric_name] = {
                "current": current,
                "target": target_value,
                "progress": round(current / target_value * 100, 1) if target_value else 0,
            }

        return summary

    # ---- budget tracking ---------------------------------------------------
    def record_spend(
        self, campaign_id: str, amount: float, description: str | None = None
    ) -> dict[str, Any]:
        """Record a spend against the campaign budget."""
        item = self.get(campaign_id)
        budget = item.get("budget") or 0
        current_spend = item.get("total_spend") or 0

        if budget and current_spend + amount > budget:
            raise CampaignError(
                f" spend ({current_spend + amount}) would exceed budget ({budget})"
            )

        self._repo.campaigns.record_spend(campaign_id, amount, description)
        return self.get(campaign_id)

    def get_budget_status(self, campaign_id: str) -> dict[str, Any]:
        """Get budget status for a campaign."""
        item = self.get(campaign_id)
        budget = item.get("budget") or 0
        total_spend = item.get("total_spend") or 0

        return {
            "campaign_id": campaign_id,
            "budget": budget,
            "total_spend": total_spend,
            "remaining": budget - total_spend if budget else None,
            "utilization": round(total_spend / budget * 100, 1) if budget else 0,
        }

    # ---- summary / stats ---------------------------------------------------
    def summary(self, campaign_id: str) -> dict[str, Any]:
        """Get a comprehensive campaign summary."""
        item = self.get(campaign_id)
        content_count = len(self.list_content(campaign_id))
        social_count = len(self.list_social_posts(campaign_id))
        experiment_count = len(self.list_experiments(campaign_id))
        metrics = self.get_metrics(campaign_id)
        budget_status = self.get_budget_status(campaign_id)

        return {
            "campaign": item,
            "content_count": content_count,
            "social_posts_count": social_count,
            "experiments_count": experiment_count,
            "metrics_count": len(metrics),
            "budget": budget_status,
        }


def _unique_slug(repo, base: str) -> str:
    """Generate a unique slug for a campaign."""
    candidate = base or "untitled"
    if repo.by_slug(candidate) is None:
        return candidate
    return f"{candidate}-{new_id()[:6]}"
