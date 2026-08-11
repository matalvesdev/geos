"""Model providers (spec §35): ModelProvider protocol + OpenAI-compatible chat provider.

Zero-dependency (stdlib `urllib`). Cloud or local OpenAI-compatible endpoints
(OpenAI, Azure OpenAI, vLLM/Ollama, ...). Models are replaceable; organizational
knowledge is not (GEOS principle #21). Deterministic callers pass the retrieved
context explicitly and keep provenance — providers never fetch data themselves.
"""

from __future__ import annotations

import http.client
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


class ModelError(Exception):
    """Raised when a model provider fails (network, auth, malformed response)."""


@dataclass
class ModelResponse:
    text: str
    model: str
    provider: str
    finish_reason: str = "stop"
    usage: dict[str, Any] | None = None
    latency_ms: int | None = None
    mock: bool = False


class ModelProvider(Protocol):
    def complete(self, system: str, user: str, temperature: float = 0.2,
                 max_tokens: int | None = None) -> ModelResponse: ...
    def model(self) -> str: ...
    def metadata(self) -> dict[str, Any]: ...


class OpenAICompatibleModelProvider:
    """OpenAI-compatible chat completions behind the ModelProvider protocol.

    stdlib `urllib` only — no SDK dependency. API key from constructor or the
    GEOS_OPENAI_API_KEY / OPENAI_API_KEY env vars. Endpoint configurable, so
    OpenAI, Azure OpenAI and local OpenAI-compatible servers work the same way.
    """

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o-mini",
                 endpoint: str = "https://api.openai.com/v1/chat/completions",
                 timeout_s: int = 60, temperature: float = 0.2) -> None:
        self._api_key = (api_key or os.environ.get("GEOS_OPENAI_API_KEY")
                         or os.environ.get("OPENAI_API_KEY"))
        if not self._api_key:
            raise ModelError(
                "OpenAICompatibleModelProvider requires an API key "
                "(constructor or GEOS_OPENAI_API_KEY/OPENAI_API_KEY env vars)"
            )
        self._model = model
        self._endpoint = endpoint
        self._timeout_s = timeout_s
        self._temperature = temperature

    def complete(self, system: str, user: str, temperature: float | None = None,
                 max_tokens: int | None = None) -> ModelResponse:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self._temperature if temperature is None else temperature,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        request = urllib.request.Request(
            self._endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self._api_key}"},
            method="POST",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
            raise ModelError(f"model HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError,
                http.client.HTTPException) as exc:
            # http.client.IncompleteRead/BadStatusLine etc. are HTTPException,
            # not OSError — all become typed errors (never leak raw exceptions).
            reason = getattr(exc, "reason", exc)
            raise ModelError(f"model network error: {reason}") from exc
        except json.JSONDecodeError as exc:
            raise ModelError(f"model response is not valid JSON: {exc}") from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        try:
            choice = (payload.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            text = str(message.get("content") or "").strip()
        except (AttributeError, IndexError, KeyError, TypeError) as exc:
            raise ModelError(f"model response shape unexpected: {exc}") from exc
        if not text:
            raise ModelError("model returned empty content")
        usage = payload.get("usage")
        return ModelResponse(
            text=text, model=self._model, provider="openai",
            finish_reason=str(choice.get("finish_reason") or "stop"),
            usage=dict(usage) if isinstance(usage, dict) else None,
            latency_ms=latency_ms,
        )

    def model(self) -> str:
        return self._model

    def metadata(self) -> dict[str, Any]:
        return {"provider": "openai", "model": self._model,
                "endpoint": self._endpoint}


def provider_from_config(model_cfg: dict[str, Any] | None) -> ModelProvider | None:
    """Build the model provider from the `models` config section.

    provider: "none" (default — deterministic mock synthesis) | "openai"
    (OpenAI-compatible API; key via env GEOS_OPENAI_API_KEY/OPENAI_API_KEY).
    Options pass through to the provider constructor.
    """
    cfg = dict(model_cfg or {})
    kind = str(cfg.get("provider") or "none").lower()
    if kind in ("none", "", "null"):
        return None
    options = dict(cfg.get("options") or {})
    if kind == "openai":
        return OpenAICompatibleModelProvider(**options)
    raise ModelError(f"unknown model provider {kind!r} (expected 'none' or 'openai')")
