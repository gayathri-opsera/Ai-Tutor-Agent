"""Azure OpenAI provider adapter (circuit-breaker fallback)."""
from __future__ import annotations

import json
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

_TIER_TO_DEPLOYMENT: dict[ModelTier, str] = {
    ModelTier.SMALL: "gpt-4o-mini",
    ModelTier.STANDARD: "gpt-4o",
    ModelTier.LARGE: "gpt-4o",
    ModelTier.EMBEDDING: "text-embedding-ada-002",
}


class AzureOpenAIProvider(LLMProvider):
    """Azure OpenAI adapter.

    Azure uses a different URL structure:
      POST {endpoint}/openai/deployments/{deployment}/chat/completions?api-version={version}
    """

    name = "azure"

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        api_version: str | None = None,
        deployment: str | None = None,
        timeout: float | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key or settings.azure_openai_api_key
        self._endpoint = (endpoint or settings.azure_openai_endpoint).rstrip("/")
        self._api_version = api_version or settings.azure_openai_api_version
        self._default_deployment = deployment or settings.azure_openai_deployment
        self._timeout = timeout or settings.request_timeout_seconds
        self._http_client = http_client

    def resolve_model(self, tier: str) -> str:
        return _TIER_TO_DEPLOYMENT.get(ModelTier(tier), self._default_deployment)

    def _deployment_url(self, deployment: str) -> str:
        return (
            f"{self._endpoint}/openai/deployments/{deployment}"
            f"/chat/completions?api-version={self._api_version}"
        )

    def _embed_url(self, deployment: str) -> str:
        return (
            f"{self._endpoint}/openai/deployments/{deployment}"
            f"/embeddings?api-version={self._api_version}"
        )

    def _get_client(self) -> httpx.AsyncClient:
        if self._http_client:
            return self._http_client
        return httpx.AsyncClient(
            headers={
                "api-key": self._api_key,
                "Content-Type": "application/json",
            },
            timeout=self._timeout,
        )

    def _build_payload(self, request: CompletionRequest, stream: bool) -> tuple[str, dict]:
        deployment = self.resolve_model(request.model_tier)
        payload = {
            "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": stream,
        }
        return deployment, payload

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        deployment, payload = self._build_payload(request, stream=False)
        url = self._deployment_url(deployment)

        client = self._get_client()
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
        finally:
            if not self._http_client:
                await client.aclose()

        data = resp.json()
        choice = data["choices"][0]
        usage = data.get("usage", {})
        input_tok = usage.get("prompt_tokens", 0)
        output_tok = usage.get("completion_tokens", 0)
        model_name = data.get("model", deployment)

        return CompletionResponse(
            request_id=request.request_id or str(uuid.uuid4()),
            provider=self.name,
            model_used=model_name,
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
            estimated_cost_usd=estimate_cost(model_name, input_tok, output_tok),
        )

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        deployment, payload = self._build_payload(request, stream=True)
        url = self._deployment_url(deployment)
        request_id = request.request_id or str(uuid.uuid4())
        total_output = 0

        client = self._get_client()
        try:
            async with client.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload_str = line[len("data: "):]
                    if payload_str.strip() == "[DONE]":
                        break
                    chunk_data = json.loads(payload_str)
                    delta = chunk_data["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    finish_reason = chunk_data["choices"][0].get("finish_reason")
                    model_name = chunk_data.get("model", deployment)
                    total_output += len(content.split())

                    usage_data = None
                    cost = None
                    if finish_reason:
                        usage_data = UsageStats(
                            token_count_input=0,
                            token_count_output=total_output,
                            total_tokens=total_output,
                        )
                        cost = estimate_cost(model_name, 0, total_output)

                    yield StreamChunk(
                        request_id=request_id,
                        provider=self.name,
                        model_used=model_name,
                        delta=content,
                        finish_reason=finish_reason,
                        usage=usage_data,
                        estimated_cost_usd=cost,
                    )
        finally:
            if not self._http_client:
                await client.aclose()

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        deployment = model or "text-embedding-ada-002"
        url = self._embed_url(deployment)
        payload = {"input": texts}

        client = self._get_client()
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
        finally:
            if not self._http_client:
                await client.aclose()

        data = resp.json()
        return [item["embedding"] for item in data["data"]]
