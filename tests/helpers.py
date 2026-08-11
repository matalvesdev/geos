"""Shared test helpers."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from geos.storage.database import Database


def temp_db() -> Database:
    db = Database(None)
    db.open()
    db.migrate()
    return db


class TempDir:
    """Context manager exposing a temp dir as Path."""

    def __enter__(self) -> Path:
        self._tmp = TemporaryDirectory()
        return Path(self._tmp.name)

    def __exit__(self, *exc: object) -> None:
        self._tmp.cleanup()
