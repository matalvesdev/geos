"""Real channel adapters (SPEC-025): X, LinkedIn, Bluesky.

Zero-dependency (stdlib `urllib`) HTTP adapters behind the `SocialAdapter`
protocol. Credentials come from env vars (constructor override wins). Honest
failure: missing credentials or any transport error raises a typed
`ChannelAdapterError` — the caller decides how to surface it (the publish flow
marks the post FAILED; no data is fabricated).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .social import SocialAdapter, SocialError

# Timeout for outbound channel calls (seconds). Deterministic, bounded.
TIMEOUT_S = 15
# Some endpoints reject the bare python-urllib User-Agent (403); be explicit.
USER_AGENT = "geos/0.9.0 (+https://github.com/matalvesdev/geos)"


class ChannelAdapterError(SocialError):
    """Typed transport/credentials failure from a real channel adapter."""


def _credentials(names: list[str]) -> str:
    """First non-empty env var among `names` (honest credential lookup)."""
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _http_json(method: str, url: str, headers: dict[str, str],
               payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """POST/GET JSON with stdlib urllib; typed errors on failure."""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("User-Agent", USER_AGENT)
    for key, value in headers.items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            body = response.read().decode("utf-8", errors="replace")
            if not body:
                return {}
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {"_raw": body}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise ChannelAdapterError(
            f"channel http {exc.code} from {url}: {detail}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ChannelAdapterError(f"channel transport error for {url}: {exc}") from exc


class XApiAdapter:
    """X API v2 — POST /2/tweets (OAuth 2.0 user context Bearer token)."""

    name = "x_api"

    def __init__(self, bearer_token: str | None = None) -> None:
        self._bearer = bearer_token or _credentials(
            ["GEOS_X_BEARER_TOKEN", "X_BEARER_TOKEN"])

    def publish(self, post: dict[str, Any]):
        from .social import SocialPublishResult

        if not self._bearer:
            raise ChannelAdapterError(
                "x_api requires GEOS_X_BEARER_TOKEN (OAuth 2.0 user context with "
                "tweet.write scope) — configure before publishing"
            )
        text = str(post.get("text") or "")
        if not text.strip():
            raise ChannelAdapterError("cannot publish empty post to X")
        response = _http_json(
            "POST", "https://api.x.com/2/tweets",
            {"Authorization": f"Bearer {self._bearer}",
             "Content-Type": "application/json"},
            {"text": text},
        )
        tweet_id = (response.get("data") or {}).get("id") or ""
        return SocialPublishResult(
            path="x", url=f"https://x.com/i/status/{tweet_id}" if tweet_id else None,
            detail=f"tweet {tweet_id}" if tweet_id else str(response)[:120],
        )


class LinkedInApiAdapter:
    """LinkedIn Community Posts API — POST /rest/posts (OAuth 2.0 Bearer)."""

    name = "linkedin_api"

    def __init__(self, bearer_token: str | None = None,
                 author_urn: str | None = None) -> None:
        self._bearer = bearer_token or _credentials(
            ["GEOS_LINKEDIN_BEARER_TOKEN", "LINKEDIN_BEARER_TOKEN"])
        self._author = author_urn or os.environ.get("GEOS_LINKEDIN_AUTHOR_URN", "").strip()

    def publish(self, post: dict[str, Any]):
        from .social import SocialPublishResult

        if not self._bearer:
            raise ChannelAdapterError(
                "linkedin_api requires GEOS_LINKEDIN_BEARER_TOKEN (w_member_social "
                "or w_organization_social) — configure before publishing"
            )
        if not self._author:
            raise ChannelAdapterError(
                "linkedin_api requires GEOS_LINKEDIN_AUTHOR_URN "
                "(urn:li:organization:... or urn:li:person:...)"
            )
        text = str(post.get("text") or "")
        if not text.strip():
            raise ChannelAdapterError("cannot publish empty post to LinkedIn")
        response = _http_json(
            "POST", "https://api.linkedin.com/rest/posts",
            {"Authorization": f"Bearer {self._bearer}",
             "X-Restli-Protocol-Version": "2.0.0",
             "Linkedin-Version": "202607",
             "Content-Type": "application/json"},
            {
                "author": self._author,
                "commentary": text,
                "visibility": "PUBLIC",
                "distribution": {"feedDistribution": "MAIN_FEED",
                                 "targetEntities": [],
                                 "thirdPartyDistributionChannels": []},
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            },
        )
        post_id = response.get("id") or ""
        return SocialPublishResult(
            path="linkedin", url=post_id or None,
            detail=f"post {post_id}" if post_id else str(response)[:120],
        )


class BlueskyApiAdapter:
    """Bluesky AT Protocol — createSession (app password) + createRecord.

    A single publish performs both calls (session JWT is not persisted).
    """

    name = "bluesky_api"

    def __init__(self, handle: str | None = None,
                 app_password: str | None = None,
                 pds_url: str = "https://bsky.social") -> None:
        self._handle = handle or _credentials(["GEOS_BLUESKY_HANDLE", "BSKY_HANDLE"])
        self._password = app_password or _credentials(
            ["GEOS_BLUESKY_APP_PASSWORD", "BSKY_APP_PASSWORD"])
        self._pds = (pds_url or "https://bsky.social").rstrip("/")

    def _create_session(self) -> str:
        response = _http_json(
            "POST", f"{self._pds}/xrpc/com.atproto.server.createSession",
            {"Content-Type": "application/json"},
            {"identifier": self._handle, "password": self._password},
        )
        access_jwt = response.get("accessJwt") or ""
        if not access_jwt:
            raise ChannelAdapterError(
                f"bluesky createSession failed: {str(response)[:160]}")
        return access_jwt

    def publish(self, post: dict[str, Any]):
        from .social import SocialPublishResult

        if not self._handle or not self._password:
            raise ChannelAdapterError(
                "bluesky_api requires GEOS_BLUESKY_HANDLE and "
                "GEOS_BLUESKY_APP_PASSWORD — configure before publishing"
            )
        text = str(post.get("text") or "")
        if not text.strip():
            raise ChannelAdapterError("cannot publish empty post to Bluesky")
        access_jwt = self._create_session()
        from ..util import now_iso

        response = _http_json(
            "POST", f"{self._pds}/xrpc/com.atproto.repo.createRecord",
            {"Authorization": f"Bearer {access_jwt}",
             "Content-Type": "application/json"},
            {
                "repo": self._handle,
                "collection": "app.bsky.feed.post",
                "record": {"$type": "app.bsky.feed.post",
                           "text": text,
                           "createdAt": now_iso()},
            },
        )
        uri = response.get("uri") or ""
        return SocialPublishResult(
            path="bluesky", url=uri or None,
            detail=f"record {uri}" if uri else str(response)[:120],
        )


def register_default_adapters() -> None:
    """Register the real channel adapters into the SocialAdapter registry."""
    from .social import register_adapter

    register_adapter("x_api", XApiAdapter)
    register_adapter("linkedin_api", LinkedInApiAdapter)
    register_adapter("bluesky_api", BlueskyApiAdapter)
