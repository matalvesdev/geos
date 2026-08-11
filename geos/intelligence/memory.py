"""Memory system (SPEC-014): scoped key/value with TTL and sensitivity, plus an
in-process WorkingMemory wrapper. Specialized memory types (lead/customer/campaign/
research/organizational) are scopes over the same store."""

from __future__ import annotations

from typing import Any

from ..storage.database import Database
from ..storage.repos import MemoryRepository


class MemoryStore:
    def __init__(self, db: Database) -> None:
        self._repo = MemoryRepository(db)

    def put(self, scope: str, key: str, value: Any, source: str | None = None,
            confidence: float | None = None, sensitivity: str = "INTERNAL",
            ttl_seconds: int | None = None) -> None:
        import json

        payload = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        self._repo.put(scope, key, payload, source=source, confidence=confidence,
                       sensitivity=sensitivity, retention_seconds=ttl_seconds)

    def get(self, scope: str, key: str, default: Any = None) -> Any:
        import json

        row = self._repo.get(scope, key)
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return row["value"]

    def list(self, scope: str | None = None) -> list[dict[str, Any]]:
        return self._repo.list(scope=scope)

    def delete(self, scope: str, key: str) -> bool:
        return self._repo.delete(scope, key)


class WorkingMemory:
    """Short-lived, non-persistent state for a single run/agent session."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def clear(self) -> None:
        self._data.clear()
