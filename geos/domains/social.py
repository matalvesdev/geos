"""Social Scheduler (SPEC-025): approved content → deterministic per-channel posts.

Builds a single, deterministic post per (content, channel) — text derived from the
content body (hook + excerpt), hashtags from keywords, CTA when present — truncated
honestly to each channel's character limit. Publishing is gated by human approval
(spec §47: social.publish = HUMAN_APPROVAL_REQUIRED): without an approval decision,
no external write ever happens. Posts can be scheduled (SCHEDULED) and the engine
lists due posts for future automation; the external write still requires an
approved publish (SPEC-025 R4).
"""

from __future__ import annotations

import dataclasses
import unicodedata
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..core.approvals import ApprovalEngine
from ..core.events import SqliteEventBus
from ..storage.database import Database
from ..storage.repos import NotFoundError, RepoFactory
from ..util import now_iso, slugify

# Content statuses from which a social post may be prepared (SPEC-025 R1).
_PREPARE_FROM = {"APPROVED", "SCHEDULED"}

# Deterministic channel limits (SPEC-025 R2). Honest: the builder never exceeds these.
CHANNELS: dict[str, dict[str, int]] = {
    "x": {"char_limit": 280},
    "linkedin": {"char_limit": 3000},
    "bluesky": {"char_limit": 300},
    "instagram": {"char_limit": 2200},
}

MAX_HASHTAGS = 5


class SocialError(ValueError):
    """Invalid social operation (bad status, unknown channel, already published)."""


@dataclasses.dataclass(frozen=True)
class SocialPublishResult:
    """Outcome of a publish adapter call."""

    path: str
    url: str | None = None
    detail: str = ""


@runtime_checkable
class SocialAdapter(Protocol):
    """Adapter contract for publishing social posts (SPEC-025)."""

    name: str

    def publish(self, post: dict[str, Any]) -> SocialPublishResult: ...


class LocalSocialAdapter:
    """Write `<channel>-<slug>.txt` (text + hashtags + provenance) into a directory."""

    name = "local"

    def __init__(self, publish_dir: str | None = None) -> None:
        self._publish_dir = publish_dir

    def publish(self, post: dict[str, Any]) -> SocialPublishResult:
        directory = Path(self._publish_dir or post.get("publish_dir") or "social")
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{post['channel']}-{post['slug']}.txt"
        path = directory / filename
        path.write_text(render_social_post(post), encoding="utf-8")
        return SocialPublishResult(path=str(path))


# ---------------------------------------------------------------------------
# Deterministic rendering (SPEC-025 R2/R3)
# ---------------------------------------------------------------------------
def render_social_post(post: dict[str, Any]) -> str:
    """Full file: post text + hashtags (from the field, once) + provenance.

    Hashtags are rendered from the `hashtags` field — never embedded in `text` —
    so any caller-provided post renders them exactly once (SPEC-025 R2).
    """
    text = str(post.get("text") or "")
    tags = " ".join(f"#{h}" for h in (post.get("hashtags") or []))
    if tags:
        text = f"{text}\n\n{tags}"
    return (
        f"{text}\n\n---\n"
        f"*Proveniência: content {post.get('content_id') or 'n/a'} · "
        f"post {post['id']} · canal {post['channel']} · gerado por GEOS (SPEC-025).*\n"
    )


def _normalize_ascii(value: str) -> str:
    """Strip accents/diacritics (NFKD) so hashtags stay ASCII (SPEC-025 R2)."""
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def _hashtags_from_keywords(keywords: list[str]) -> list[str]:
    """Deterministic hashtags: slugified keywords, deduped, capped (SPEC-025 R2)."""
    seen: set[str] = set()
    result: list[str] = []
    for keyword in keywords or []:
        tag = slugify(_normalize_ascii(str(keyword)))
        if tag and tag not in seen:
            seen.add(tag)
            result.append(tag)
        if len(result) >= MAX_HASHTAGS:
            break
    return result


def _body_lines(content: dict[str, Any]) -> list[str]:
    """Meaningful body lines: skip empty lines and markdown headings."""
    body = str(content.get("body") or "")
    lines = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    """Truncate honestly with an ellipsis; never silently cut (SPEC-025 R2)."""
    if len(text) <= limit:
        return text, False
    return text[: limit - 1].rstrip() + "…", True


def build_post_text(content: dict[str, Any], channel: str) -> dict[str, Any]:
    """Deterministic post payload (text, hashtags, truncated flag) for a channel.

    Structure: hook (first meaningful body line, else title) + excerpt + CTA +
    hashtags. Each part is derived from the content object — never fabricated.
    """
    limit = CHANNELS[channel]["char_limit"]
    lines = _body_lines(content)
    hook = lines[0] if lines else str(content.get("title") or "")
    excerpt = " ".join(lines[1:]) if len(lines) > 1 else ""
    cta = str(content.get("cta") or "").strip()
    hashtags = _hashtags_from_keywords(content.get("keywords") or [])

    # Compose body parts only — hashtags are kept in the `hashtags` field and
    # rendered once by render_social_post (no duplication, SPEC-025 R2).
    parts: list[str] = [hook]
    if excerpt:
        parts.append(excerpt)
    if cta:
        parts.append(cta)
    body_text = "\n\n".join(parts)

    # The real post payload = text + hashtags; both must fit the channel limit.
    # `budget` reserves the hashtag line up front, so the final composition never
    # exceeds the limit (SPEC-025 R2).
    tags_text = " ".join(f"#{h}" for h in hashtags)
    reserve = (len(tags_text) + 2) if tags_text else 0
    budget = max(limit - reserve, 1)
    text, truncated = _truncate(body_text, budget)
    chars = len(text) + (reserve if tags_text else 0)
    if chars > limit:
        # Last-resort: hashtags alone ate the whole budget — honest minimal body.
        text, truncated = "", True
        chars = reserve

    return {"text": text, "hashtags": hashtags, "truncated": truncated,
            "chars": chars, "char_limit": limit}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class SocialEngine:
    def __init__(self, db: Database, publish_dir: str | None = None,
                 approvals: dict[str, str] | None = None) -> None:
        self._db = db
        self._repo = RepoFactory(db)
        self._default_publish_dir = publish_dir
        self._approvals = approvals

    # ---- preparation --------------------------------------------------------
    def prepare(self, content_id: str, channel: str, adapter: str = "local",
                publish_dir: str | None = None,
                scheduled_at: str | None = None) -> dict[str, Any]:
        """Turn an APPROVED/SCHEDULED content object into a DRAFT social post."""
        if channel not in CHANNELS:
            raise SocialError(
                f"unknown channel {channel!r} (available: {sorted(CHANNELS)}, SPEC-025)"
            )
        content = self._repo.content.get(content_id)
        if content is None:
            raise NotFoundError(f"content {content_id}")
        if content["status"] not in _PREPARE_FROM:
            raise SocialError(
                f"cannot prepare social post from content in status "
                f"{content['status']} (APPROVED or SCHEDULED required, SPEC-025 R1)"
            )
        body = str(content.get("body") or "").strip()
        if not body:
            raise SocialError("content has no draft body — produce a draft first (SPEC-022)")
        existing = self._repo.social.by_content_channel(content_id, channel)
        if existing is not None and existing["status"] != "FAILED":
            raise SocialError(
                f"social post for content {content_id} on {channel} already exists "
                f"({existing['status']}) — publish that post or choose another channel"
            )
        payload = build_post_text(content, channel)
        if existing is not None:
            # FAILED row: reuse it (unique (content_id, channel) index — re-prepare
            # must not hit IntegrityError, SPEC-025 R1).
            post_id = existing["id"]
            # Note: no approval reset — a PENDING approval for the failed attempt
            # is reused by publish (no queue spam); non-pending ones are replaced.
            self._repo.social.update(
                post_id, status="DRAFT", slug=content["slug"],
                text=payload["text"], hashtags=payload["hashtags"],
                adapter=adapter,
                publish_dir=publish_dir or self._default_publish_dir,
                scheduled_at=scheduled_at,
            )
        else:
            post_id = self._repo.social.create(
                content_id=content_id, slug=content["slug"], channel=channel,
                text=payload["text"], hashtags=payload["hashtags"],
                adapter=adapter,
                publish_dir=publish_dir or self._default_publish_dir,
                scheduled_at=scheduled_at,
            )
        try:
            SqliteEventBus(self._db).publish(
                "social.prepared",
                {"post_id": post_id, "content_id": content_id, "channel": channel,
                 "truncated": payload["truncated"]},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001 - telemetry must not fail prepare
            pass
        return self.get(post_id)

    def get(self, post_id: str) -> dict[str, Any]:
        post = self._repo.social.get(post_id)
        if post is None:
            raise NotFoundError(f"social post {post_id}")
        return post

    def list(self, status: str | None = None, channel: str | None = None,
             limit: int = 100) -> list[dict[str, Any]]:
        return self._repo.social.list(status=status, channel=channel, limit=limit)

    def due(self, limit: int = 100) -> list[dict[str, Any]]:
        """SCHEDULED posts whose time has come (for the scheduler/worker)."""
        return self._repo.social.due(limit=limit)

    def schedule(self, post_id: str, scheduled_at: str) -> dict[str, Any]:
        """Human decision: set the publish window (SPEC-025 R4)."""
        post = self.get(post_id)
        if post["status"] in ("PUBLISHED", "FAILED"):
            raise SocialError(
                f"cannot schedule a {post['status']} post (SPEC-025 R4)"
            )
        self._repo.social.update(post_id, scheduled_at=scheduled_at)
        return self.get(post_id)

    # ---- publish (approval-gated, SPEC-025 R1/R3) ---------------------------
    def publish(self, post_id: str, approve: bool = False,
                decided_by: str = "cli") -> dict[str, Any]:
        """Publish a social post.

        Gate (SPEC-025 R1): an external write happens only when there is a human
        decision — either the caller decides now (`approve=True`, decided by
        `decided_by`) or the linked approval was already decided APPROVED (via
        `geos approvals decide`), which lets the worker execute approved posts.
        """
        post = self.get(post_id)
        if post["status"] == "PUBLISHED":
            raise SocialError(
                f"post {post_id} is already PUBLISHED (SPEC-025 R3 — one publish per post)"
            )
        approvals = ApprovalEngine(self._db, self._approvals)
        approval_id = post.get("approval_id")
        if approval_id:
            existing = approvals.get(approval_id)
            if existing is not None and existing.status in ("PENDING", "APPROVED"):
                pass  # reuse: open request, or a decision the worker may execute
            else:
                approval_id = None
        if approval_id is None:
            approval = approvals.request(
                action="social.publish",
                metadata={"post_id": post_id, "channel": post["channel"],
                          "content_id": post.get("content_id")},
            )
            approval_id = approval.id
        current = approvals.get(approval_id)
        # Gate: no decision yet and nobody is deciding now → nothing external.
        if not approve and current is not None and current.status == "PENDING":
            self._repo.social.update(post_id, status="APPROVAL_PENDING",
                                     approval_id=approval_id)
            return self.get(post_id)
        # Scheduled for the future: approved but queued — no external write yet.
        if post.get("scheduled_at") and post["scheduled_at"] > now_iso():
            self._repo.social.update(post_id, status="SCHEDULED",
                                     approval_id=approval_id)
            return self.get(post_id)
        # Decision recorded only AFTER a successful adapter write. Real channel
        # adapters raise ChannelAdapterError (a SocialError), the local adapter
        # raises OSError — both mark the post FAILED (SPEC-025 contract).
        try:
            adapter = get_adapter(post.get("adapter") or "local",
                                  post.get("publish_dir"))
            result = adapter.publish(post)
        except (OSError, SocialError) as exc:
            self._repo.social.update(post_id, status="FAILED", approval_id=approval_id)
            raise SocialError(f"publish adapter failed: {exc}") from exc
        # Decide only if this call is the deciding authority (worker executes an
        # already-APPROVED decision without re-deciding).
        if current is not None and current.status == "PENDING":
            self._repo.approvals.decide(approval_id, "approve", decided_by)
        self._repo.social.update(
            post_id, status="PUBLISHED", published_path=result.path,
            published_url=result.url,
            published_at=post.get("scheduled_at") or now_iso(),
            approval_id=approval_id,
        )
        try:
            SqliteEventBus(self._db).publish(
                "social.published",
                {"post_id": post_id, "channel": post["channel"], "path": result.path},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass
        return self.get(post_id)

    # ---- worker (SPEC-025 R4: executes pre-approved, due posts) ------------
    def worker(self, limit: int = 100) -> dict[str, int]:
        """Publish posts that a human already approved and whose window is due.

        Read-only on decisions: never requests nor decides an approval — only
        executes APPROVED ones (spec §47, L3 AUTOMATED + APPROVAL). Counts
        published only when the post actually reaches PUBLISHED (a post whose
        window is still future is queued, not counted).
        """
        published = 0
        waiting = 0
        now = now_iso()
        for post in self.list(status="APPROVAL_PENDING", limit=limit) + \
                self.list(status="SCHEDULED", limit=limit):
            approval_id = post.get("approval_id")
            approval = (self._repo.approvals.get(approval_id)
                        if approval_id else None)
            scheduled_at = post.get("scheduled_at")
            is_due = (scheduled_at is None or scheduled_at <= now)
            if approval is not None and approval.status == "APPROVED" and is_due:
                try:
                    result = self.publish(post["id"])
                    if result["status"] == "PUBLISHED":
                        published += 1
                    else:
                        waiting += 1  # queued (future window) or still pending
                except SocialError:
                    waiting += 1  # adapter failure or rejected decision
            else:
                waiting += 1
        return {"published": published, "waiting": waiting}


# ---------------------------------------------------------------------------
# Adapter registry (SPEC-025; deterministic, extensible)
# ---------------------------------------------------------------------------
_ADAPTERS: dict[str, type] = {"local": LocalSocialAdapter}


def register_adapter(name: str, adapter_cls: type) -> None:
    _ADAPTERS[name] = adapter_cls


def get_adapter(name: str, publish_dir: str | None = None) -> SocialAdapter:
    _ensure_real_adapters()
    cls = _ADAPTERS.get(name)
    if cls is None:
        raise SocialError(f"unknown social adapter {name!r} (registered: {sorted(_ADAPTERS)})")
    try:
        if publish_dir is not None:
            return cls(publish_dir)
        return cls()
    except TypeError:
        # Adapters without a publish_dir constructor arg.
        return cls()


# Register the real channel adapters (X/LinkedIn/Bluesky) lazily on first use
# of the registry, so importing `social` never requires network config.
def _ensure_real_adapters() -> None:
    if "x_api" not in _ADAPTERS:
        from . import social_adapters

        social_adapters.register_default_adapters()
