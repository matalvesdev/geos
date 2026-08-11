"""Project manifest + repository registry (SPEC-009 / mandated SPEC-107)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .capabilities import Detection
from .mode import ModeResult


@dataclass
class RepoEntry:
    id: str
    name: str
    path: str
    repo_type: str = "PRODUCT"
    domains: list[str] = field(default_factory=list)
    last_indexed_at: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class RepositoryRegistry:
    """JSON-backed registry at .geos/repositories.json (SQLite table comes later)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._entries: dict[str, RepoEntry] = {}
        if self.path.is_file():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                for item in data.get("repositories", []):
                    entry = RepoEntry(**item)
                    self._entries[entry.id] = entry
            except (json.JSONDecodeError, TypeError, ValueError):
                self._entries = {}

    def add(self, entry: RepoEntry) -> RepoEntry:
        self._entries[entry.id] = entry
        self._save()
        return entry

    def get(self, repo_id: str) -> RepoEntry | None:
        return self._entries.get(repo_id)

    def list(self) -> list[RepoEntry]:
        return list(self._entries.values())

    def remove(self, repo_id: str) -> bool:
        removed = self._entries.pop(repo_id, None) is not None
        if removed:
            self._save()
        return removed

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"repositories": [e.to_dict() for e in self._entries.values()]}
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def build_manifest(
    root: str | Path,
    mode_result: ModeResult,
    detections: list[Detection],
    repositories: list[RepoEntry],
) -> dict[str, object]:
    capabilities = [
        {
            "name": d.name,
            "capability": d.capability,
            "confidence": d.confidence,
            "evidence": d.evidence,
        }
        for d in detections
    ]
    languages = sorted(
        {d.name for d in detections if d.capability == "language_runtime"}
    )
    return {
        "schema": "geos/project-manifest/1",
        "mode": mode_result.mode,
        "mode_confidence": mode_result.confidence,
        "mode_evidence": mode_result.evidence,
        "installation": "SIDECAR",
        "capabilities": capabilities,
        "languages": languages,
        "repositories": [r.to_dict() for r in repositories],
        "last_audit": datetime.now(timezone.utc).isoformat(),
    }


def write_manifest(manifest: dict[str, object], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def load_manifest(path: str | Path) -> dict[str, object] | None:
    path = Path(path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None
