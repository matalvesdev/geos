"""Deterministic helpers: identity, time, slugs (SPEC-001, ADR-0004)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

UUID_RE = re.compile(r"[^0-9a-f]")


def new_id() -> str:
    """Canonical RFC-4122 UUID, hex form (no dashes) — same convention as Zetra One."""
    return uuid.uuid4().hex


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return utc_now().isoformat()


def duration_ms(started: datetime, finished: datetime) -> int:
    return int((finished - started).total_seconds() * 1000)


def slugify(value: str) -> str:
    """Deterministic slug: lowercase, alphanumeric + hyphen."""
    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "item"
