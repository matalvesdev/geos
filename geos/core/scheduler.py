"""Scheduler (SPEC-006, ADR-0004). Cron + interval schedules over the job queue.

Deterministic-first: own minimal 5-field cron parser — no third-party dependency.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from ..util import now_iso
from .jobs import JobQueueProtocol

_STEP_LIMIT_MINUTES = 527_040  # 366 days of minute-stepping before giving up


class CronSyntaxError(ValueError):
    """Invalid cron expression (fails fast at definition time)."""


@dataclass(frozen=True)
class CronExpr:
    minute: frozenset[int]
    hour: frozenset[int]
    dom: frozenset[int]
    month: frozenset[int]
    dow: frozenset[int]
    source: str
    _dom_restricted: bool = False
    _dow_restricted: bool = False

    @classmethod
    def parse(cls, expression: str) -> "CronExpr":
        fields = expression.split()
        if len(fields) != 5:
            raise CronSyntaxError(
                f"cron expression {expression!r} must have 5 fields (minute hour dom month dow)"
            )
        minute = _parse_field(fields[0], 0, 59)
        hour = _parse_field(fields[1], 0, 23)
        dom = _parse_field(fields[2], 1, 31)
        month = _parse_field(fields[3], 1, 12)
        dow = _parse_field(fields[4], 0, 7)
        # Normalize: 0 and 7 both mean Sunday.
        dow = frozenset(0 if d == 7 else d for d in dow)
        return cls(
            minute=minute, hour=hour, dom=dom, month=month, dow=dow, source=expression,
            _dom_restricted=fields[2] not in ("*", "?"),
            _dow_restricted=fields[4] not in ("*", "?"),
        )

    def matches(self, dt: datetime) -> bool:
        if dt.minute not in self.minute or dt.hour not in self.hour:
            return False
        if dt.month not in self.month:
            return False
        dom_ok = dt.day in self.dom
        # Sunday is both weekday()==6 and cron dow value 0 (7 normalized to 0).
        dow_value = 0 if dt.weekday() == 6 else dt.weekday() + 1
        dow_ok = dow_value in self.dow
        if self._dom_restricted and self._dow_restricted:
            return dom_ok or dow_ok  # standard cron: OR when both restricted
        return dom_ok and dow_ok

    def next_after(self, now: datetime) -> datetime:
        t = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(_STEP_LIMIT_MINUTES):
            if self.matches(t):
                return t
            t += timedelta(minutes=1)
        raise CronSyntaxError(f"no next occurrence found for {self.source!r} within 366 days")


def _parse_field(raw: str, lo: int, hi: int) -> frozenset[int]:
    values: set[int] = set()
    if raw in ("*", "?"):
        return frozenset(range(lo, hi + 1))
    for part in raw.split(","):
        part = part.strip()
        if not part:
            raise CronSyntaxError(f"empty field part in {raw!r}")
        step = 1
        if "/" in part:
            base, _, step_s = part.partition("/")
            try:
                step = int(step_s)
            except ValueError as exc:
                raise CronSyntaxError(f"invalid step {step_s!r} in {raw!r}") from exc
            if step < 1:
                raise CronSyntaxError(f"step must be >= 1 in {raw!r}")
        else:
            base = part
        if base in ("*", "?"):
            rng_lo, rng_hi = lo, hi
        elif "-" in base:
            a, _, b = base.partition("-")
            try:
                rng_lo, rng_hi = int(a), int(b)
            except ValueError as exc:
                raise CronSyntaxError(f"invalid range {base!r} in {raw!r}") from exc
        else:
            try:
                rng_lo = rng_hi = int(base)
            except ValueError as exc:
                raise CronSyntaxError(f"invalid value {base!r} in {raw!r}") from exc
        if not (lo <= rng_lo <= rng_hi <= hi):
            raise CronSyntaxError(f"value out of range in {raw!r} (expected {lo}-{hi})")
        values.update(range(rng_lo, rng_hi + 1, step))
    return frozenset(values)


@dataclass
class Schedule:
    """Declarative schedule. kind: cron | interval | event | manual | conditional."""

    kind: str
    cron: str | None = None
    seconds: int | None = None
    event_type: str | None = None
    expression: str | None = None
    schedule_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in ("cron", "interval", "event", "manual", "conditional"):
            raise ValueError(f"unknown schedule kind {self.kind!r}")
        if self.kind == "cron" and self.cron is None:
            raise ValueError("cron schedule requires 'cron' expression")

    def next_after(self, now: datetime) -> datetime:
        if self.kind == "cron":
            return CronExpr.parse(self.cron or "").next_after(now)
        if self.kind == "interval":
            if not self.seconds or self.seconds < 1:
                raise ValueError("interval schedule requires seconds >= 1")
            return now + timedelta(seconds=self.seconds)
        raise ValueError(f"kind {self.kind!r} has no time-based next_after")

    @classmethod
    def from_dict(cls, data: dict[str, Any], schedule_id: str | None = None) -> "Schedule":
        kind = str(data.get("kind") or data.get("type") or "manual")
        return cls(
            kind=kind,
            cron=data.get("cron"),
            seconds=int(data["seconds"]) if data.get("seconds") is not None else None,
            event_type=data.get("event"),
            expression=data.get("expression"),
            schedule_id=schedule_id,
        )


@dataclass
class ScheduledJob:
    schedule: Schedule
    kind: str
    payload: dict[str, Any]
    next_run: datetime
    max_attempts: int = 3


class Scheduler:
    """Turns schedules into idempotent jobs (SPEC-006). In-memory next-run tracking."""

    def __init__(self, queue: JobQueueProtocol) -> None:
        self._queue = queue
        self._jobs: dict[str, ScheduledJob] = {}

    def add(self, schedule: Schedule, kind: str, payload: dict[str, Any],
            max_attempts: int = 3, now: datetime | None = None) -> str:
        """Register a schedule. Interval schedules fire immediately on first run_due."""
        schedule_id = schedule.schedule_id or _schedule_key(schedule, kind, payload)
        now = now or datetime.now()
        if schedule.kind == "cron":
            next_run = schedule.next_after(now)
        else:
            next_run = now  # interval/event/manual: due on first run_due
        self._jobs[schedule_id] = ScheduledJob(
            schedule=schedule, kind=kind, payload=payload,
            next_run=next_run, max_attempts=max_attempts,
        )
        return schedule_id

    def run_due(self, now: datetime | None = None) -> int:
        """Enqueue jobs whose next_run <= now. Idempotency keys prevent duplicates."""
        now = now or datetime.now()
        enqueued = 0
        for schedule_id, entry in list(self._jobs.items()):
            if entry.next_run <= now:
                key = f"sched:{schedule_id}:{entry.next_run.isoformat()}"
                self._queue.enqueue(
                    entry.kind, entry.payload, idempotency_key=key,
                    run_after=now_iso(), max_attempts=entry.max_attempts,
                )
                entry.next_run = entry.schedule.next_after(now)
                enqueued += 1
        return enqueued

    def entries(self) -> dict[str, ScheduledJob]:
        return dict(self._jobs)


def _schedule_key(schedule: Schedule, kind: str, payload: dict[str, Any]) -> str:
    blob = f"{schedule.kind}|{schedule.cron}|{schedule.seconds}|{kind}|{payload!r}"
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]
