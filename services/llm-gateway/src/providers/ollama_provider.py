"""Ollama provider adapter (local dev / offline mode)."""
from __future__ import annotations

import json
import uuid
from typing import AsyncIterator

import httpx

from src.config import settings
from src.providers.base import LLMProvider
from src.schemas.request import CompletionRequest, ModelTier
from src.schemas.response import (
    CompletionChoice,
    CompletionResponse,
    StreamChunk,
    UsageStats,
)

_TIER_TO_MODEL: dict[ModelTier, str] = {
    ModelTier.SMALL: "llama3.2:3b",
    ModelTier.STANDARD: "llama3.2",
    ModelTier.LARGE: "llama3.1:70b",
    ModelTier.EMBEDDING: "nomic-embed-text",
}


class OllamaProvider(LLMProvider):
    """Ollama adapter using the /api/chat endpoint.

    Only intended for local development — not for production traffic.
    """

    name = "ollama"

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._timeout = timeout or settings.request_timeout_seconds
        self._http_client = http_client

    def resolve_model(self, tier: str) -> str:
        return _TIER_TO_MODEL.get(ModelTier(tier), "llama3.2")

    def _get_client(self) -> httpx.AsyncClient:
        if self._http_client:
            return self._http_client
        return httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)

    def _build_payload(self, request: CompletionRequest, stream: bool) -> dict:
        model = self.resolve_model(request.model_tier)
        return {
            "model": model,
            "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
            "stream": stream,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        payload = self._build_payload(request, stream=False)
        model = payload["model"]

        client = self._get_client()
        try:
            resp = await client.post("/api/chat", json=payload)
            resp.raise_for_status()
        finally:
            if not self._http_client:
                await client.aclose()

        data = resp.json()
        message = data.get("message", {})
        eval_count = data.get("eval_count", 0)
        prompt_eval_count = data.get("prompt_eval_count", 0)

        return CompletionResponse(
            request_id=request.request_id or str(uuid.uuid4()),
            provider=self.name,
            model_used=model,
            choices=[
                CompletionChoice(
                    index=0,
                    message_role=message.get("role", "assistant"),
                    message_content=message.get("content", ""),
                    finish_reason="stop" if data.get("done") else None,
                )
            ],
            usage=UsageStats(
                token_count_input=prompt_eval_count,
                token_count_output=eval_count,
                total_tokens=prompt_eval_count + eval_count,
            ),
            estimated_cost_usd=0.0,  # local model — no cost
        )

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        payload = self._build_payload(request, stream=True)
        model = payload["model"]
        request_id = request.request_id or str(uuid.uuid4())
        total_output = 0

        client = self._get_client()
        try:
            async with client.stream("POST", "/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    chunk_data = json.loads(line)
                    message = chunk_data.get("message", {})
                    content = message.get("content", "")
                    done = chunk_data.get("done", False)
                    total_output += len(content.split())

                    usage_data = None
                    if done:
                        usage_data = UsageStats(
                            token_count_input=chunk_data.get("prompt_eval_count", 0),
                            token_count_output=chunk_data.get("eval_count", total_output),
                            total_tokens=chunk_data.get("prompt_eval_count", 0)
                            + chunk_data.get("eval_count", total_output),
                        )

                    yield StreamChunk(
                        request_id=request_id,
                        provider=self.name,
                        model_used=model,
                        delta=content,
                        finish_reason="stop" if done else None,
                        usage=usage_data,
                        estimated_cost_usd=0.0 if done else None,
                    )
        finally:
            if not self._http_client:
                await client.aclose()

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        embed_model = model or "nomic-embed-text"
        embeddings: list[list[float]] = []
        client = self._get_client()
        try:
            for text in texts:
                resp = await client.post("/api/embeddings", json={"model": embed_model, "prompt": text})
                resp.raise_for_status()
                embeddings.append(resp.json()["embedding"])
        finally:
            if not self._http_client:
                await client.aclose()
        return embeddings
