"""Blog Publisher (SPEC-024): approved content → publishable markdown posts.

Prepares deterministic markdown + YAML front matter from APPROVED/SCHEDULED content
objects and publishes through pluggable adapters. Publishing is gated by human
approval (spec §47: blog.publish = HUMAN_APPROVAL_REQUIRED) — without an approval
decision, no external write ever happens. Provenance is preserved end-to-end
(content_id, version, sources in front matter).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..core.approvals import ApprovalEngine
from ..core.events import SqliteEventBus
from ..storage.database import Database
from ..storage.repos import NotFoundError, RepoFactory
from ..util import now_iso

# Content statuses from which a post may be prepared (SPEC-024 R1).
_PREPARE_FROM = {"APPROVED", "SCHEDULED"}


class BlogError(ValueError):
    """Invalid blog operation (bad status, already published, missing body)."""


@dataclasses.dataclass(frozen=True)
class BlogPublishResult:
    """Outcome of a publish adapter call."""

    path: str
    url: str | None = None
    detail: str = ""


@runtime_checkable
class BlogAdapter(Protocol):
    """Adapter contract for publishing markdown posts (SPEC-024)."""

    name: str

    def publish(self, post: dict[str, Any]) -> BlogPublishResult: ...


class LocalMarkdownAdapter:
    """Write `<slug>.md` (front matter + body) into a directory (headless default)."""

    name = "local"

    def __init__(self, publish_dir: str | None = None) -> None:
        self._publish_dir = publish_dir

    def publish(self, post: dict[str, Any]) -> BlogPublishResult:
        directory = Path(self._publish_dir or post.get("publish_dir") or "blog")
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{post['slug']}.md"
        path = directory / filename
        rendered = render_markdown(post)
        path.write_text(rendered, encoding="utf-8")
        return BlogPublishResult(path=str(path), url=f"/{filename}")


# ---------------------------------------------------------------------------
# Deterministic rendering (SPEC-024 R2)
# ---------------------------------------------------------------------------
def render_front_matter(post: dict[str, Any]) -> str:
    """Render YAML front matter deterministically (stable key order)."""
    fm = dict(post.get("front_matter") or {})
    fm.setdefault("title", post.get("title", ""))
    fm.setdefault("slug", post.get("slug", ""))
    fm.setdefault("date", post.get("published_at") or now_iso()[:10])
    lines = ["---"]
    for key in sorted(fm):
        value = fm[key]
        if isinstance(value, (list, tuple)):
            rendered = ", ".join(str(v) for v in value)
            lines.append(f"{key}: [{rendered}]")
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        else:
            text = str(value).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key}: "{text}"')
    lines.append("---")
    return "\n".join(lines)


def render_markdown(post: dict[str, Any]) -> str:
    """Full file: front matter + body (+ provenance footer)."""
    body = str(post.get("body") or "")
    footer = (
        "\n\n---\n"
        f"*Proveniência: content {post.get('content_id') or 'n/a'} · "
        f"post {post['id']} · gerado por GEOS (SPEC-024).*"
    )
    return f"{render_front_matter(post)}\n\n{body}{footer}\n"


def _build_front_matter(content: dict[str, Any]) -> dict[str, Any]:
    """Deterministic front matter from a content object (SPEC-024 R2/R4)."""
    body = str(content.get("body") or "")
    summary = ""
    for line in body.splitlines():
        if line.strip() and not line.strip().startswith("#"):
            summary = line.strip()[:160]
            break
    fm: dict[str, Any] = {
        "title": content["title"],
        "slug": content["slug"],
        "type": content["content_type"],
        "status": content["status"],
        "keywords": [str(k) for k in (content.get("keywords") or [])],
        "summary": summary,
        "sources": [str(s) for s in (content.get("sources") or [])],
        "mock": bool(content.get("mock", True)),
        "content_id": content["id"],
        "content_version": int(content.get("version") or 1),
    }
    return fm


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class BlogEngine:
    def __init__(self, db: Database, publish_dir: str | None = None,
                 approvals: dict[str, str] | None = None) -> None:
        self._db = db
        self._repo = RepoFactory(db)
        self._default_publish_dir = publish_dir
        self._approvals = approvals

    # ---- preparation --------------------------------------------------------
    def prepare(self, content_id: str, adapter: str = "local",
                publish_dir: str | None = None) -> dict[str, Any]:
        """Turn an APPROVED/SCHEDULED content object into a DRAFT blog post."""
        content = self._repo.content.get(content_id)
        if content is None:
            raise NotFoundError(f"content {content_id}")
        if content["status"] not in _PREPARE_FROM:
            raise BlogError(
                f"cannot prepare blog post from content in status "
                f"{content['status']} (APPROVED or SCHEDULED required, SPEC-024 R1)"
            )
        body = str(content.get("body") or "").strip()
        if not body:
            raise BlogError("content has no draft body — produce a draft first (SPEC-022)")
        existing = self._repo.blog.by_slug(content["slug"])
        if existing is not None and existing["status"] != "FAILED":
            raise BlogError(
                f"blog post for slug {content['slug']!r} already exists "
                f"({existing['status']}) — publish that post or choose another content"
            )
        post_id = self._repo.blog.create(
            content_id=content_id, slug=content["slug"], title=content["title"],
            body=body, front_matter=_build_front_matter(content), adapter=adapter,
            publish_dir=publish_dir or self._default_publish_dir,
        )
        try:
            SqliteEventBus(self._db).publish(
                "blog.prepared",
                {"post_id": post_id, "content_id": content_id, "slug": content["slug"]},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001 - telemetry must not fail prepare
            pass
        return self.get(post_id)

    def get(self, post_id: str) -> dict[str, Any]:
        post = self._repo.blog.get(post_id)
        if post is None:
            raise NotFoundError(f"blog post {post_id}")
        return post

    def list(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return self._repo.blog.list(status=status, limit=limit)

    # ---- publish (approval-gated, SPEC-024 R1/R3) ---------------------------
    def publish(self, post_id: str, approve: bool = False,
                decided_by: str = "cli") -> dict[str, Any]:
        post = self.get(post_id)
        if post["status"] == "PUBLISHED":
            raise BlogError(
                f"post {post_id} is already PUBLISHED (SPEC-024 R3 — one publish per post)"
            )
        approvals = ApprovalEngine(self._db, self._approvals)
        # Reuse an existing pending approval for this post instead of spamming
        # the approval queue on repeated gated publish calls (review finding).
        approval_id = post.get("approval_id")
        if approval_id:
            existing = approvals.get(approval_id)
            if existing is not None and existing.status == "PENDING":
                pass  # reuse the open request
            else:
                approval_id = None
        if approval_id is None:
            approval = approvals.request(
                action="blog.publish",
                metadata={"post_id": post_id, "slug": post["slug"]},
            )
            approval_id = approval.id
        # Gate: no approval decision → nothing external happens (SPEC-024 R1).
        if not approve:
            self._repo.blog.update(post_id, status="APPROVAL_PENDING",
                                   approval_id=approval_id)
            return self.get(post_id)
        # Decision recorded only AFTER a successful adapter write, so the
        # approval trail reflects the actual outcome (review finding).
        try:
            adapter = get_adapter(post.get("adapter") or "local",
                                  post.get("publish_dir"))
            result = adapter.publish(post)
        except OSError as exc:
            # Keep the approval trail attached on failure (review finding).
            self._repo.blog.update(post_id, status="FAILED", approval_id=approval_id)
            raise BlogError(f"publish adapter failed: {exc}") from exc
        self._repo.approvals.decide(approval_id, "approve", decided_by)
        self._repo.blog.update(
            post_id, status="PUBLISHED", published_path=result.path,
            published_url=result.url, published_at=now_iso(), approval_id=approval_id,
        )
        try:
            SqliteEventBus(self._db).publish(
                "blog.published",
                {"post_id": post_id, "slug": post["slug"], "path": result.path},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass
        return self.get(post_id)


# ---------------------------------------------------------------------------
# Adapter registry (SPEC-024; deterministic, extensible)
# ---------------------------------------------------------------------------
_ADAPTERS: dict[str, type] = {"local": LocalMarkdownAdapter}


def register_adapter(name: str, adapter_cls: type) -> None:
    _ADAPTERS[name] = adapter_cls


def get_adapter(name: str, publish_dir: str | None = None) -> BlogAdapter:
    cls = _ADAPTERS.get(name)
    if cls is None:
        raise BlogError(f"unknown blog adapter {name!r} (registered: {sorted(_ADAPTERS)})")
    try:
        if publish_dir is not None:
            return cls(publish_dir)
        return cls()
    except TypeError:
        # Adapters without a publish_dir constructor arg (review finding).
        return cls()
