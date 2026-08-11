"""SQLite connection manager (SPEC-002). WAL, FK enforcement, migration hookup."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .migrations import MIGRATIONS, MigrationError


class Database:
    """Owns a single SQLite connection. path=None -> in-memory (tests)."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path: Path | None = Path(path) if path is not None else None
        self.conn: sqlite3.Connection | None = None

    def open(self) -> "Database":
        if self.conn is not None:
            return self
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.path), timeout=10)
        else:
            conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        if self.path is not None:
            conn.execute("PRAGMA journal_mode = WAL")
        self.conn = conn
        return self

    @property
    def conn_checked(self) -> sqlite3.Connection:
        if self.conn is None:
            raise RuntimeError("Database not open; call open() first")
        return self.conn

    def migrate(self) -> int:
        """Apply pending migrations, return the resulting schema version."""
        return _apply(self, MIGRATIONS)

    def current_version(self) -> int:
        return _current_version(self)

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __enter__(self) -> "Database":
        return self.open()

    def __exit__(self, *exc: object) -> None:
        self.close()


def _ensure_tracking(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS migration_history ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " version INTEGER NOT NULL,"
        " name TEXT NOT NULL,"
        " applied_at TEXT NOT NULL)"
    )


def _current_version(db: Database) -> int:
    conn = db.conn_checked
    _ensure_tracking(conn)
    row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    return int(row["version"]) if row else 0


def _apply(db: Database, migrations: list[tuple[int, str, str]]) -> int:
    conn = db.conn_checked
    _ensure_tracking(conn)
    current = _current_version(db)
    pending = [m for m in migrations if m[0] > current]
    for version, name, sql in pending:
        try:
            # executescript() runs in autocommit (it implicitly commits any pending
            # transaction first). SQLite DDL is therefore NOT atomic with the version
            # bump below — a failed script leaves partial DDL behind. Bootstrap DDL uses
            # IF NOT EXISTS everywhere, so a re-run is safe. Do not assume atomicity.
            conn.executescript(sql)
            with conn:  # version + history recorded in one small transaction
                if conn.execute("SELECT COUNT(*) c FROM schema_version").fetchone()["c"] == 0:
                    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
                else:
                    conn.execute("UPDATE schema_version SET version = ?", (version,))
                conn.execute(
                    "INSERT INTO migration_history (version, name, applied_at) VALUES (?, ?, datetime('now'))",
                    (version, name),
                )
        except sqlite3.Error as exc:
            raise MigrationError(f"Migration V{version:03d} ({name}) failed: {exc}") from exc
    return _current_version(db)
