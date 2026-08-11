"""Real channel adapter tests (SPEC-025): credentials, payloads, typed errors.

HTTP is mocked (`urllib.request.urlopen`) — no live network in tests.
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

from geos.domains.social import get_adapter
from geos.domains.social_adapters import (BlueskyApiAdapter,
                                          ChannelAdapterError, LinkedInApiAdapter,
                                          XApiAdapter, register_default_adapters)


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc: object) -> None:
        pass


class XApiAdapterTests(unittest.TestCase):
    def test_requires_bearer_token(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            adapter = XApiAdapter()
            with self.assertRaises(ChannelAdapterError):
                adapter.publish({"text": "olá", "channel": "x", "id": "p1"})

    def test_reads_token_from_env(self) -> None:
        with mock.patch.dict("os.environ", {"GEOS_X_BEARER_TOKEN": "tok"}, clear=True):
            self.assertEqual(XApiAdapter()._bearer, "tok")

    def test_publishes_text_and_parses_tweet_id(self) -> None:
        def fake_urlopen(request, timeout):  # noqa: ANN001
            self.assertEqual(request.full_url, "https://api.x.com/2/tweets")
            self.assertEqual(request.method, "POST")
            self.assertIn("Bearer tok", request.get_header("Authorization"))
            body = json.loads(request.data.decode("utf-8"))
            self.assertEqual(body["text"], "olá mundo")
            return FakeResponse({"data": {"id": "123456"}})

        adapter = XApiAdapter(bearer_token="tok")
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = adapter.publish({"text": "olá mundo", "channel": "x", "id": "p1"})
        self.assertEqual(result.url, "https://x.com/i/status/123456")

    def test_http_error_typed(self) -> None:
        from urllib.error import HTTPError

        error = HTTPError("https://api.x.com/2/tweets", 403, "Forbidden", {}, None)
        adapter = XApiAdapter(bearer_token="tok")
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(ChannelAdapterError):
                adapter.publish({"text": "olá", "channel": "x", "id": "p1"})


class LinkedInApiAdapterTests(unittest.TestCase):
    def test_requires_credentials(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            adapter = LinkedInApiAdapter()
            with self.assertRaises(ChannelAdapterError):
                adapter.publish({"text": "olá", "channel": "linkedin", "id": "p1"})

    def test_publishes_community_post_payload(self) -> None:
        captured = {}

        def fake_urlopen(request, timeout):  # noqa: ANN001
            captured["url"] = request.full_url
            captured["headers"] = {k: v for k, v in request.header_items()}
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse({"id": "urn:li:share:777"})

        adapter = LinkedInApiAdapter(bearer_token="tok",
                                     author_urn="urn:li:organization:123")
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = adapter.publish(
                {"text": "post de teste", "channel": "linkedin", "id": "p1"})
        self.assertEqual(captured["url"], "https://api.linkedin.com/rest/posts")
        # urllib lowercases header names on the wire
        lowered = {k.lower(): v for k, v in captured["headers"].items()}
        self.assertEqual(lowered.get("linkedin-version"), "202607")
        self.assertEqual(lowered.get("x-restli-protocol-version"), "2.0.0")
        self.assertEqual(captured["body"]["author"], "urn:li:organization:123")
        self.assertEqual(captured["body"]["lifecycleState"], "PUBLISHED")
        self.assertEqual(captured["body"]["commentary"], "post de teste")
        self.assertEqual(result.url, "urn:li:share:777")


class BlueskyApiAdapterTests(unittest.TestCase):
    def test_requires_credentials(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            adapter = BlueskyApiAdapter()
            with self.assertRaises(ChannelAdapterError):
                adapter.publish({"text": "olá", "channel": "bluesky", "id": "p1"})

    def test_session_then_create_record(self) -> None:
        calls = []

        def fake_urlopen(request, timeout):  # noqa: ANN001
            calls.append(request.full_url)
            if request.full_url.endswith("com.atproto.server.createSession"):
                body = json.loads(request.data.decode("utf-8"))
                self.assertEqual(body["identifier"], "user.bsky.social")
                self.assertEqual(body["password"], "app-pass")
                return FakeResponse({"accessJwt": "jwt123", "handle": "user.bsky.social"})
            body = json.loads(request.data.decode("utf-8"))
            self.assertEqual(body["repo"], "user.bsky.social")
            self.assertEqual(body["collection"], "app.bsky.feed.post")
            self.assertEqual(body["record"]["text"], "olá bluesky")
            self.assertEqual(request.get_header("Authorization"), "Bearer jwt123")
            return FakeResponse({"uri": "at://user.bsky.social/app.bsky.feed.post/abc"})

        adapter = BlueskyApiAdapter(handle="user.bsky.social", app_password="app-pass")
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = adapter.publish({"text": "olá bluesky", "channel": "bluesky",
                                      "id": "p1"})
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0].endswith("com.atproto.server.createSession"))
        self.assertTrue(calls[1].endswith("com.atproto.repo.createRecord"))
        self.assertEqual(result.url, "at://user.bsky.social/app.bsky.feed.post/abc")

    def test_session_failure_typed(self) -> None:
        def fake_urlopen(request, timeout):  # noqa: ANN001
            return FakeResponse({"error": "AuthenticationRequired"})

        adapter = BlueskyApiAdapter(handle="h", app_password="p")
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with self.assertRaises(ChannelAdapterError):
                adapter.publish({"text": "olá", "channel": "bluesky", "id": "p1"})


class RegistryTests(unittest.TestCase):
    def test_real_adapters_registered(self) -> None:
        register_default_adapters()
        for name in ("x_api", "linkedin_api", "bluesky_api"):
            self.assertEqual(get_adapter(name).name, name)

    def test_local_still_default_and_real_apis_unknown_names_fail(self) -> None:
        from geos.domains.social import SocialError

        self.assertEqual(get_adapter("local").name, "local")
        with self.assertRaises(SocialError):
            get_adapter("tiktok_api")  # not registered


if __name__ == "__main__":
    unittest.main()
