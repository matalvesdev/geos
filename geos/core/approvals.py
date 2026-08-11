"""Approval engine (SPEC-019 DDL now, engine minimal). Human-in-the-loop (spec §46–§47)."""

from __future__ import annotations

from typing import Any

from ..storage.database import Database
from ..storage.repos import Approval, ApprovalRepository, NotFoundError
from .policies import RiskLevel, classify_action


class ApprovalEngine:
    def __init__(self, db: Database, config_overrides: dict[str, str] | None = None) -> None:
        self._repo = ApprovalRepository(db)
        self._overrides = config_overrides or {}

    def request(self, action: str, agent: str | None = None,
                metadata: dict[str, Any] | None = None) -> Approval:
        risk = classify_action(action, self._overrides).value
        return self._repo.request(action=action, agent=agent, risk=risk, metadata=metadata)

    def decide(self, approval_id: str, decision: str, decided_by: str) -> Approval:
        if decision.lower() not in ("approve", "reject"):
            raise ValueError("decision must be 'approve' or 'reject'")
        return self._repo.decide(approval_id, decision, decided_by)

    def pending(self, limit: int = 100) -> list[Approval]:
        return self._repo.list_pending(limit=limit)

    def risk_of(self, action: str) -> RiskLevel:
        return classify_action(action, self._overrides)

    def get(self, approval_id: str) -> Approval | None:
        return self._repo.get(approval_id)
