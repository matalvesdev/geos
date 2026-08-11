"""Telemetry (SPEC-001/§155). Every run records trace, duration, model, tokens, cost, error."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..storage.database import Database
from ..storage.repos import Run, RunRepository
from ..util import duration_ms, new_id, now_iso, utc_now


@dataclass
class RunContext:
    """Live handle for one run; finish() writes the terminal record."""

    repo: RunRepository
    run: Run
    _started: datetime = field(default_factory=utc_now)

    def finish(self, status: str, error: str | None = None, model: str | None = None,
               tokens: int | None = None, cost: float | None = None) -> None:
        self.repo.finish(
            self.run.id, status=status, error=error, model=model, tokens=tokens, cost=cost,
        )


class Telemetry:
    def __init__(self, db: Database, workspace_id: str = "default") -> None:
        self._repo = RunRepository(db)
        self._workspace_id = workspace_id

    def start(self, workflow_id: str | None = None, agent: str | None = None,
              trace_id: str | None = None) -> RunContext:
        run = Run(
            id=new_id(), workspace_id=self._workspace_id, workflow_id=workflow_id,
            agent=agent, trace_id=trace_id or new_id(), status="RUNNING",
            started_at=now_iso(),
        )
        self._repo.insert(run)
        return RunContext(repo=self._repo, run=run, _started=utc_now())

    def list(self, status: str | None = None, limit: int = 100) -> list[Run]:
        return self._repo.list(status=status, limit=limit)


def elapsed_ms(ctx: RunContext) -> int:
    return duration_ms(ctx._started, utc_now())
