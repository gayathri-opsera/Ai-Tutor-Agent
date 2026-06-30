"""OpenAI provider adapter (primary provider)."""
from __future__ import annotations

import uuid
from typing import AsyncIterator

import httpx

from src.config import settings
from src.providers.base import LLMProvider, estimate_cost
from src.schemas.request import CompletionRequest, ModelTier
from src.schemas.response import (
    CompletionChoice,
    CompletionResponse,
    StreamChunk,
    UsageStats,
)

_TIER_TO_MODEL: dict[ModelTier, str] = {
    ModelTier.SMALL: "gpt-4o-mini",
    ModelTier.STANDARD: "gpt-4o",
    ModelTier.LARGE: "gpt-4o",
    ModelTier.EMBEDDING: "text-embedding-ada-002",
}


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        timeout: float | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key or settings.openai_api_key
        self._api_base = (api_base or settings.openai_api_base).rstrip("/")
        self._timeout = timeout or settings.request_timeout_seconds
        # Allow injecting a custom client for testing
        self._http_client = http_client

    def resolve_model(self, tier: str) -> str:
        return _TIER_TO_MODEL.get(ModelTier(tier), "gpt-4o")

    def _get_client(self) -> httpx.AsyncClient:
        if self._http_client:
            return self._http_client
        return httpx.AsyncClient(
            base_url=self._api_base,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=self._timeout,
        )

    def _build_payload(self, request: CompletionRequest, stream: bool) -> dict:
        model = self.resolve_model(request.model_tier)
        return {
            "model": model,
            "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": stream,
        }

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        payload = self._build_payload(request, stream=False)
        model = payload["model"]

        client = self._get_client()
        try:
            resp = await client.post("/chat/completions", json=payload)
            resp.raise_for_status()
        finally:
            if not self._http_client:
                await client.aclose()

        data = resp.json()
        choice = data["choices"][0]
        usage = data.get("usage", {})
        input_tok = usage.get("prompt_tokens", 0)
        output_tok = usage.get("completion_tokens", 0)

        return CompletionResponse(
            request_id=request.request_id or str(uuid.uuid4()),
            provider=self.name,
            model_used=model,
            choices=[
                CompletionChoice(
                    index=0,
                    message_role=choice["message"]["role"],
                    message_content=choice["message"]["content"],
                    finish_reason=choice.get("finish_reason"),
                )
            ],
            usage=UsageStats(
                token_count_input=input_tok,
                token_count_output=output_tok,
                total_tokens=input_tok + output_tok,
            ),
            estimated_cost_usd=estimate_cost(model, input_tok, output_tok),
        )

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        payload = self._build_payload(request, stream=True)
        model = payload["model"]
        request_id = request.request_id or str(uuid.uuid4())
        total_output = 0

        client = self._get_client()
        try:
            async with client.stream("POST", "/chat/completions", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload_str = line[len("data: "):]
                    if payload_str.strip() == "[DONE]":
                        break
                    import json
                    chunk_data = json.loads(payload_str)
                    delta = chunk_data["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    finish_reason = chunk_data["choices"][0].get("finish_reason")
                    total_output += len(content.split())  # rough token count

                    usage_data = None
                    cost = None
                    if finish_reason:
                        usage_data = UsageStats(
                            token_count_input=0,
                            token_count_output=total_output,
                            total_tokens=total_output,
                        )
                        cost = estimate_cost(model, 0, total_output)

                    yield StreamChunk(
                        request_id=request_id,
                        provider=self.name,
                        model_used=model,
                        delta=content,
                        finish_reason=finish_reason,
                        usage=usage_data,
                        estimated_cost_usd=cost,
                    )
        finally:
            if not self._http_client:
                await client.aclose()

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        embed_model = model or "text-embedding-ada-002"
        payload = {"model": embed_model, "input": texts}

        client = self._get_client()
        try:
            resp = await client.post("/embeddings", json=payload)
            resp.raise_for_status()
        finally:
            if not self._http_client:
                await client.aclose()

        data = resp.json()
        return [item["embedding"] for item in data["data"]]
