"""Job system (SPEC-005, ADR-0003). Queue + worker with retry, backoff, dead-letter.

States (spec §50): PENDING, RUNNING, WAITING_APPROVAL, SUCCESS, FAILED, CANCELLED,
RETRYING + DEAD (dead-letter terminal state).

Attempts semantics: `attempts` counts retries (increments only when a job is
re-queued after a transient failure). A job that fails terminally on the first
execution records attempts=0.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Protocol

from ..storage.database import Database
from ..storage.repos import Job, JobRepository
from ..util import now_iso

logger = logging.getLogger("geos.jobs")


class TransientError(Exception):
    """Retryable failure (network, rate limit, temporary lock)."""


class PermanentError(Exception):
    """Terminal failure — do not retry."""


class JobQueueProtocol(Protocol):
    def enqueue(self, kind: str, payload: dict[str, Any], idempotency_key: str | None = None,
                run_after: str | None = None, max_attempts: int = 3,
                trace_id: str | None = None) -> Job: ...
    def claim_next(self, now: str) -> Job | None: ...


class SqliteJobQueue:
    """SQLite-backed queue. Single-writer semantics (ADR-0002)."""

    def __init__(self, db: Database) -> None:
        self._repo = JobRepository(db)

    def enqueue(self, kind: str, payload: dict[str, Any], idempotency_key: str | None = None,
                run_after: str | None = None, max_attempts: int = 3,
                trace_id: str | None = None) -> Job:
        return self._repo.enqueue(
            kind, payload, idempotency_key=idempotency_key, run_after=run_after,
            max_attempts=max_attempts, trace_id=trace_id,
        )

    def claim_next(self, now: str) -> Job | None:
        return self._repo.claim_next(now)

    def update(self, job: Job, status: str, error: str | None = None,
               run_after: str | None = None) -> None:
        self._repo.update_status(job.id, status, error=error, run_after=run_after)

    def increment_attempts(self, job_id: str) -> int:
        return self._repo.increment_attempts(job_id)

    def list(self, status: str | None = None, limit: int = 100) -> list[Job]:
        return self._repo.list(status=status, limit=limit)


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    backoff_base: float = 2.0
    backoff_max_seconds: float = 300.0
    jitter: bool = False  # deterministic-first (ADR-0004); enable jitter only when needed

    def next_run_after(self, attempts: int, now: datetime) -> datetime:
        delay = min(self.backoff_base ** attempts, self.backoff_max_seconds)
        if self.jitter:
            delay = delay * random.uniform(0.8, 1.2)
        return now + timedelta(seconds=delay)


JobHandler = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any] | None]


class Worker:
    """Executes due jobs. Handlers are resolved from a fixed registry (no code-from-payload)."""

    def __init__(self, queue: JobQueueProtocol, retry_policy: RetryPolicy | None = None) -> None:
        self._queue = queue
        self._policy = retry_policy or RetryPolicy()
        self._registry: dict[str, JobHandler] = {}

    def register(self, kind: str, handler: JobHandler) -> None:
        self._registry[kind] = handler

    def run_once(self, now: str | None = None) -> Job | None:
        now = now or now_iso()
        job = self._queue.claim_next(now)
        if job is None:
            return None
        handler = self._registry.get(job.kind)
        if handler is None:
            self._queue.update(job, "DEAD", error=f"no handler registered for kind {job.kind!r}")
            return job
        ctx = {"job": job, "trace_id": job.trace_id}
        try:
            handler(job.payload, ctx)
            self._queue.update(job, "SUCCESS")
        except TransientError as exc:
            self._handle_retry(job, str(exc), now)
        except PermanentError as exc:
            self._queue.update(job, "FAILED", error=str(exc))
        except Exception as exc:  # noqa: BLE001 - unknown errors are terminal
            logger.error("job %s (%s) failed", job.id, job.kind, exc_info=True)
            self._queue.update(job, "FAILED", error=f"{type(exc).__name__}: {exc}")
        return job

    def _handle_retry(self, job: Job, error: str, now: str) -> None:
        attempts = self._queue.increment_attempts(job.id)
        if attempts >= job.max_attempts:
            self._queue.update(job, "DEAD", error=error)
            return
        try:
            now_dt = datetime.fromisoformat(now)
        except ValueError:
            now_dt = datetime.now()
        run_after = self._policy.next_run_after(attempts, now_dt).isoformat()
        self._queue.update(job, "RETRYING", error=error, run_after=run_after)

    def run_until_idle(self, max_loops: int = 10_000, now: str | None = None) -> int:
        """Run until no due jobs remain (guarded against infinite loops). Returns count."""
        count = 0
        while count < max_loops:
            job = self.run_once(now=now)
            if job is None:
                break
            count += 1
        return count
