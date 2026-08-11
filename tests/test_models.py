"""SPEC-039 model provider tests."""

from __future__ import annotations

import json
import unittest
import urllib.error
from unittest import mock

from geos.core.models import (
    ModelError,
    OpenAICompatibleModelProvider,
    ModelResponse,
    provider_from_config,
)
from geos.domains.research import ResearchEngine
from geos.intelligence.knowledge import ingest_directory
from tests.helpers import TempDir, temp_db


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


def _chat_payload(text: str, model: str = "mock-model") -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": text},
                     "finish_reason": "stop"}],
        "model": model,
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


class FakeModelProvider:
    """Deterministic ModelProvider double for research tests."""

    def __init__(self, text: str = "Síntese real [F1] com citação.", model: str = "fake") -> None:
        self._text = text
        self._model = model

    def complete(self, system: str, user: str, temperature: float = 0.2,
                 max_tokens: int | None = None) -> ModelResponse:
        return ModelResponse(text=self._text, model=self._model, provider="fake")

    def model(self) -> str:
        return self._model

    def metadata(self) -> dict:
        return {"provider": "fake", "model": self._model}


class FailingModelProvider(FakeModelProvider):
    def complete(self, system: str, user: str, temperature: float = 0.2,
                 max_tokens: int | None = None) -> ModelResponse:
        raise ModelError("boom")


class EmptyTextModelProvider(FakeModelProvider):
    """Returns empty text without raising — must still trigger the mock fallback."""

    def complete(self, system: str, user: str, temperature: float = 0.2,
                 max_tokens: int | None = None) -> ModelResponse:
        return ModelResponse(text="   ", model="fake", provider="fake")


class OpenAICompatibleProviderTests(unittest.TestCase):
    def _provider(self, **kwargs) -> OpenAICompatibleModelProvider:
        return OpenAICompatibleModelProvider(api_key="test-key", model="mock-model",
                                             endpoint="https://example.test/v1/chat/completions",
                                             timeout_s=5, **kwargs)

    def test_complete_parses_response(self) -> None:
        provider = self._provider()
        with mock.patch("urllib.request.urlopen",
                        return_value=FakeResponse(_chat_payload("Olá!"))) as urlopen:
            response = provider.complete("sys", "user")
        self.assertEqual(response.text, "Olá!")
        self.assertEqual(response.model, "mock-model")
        self.assertEqual(response.usage["total_tokens"], 15)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        body = json.loads(request.data)
        self.assertEqual(body["messages"][0]["content"], "sys")

    def test_requires_api_key(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ModelError):
                OpenAICompatibleModelProvider(api_key=None)

    def test_http_error_typed(self) -> None:
        provider = self._provider()
        error = urllib.error.HTTPError("https://example.test", 401, "unauthorized", {}, None)
        error.read = lambda: b'{"error": "bad key"}'  # type: ignore[method-assign]
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(ModelError) as ctx:
                provider.complete("s", "u")
        self.assertIn("401", str(ctx.exception))

    def test_timeout_typed(self) -> None:
        provider = self._provider()
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaises(ModelError) as ctx:
                provider.complete("s", "u")
        self.assertIn("timed out", str(ctx.exception))

    def test_empty_content_raises(self) -> None:
        provider = self._provider()
        with mock.patch("urllib.request.urlopen",
                        return_value=FakeResponse(_chat_payload("  "))):
            with self.assertRaises(ModelError):
                provider.complete("s", "u")

    def test_factory(self) -> None:
        self.assertIsNone(provider_from_config(None))
        self.assertIsNone(provider_from_config({"provider": "none"}))
        with mock.patch.dict("os.environ", {"GEOS_OPENAI_API_KEY": "k"}, clear=True):
            p = provider_from_config({"provider": "openai", "options": {"model": "m"}})
        self.assertIsInstance(p, OpenAICompatibleModelProvider)
        self.assertEqual(p.model(), "m")
        with self.assertRaises(ModelError):
            provider_from_config({"provider": "weird"})


class ResearchSynthesisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()

    def tearDown(self) -> None:
        self.db.close()

    def _ingest(self) -> None:
        with TempDir() as tmp:
            (tmp / "docs").mkdir()
            (tmp / "docs" / "origem.md").write_text(
                "# Origem de crédito\n\nA origem de crédito bancário é essencial "
                "para a decisão financeira. Conciliação com evidência documental "
                "é o processo central.\n",
                encoding="utf-8",
            )
            ingest_directory(self.db, tmp / "docs", source="test")

    def test_mock_by_default(self) -> None:
        self._ingest()
        report = ResearchEngine(self.db).run("origem de crédito")
        self.assertTrue(report.mock)
        self.assertIsNone(report.model)
        self.assertIn("mock", report.synthesis)

    def test_model_synthesis_with_citations(self) -> None:
        self._ingest()
        provider = FakeModelProvider("Síntese real [F1] sobre origem de crédito.")
        report = ResearchEngine(self.db, model_provider=provider).run("origem de crédito")
        self.assertFalse(report.mock)
        self.assertEqual(report.model, "fake")
        self.assertEqual(report.provider, "fake")
        self.assertIn("[F1]", report.synthesis)
        # persisted with provenance
        row = self.db.conn_checked.execute(
            "SELECT model, provider, mock FROM research ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(row["model"], "fake")
        self.assertEqual(row["mock"], 0)

    def test_model_failure_falls_back_to_mock(self) -> None:
        self._ingest()
        report = ResearchEngine(self.db, model_provider=FailingModelProvider()).run(
            "origem de crédito"
        )
        self.assertTrue(report.mock)
        self.assertIsNone(report.model)
        self.assertIn("mock", report.synthesis)

    def test_empty_model_text_falls_back_to_mock(self) -> None:
        """Regression (SPEC-039 R3): empty text must not fail the research."""
        self._ingest()
        report = ResearchEngine(self.db, model_provider=EmptyTextModelProvider()).run(
            "origem de crédito"
        )
        self.assertTrue(report.mock)
        self.assertIsNone(report.model)
        self.assertIn("mock", report.synthesis)
        self.assertEqual(report.status, "COMPLETED")

    def test_empty_retrieval_stays_honest(self) -> None:
        report = ResearchEngine(self.db, model_provider=FakeModelProvider()).run(
            "nada indexado ainda"
        )
        self.assertTrue(report.mock)
        self.assertTrue(report.empty)
        self.assertIn("nenhuma fonte foi inventada", report.synthesis)


if __name__ == "__main__":
    unittest.main()
