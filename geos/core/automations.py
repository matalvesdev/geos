"""Automation registry (SPEC-006 wiring): persisted schedules + job handlers.

Schedules live in `.geos/automations.json` (like the repository registry) so a
`geos automations worker` process can reconstruct them and enqueue due jobs.
Handlers execute internal automations: social.worker (L3 — only pre-approved
posts), analytics.collect, opportunities.collect and seo.audit. External
actions remain approval-gated; nothing here ever decides an approval.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..storage.database import Database
from .jobs import SqliteJobQueue, Worker
from .scheduler import Schedule


@dataclass
class AutomationEntry:
    id: str
    kind: str
    cron: str
    payload: dict[str, Any] = field(default_factory=dict)
    max_attempts: int = 3
    next_run: str | None = None  # persisted so cron fires across invocations

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class AutomationRegistry:
    """JSON-backed schedule registry at .geos/automations.json."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._entries: dict[str, AutomationEntry] = {}
        if self.path.is_file():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                for item in data.get("automations", []):
                    entry = AutomationEntry(**item)
                    self._entries[entry.id] = entry
            except (json.JSONDecodeError, TypeError, ValueError):
                self._entries = {}

    def add(self, entry: AutomationEntry) -> AutomationEntry:
        self._entries[entry.id] = entry
        self._save()
        return entry

    def get(self, automation_id: str) -> AutomationEntry | None:
        return self._entries.get(automation_id)

    def list(self) -> list[AutomationEntry]:
        return list(self._entries.values())

    def remove(self, automation_id: str) -> bool:
        removed = self._entries.pop(automation_id, None) is not None
        if removed:
            self._save()
        return removed

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"automations": [e.to_dict() for e in self._entries.values()]}
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def register_internal_handlers(worker: Worker, db: Database,
                               approvals: dict[str, str] | None = None) -> None:
    """Register the internal automation job handlers on a Worker (SPEC-006)."""

    def social_worker(payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, int]:
        from ..domains.social import SocialEngine

        return SocialEngine(db, approvals=approvals).worker()

    def analytics_collect(payload: dict[str, Any],
                          ctx: dict[str, Any]) -> dict[str, Any]:
        from ..domains.analytics import AnalyticsEngine

        return AnalyticsEngine(db).collect()

    def opportunities_collect(payload: dict[str, Any],
                              ctx: dict[str, Any]) -> dict[str, int]:
        from ..domains.growth import OpportunityEngine

        return OpportunityEngine(db).collect()

    def seo_audit(payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        from ..domains.seo import SeoEngine

        scopes = tuple(payload.get("scopes") or ("docs", "content"))
        return SeoEngine(db).run_audit(scopes=scopes)

    worker.register("social.worker", social_worker)
    worker.register("analytics.collect", analytics_collect)
    worker.register("opportunities.collect", opportunities_collect)
    worker.register("seo.audit", seo_audit)


def run_automations(registry: AutomationRegistry, db: Database,
                    approvals: dict[str, str] | None = None) -> tuple[int, int]:
    """Enqueue due schedules and process them. Returns (enqueued, processed).

    `next_run` is persisted on each entry, so cron jobs fire across separate
    `geos automations run` invocations (not just within one long-lived process).
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    enqueued = 0
    queue = SqliteJobQueue(db)
    for entry in registry.list():
        schedule = Schedule.from_dict({"kind": "cron", "cron": entry.cron},
                                      schedule_id=entry.id)
        if entry.next_run is None:
            # First registration: persist the first occurrence (cron must not
            # fire on registration) so later invocations can detect it's due.
            entry.next_run = schedule.next_after(now).isoformat()
            registry.add(entry)
            continue
        due_at = _parse_dt(entry.next_run)
        if due_at is None or due_at > now:
            continue
        queue.enqueue(
            entry.kind, entry.payload,
            idempotency_key=f"auto:{entry.id}:{due_at.isoformat()}",
            max_attempts=entry.max_attempts,
        )
        entry.next_run = schedule.next_after(now).isoformat()
        registry.add(entry)  # persists the advanced next_run
        enqueued += 1
    worker = Worker(SqliteJobQueue(db))
    register_internal_handlers(worker, db, approvals=approvals)
    processed = worker.run_until_idle()
    return enqueued, processed


def _parse_dt(value: str | None):
    if not value:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def default_automations() -> list[AutomationEntry]:
    """The bootstrap defaults (idempotent by id; safe to register repeatedly)."""
    return [
        AutomationEntry(id="daily-intelligence", kind="workflow.run",
                        cron="0 7 * * *",
                        payload={"workflow_id": "daily-intelligence"}),
        AutomationEntry(id="social-worker", kind="social.worker",
                        cron="*/30 * * * *"),
        AutomationEntry(id="analytics-collect", kind="analytics.collect",
                        cron="5 0 * * *"),
        AutomationEntry(id="opportunities-collect", kind="opportunities.collect",
                        cron="10 0 * * *"),
        AutomationEntry(id="seo-audit", kind="seo.audit",
                        cron="15 0 * * 1",
                        payload={"scopes": ["docs", "content"]}),
    ]


def register_default_automations(registry: AutomationRegistry) -> list[str]:
    added: list[str] = []
    for entry in default_automations():
        if registry.get(entry.id) is None:
            registry.add(entry)
            added.append(entry.id)
    return added
