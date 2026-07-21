"""Gateway-backed ModelProvider implementation.

Delegates all LLM calls to the ``llm-gateway`` service over HTTP.
This is the default implementation used by all non-gateway services
(chat-orchestrator, assessment, agent-reasoning, etc.).

Injecting this class via dependency injection allows tests to substitute
a ``MockModelProvider`` without touching HTTP or any SDK.

Usage::

    from libs.model.src.gateway_provider import GatewayModelProvider

    provider = GatewayModelProvider()
    response = await provider.complete("Explain Python decorators.")
"""
from __future__ import annotations

import os
from typing import AsyncIterator, Any

import httpx

try:
    from provider import ModelProvider  # when libs/model/src/ is in PYTHONPATH
except ImportError:
    from libs.model.src.provider import ModelProvider  # when /app is in PYTHONPATH

_LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://llm-gateway:8004")
_DEFAULT_MODEL    = os.getenv("LLM_DEFAULT_MODEL", "claude-sonnet-4-5")
_TIMEOUT          = float(os.getenv("LLM_GATEWAY_TIMEOUT", "120"))


class GatewayModelProvider(ModelProvider):
    """Routes all model calls through the llm-gateway microservice.

    Supports single-shot completions, streaming, and embeddings.
    Uses ``SERVICE_INTERNAL_TOKEN`` for inter-service auth when set.
    """

    name = "gateway"

    def __init__(
        self,
        base_url: str = _LLM_GATEWAY_URL,
        model: str = _DEFAULT_MODEL,
        token: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._token = token or os.getenv("SERVICE_INTERNAL_TOKEN", "")

    def _auth_headers(self) -> dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}",
                    "X-Service-Name": os.getenv("SERVICE_NAME", "ai-tutor-service")}
        return {}

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "model": kwargs.get("model", self._model),
            "max_tokens": kwargs.get("max_tokens", 1024),
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{self._base_url}/api/internal/llm/complete",
                json=payload,
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("content") or data.get("choices", [{}])[0].get("message", {}).get("content", "")

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "model": kwargs.get("model", self._model),
            "max_tokens": kwargs.get("max_tokens", 1024),
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/internal/llm/stream",
                json=payload,
                headers=self._auth_headers(),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        yield line[6:]

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        payload = {"texts": texts, "model": model or "text-embedding-ada-002"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self._base_url}/api/internal/llm/embed",
                json=payload,
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            return resp.json().get("embeddings", [])
