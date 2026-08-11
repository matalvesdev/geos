"""Community Engine (SPEC-037): community management and engagement.

Community manages members, threads, and replies across platforms.
Threads flow through: open → resolved → archived.

The engine supports Discord blueprint integration and question→education
loop (questions in community can generate academy content suggestions).
"""

from __future__ import annotations

from typing import Any

from ..core.events import SqliteEventBus
from ..storage.database import Database
from ..storage.repos import NotFoundError, RepoFactory
from ..util import new_id, now_iso

# Thread statuses
THREAD_STATUSES: dict[str, set[str]] = {
    "open": {"resolved", "archived"},
    "resolved": {"archived"},
    "archived": set(),
}

# Platforms
PLATFORMS = ("internal", "discord", "slack", "forum", "github")

# Member roles
MEMBER_ROLES = ("member", "moderator", "admin", "bot")


class CommunityError(ValueError):
    """Invalid community operation."""


class CommunityEngine:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._repo = RepoFactory(db)

    # ---- members -----------------------------------------------------------
    def add_member(
        self,
        name: str,
        external_id: str | None = None,
        email: str | None = None,
        platform: str = "internal",
        role: str = "member",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Add a community member."""
        name = name.strip()
        if not name:
            raise CommunityError("name is required")
        if platform not in PLATFORMS:
            raise CommunityError(f"unknown platform {platform!r}")
        if role not in MEMBER_ROLES:
            raise CommunityError(f"unknown role {role!r}")

        member_id = self._repo.community.add_member(
            name=name, external_id=external_id, email=email,
            platform=platform, role=role, metadata=metadata,
        )

        try:
            SqliteEventBus(self._db).publish(
                "community.member_joined",
                {"member_id": member_id, "name": name, "platform": platform},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass

        return self._repo.community.get_member(member_id)

    def get_member(self, member_id: str) -> dict[str, Any]:
        """Get member by ID."""
        item = self._repo.community.get_member(member_id)
        if item is None:
            raise NotFoundError(f"community member {member_id}")
        return item

    def list_members(
        self, platform: str | None = None, role: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """List members with filters."""
        return self._repo.community.list_members(
            platform=platform, role=role, limit=limit
        )

    def update_activity(self, member_id: str) -> dict[str, Any]:
        """Update member's last active timestamp."""
        self.get_member(member_id)  # validate exists
        self._repo.community.update_activity(member_id)
        return self.get_member(member_id)

    # ---- threads -----------------------------------------------------------
    def create_thread(
        self,
        channel: str,
        title: str,
        author_id: str | None = None,
        content: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new thread."""
        title = title.strip()
        if not title:
            raise CommunityError("title is required")
        if not channel:
            raise CommunityError("channel is required")

        # Validate author exists if provided
        if author_id:
            self.get_member(author_id)

        thread_id = self._repo.community.create_thread(
            channel=channel, title=title, author_id=author_id,
            tags=tags or [],
        )

        # Add initial reply if content provided
        if content and author_id:
            self.add_reply(thread_id, author_id, content)

        try:
            SqliteEventBus(self._db).publish(
                "community.thread_created",
                {"thread_id": thread_id, "channel": channel, "title": title},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass

        return self._repo.community.get_thread(thread_id)

    def get_thread(self, thread_id: str) -> dict[str, Any]:
        """Get thread by ID."""
        item = self._repo.community.get_thread(thread_id)
        if item is None:
            raise NotFoundError(f"community thread {thread_id}")
        return item

    def list_threads(
        self, channel: str | None = None, status: str | None = None,
        author_id: str | None = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List threads with filters."""
        return self._repo.community.list_threads(
            channel=channel, status=status, author_id=author_id, limit=limit
        )

    def transition_thread(self, thread_id: str, target: str) -> dict[str, Any]:
        """Transition thread status."""
        item = self.get_thread(thread_id)
        target = target.lower()
        allowed = THREAD_STATUSES.get(item["status"], set())
        if target not in allowed:
            raise CommunityError(
                f"invalid transition {item['status']} → {target} "
                f"(allowed: {sorted(allowed) or 'none'})"
            )

        self._repo.community.update_thread_status(thread_id, target)
        return self.get_thread(thread_id)

    def resolve_thread(self, thread_id: str) -> dict[str, Any]:
        """Resolve a thread."""
        return self.transition_thread(thread_id, "resolved")

    def archive_thread(self, thread_id: str) -> dict[str, Any]:
        """Archive a thread."""
        return self.transition_thread(thread_id, "archived")

    # ---- replies -----------------------------------------------------------
    def add_reply(
        self, thread_id: str, author_id: str, content: str,
        is_answer: bool = False,
    ) -> dict[str, Any]:
        """Add a reply to a thread."""
        self.get_thread(thread_id)  # validate exists
        self.get_member(author_id)  # validate exists

        content = content.strip()
        if not content:
            raise CommunityError("content is required")

        reply_id = self._repo.community.add_reply(
            thread_id=thread_id, author_id=author_id,
            content=content, is_answer=is_answer,
        )

        # Update reply count and last_reply_at
        self._repo.community.increment_reply_count(thread_id)

        try:
            SqliteEventBus(self._db).publish(
                "community.reply_added",
                {"thread_id": thread_id, "reply_id": reply_id, "author_id": author_id},
                trace_id=None,
            )
        except Exception:  # noqa: BLE001
            pass

        return self._repo.community.get_reply(reply_id)

    def list_replies(self, thread_id: str) -> list[dict[str, Any]]:
        """List replies for a thread."""
        self.get_thread(thread_id)  # validate exists
        return self._repo.community.list_replies(thread_id)

    # ---- analytics ---------------------------------------------------------
    def channel_analytics(self, channel: str) -> dict[str, Any]:
        """Get analytics for a channel."""
        threads = self._repo.community.list_threads(channel=channel, limit=1000)
        total = len(threads)
        open_count = sum(1 for t in threads if t["status"] == "open")
        resolved = sum(1 for t in threads if t["status"] == "resolved")

        return {
            "channel": channel,
            "total_threads": total,
            "open": open_count,
            "resolved": resolved,
            "resolution_rate": round(resolved / total * 100, 1) if total else 0,
        }

    def community_overview(self) -> dict[str, Any]:
        """Get overall community stats."""
        members = self.list_members(limit=10000)
        threads = self._repo.community.list_threads(limit=10000)

        return {
            "total_members": len(members),
            "total_threads": len(threads),
            "open_threads": sum(1 for t in threads if t["status"] == "open"),
            "platforms": list({m["platform"] for m in members}),
        }
