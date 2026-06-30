"""Embedding backend that delegates to the LLM Gateway's embed endpoint.

Routes requests through POST /api/internal/llm/completions to the LLM Gateway,
which in turn calls OpenAI's text-embedding-ada-002 (or configured model).
This keeps all provider credentials inside the LLM Gateway — the Embedding
Service never holds API keys.
"""
from __future__ import annotations

import logging

import httpx

from src.config import settings
from src.backends.base import EmbeddingBackend

logger = logging.getLogger(__name__)

_DIMENSIONS: dict[str, int] = {
    "text-embedding-ada-002": 1536,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}

_DEFAULT_MODEL = settings.openai_embedding_model


class OpenAIGatewayBackend(EmbeddingBackend):
    """Calls the LLM Gateway's /embed endpoint.

    The LLM Gateway already handles retries, circuit breaking, and provider
    credentials, so this backend is a thin HTTP wrapper.
    """

    name = "openai_gateway"

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._client = http_client

    def default_model(self) -> str:
        return _DEFAULT_MODEL

    def dimensions_for(self, model: str) -> int:
        return _DIMENSIONS.get(model, 1536)

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        model = model or _DEFAULT_MODEL
        payload = {"texts": texts, "model": model}

        client = self._client or httpx.AsyncClient(
            base_url=settings.llm_gateway_url,
            timeout=settings.llm_gateway_timeout,
        )
        owned = self._client is None
        try:
            resp = await client.post("/api/internal/llm/embed", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["embeddings"]
        finally:
            if owned:
                await client.aclose()
