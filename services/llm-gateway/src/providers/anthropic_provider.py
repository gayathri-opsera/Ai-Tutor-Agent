"""Anthropic Claude provider adapter."""
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

_ANTHROPIC_API_BASE = "https://api.anthropic.com/v1"
_ANTHROPIC_VERSION  = "2023-06-01"

# Anthropic model tier mapping — using latest available models
_TIER_TO_MODEL: dict[ModelTier, str] = {
    ModelTier.SMALL:     "claude-haiku-4-5",
    ModelTier.STANDARD:  "claude-sonnet-4-5",
    ModelTier.LARGE:     "claude-sonnet-5",
    ModelTier.EMBEDDING: "claude-haiku-4-5",
}


class AnthropicProvider(LLMProvider):
    """Adapter for the Anthropic Messages API (claude-* family)."""

    name = "anthropic"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key  = api_key  or settings.anthropic_api_key
        self._timeout  = timeout  or settings.request_timeout_seconds
        self._http_client = http_client

    def resolve_model(self, tier: str) -> str:
        return _TIER_TO_MODEL.get(ModelTier(tier), "claude-sonnet-5")

    def _get_client(self) -> httpx.AsyncClient:
        if self._http_client:
            return self._http_client
        return httpx.AsyncClient(
            base_url=_ANTHROPIC_API_BASE,
            headers={
                "x-api-key":         self._api_key,
                "anthropic-version": _ANTHROPIC_VERSION,
                "content-type":      "application/json",
            },
            timeout=self._timeout,
        )

    def _build_payload(self, request: CompletionRequest, stream: bool) -> dict:
        """Convert internal CompletionRequest → Anthropic Messages API format.

        The Anthropic API expects:
          - system prompt extracted from messages with role='system'
          - messages list with only 'user' / 'assistant' roles
        """
        model = self.resolve_model(request.model_tier)

        system_parts: list[str] = []
        user_messages: list[dict] = []

        for msg in request.messages:
            if msg.role.value == "system":
                system_parts.append(msg.content)
            else:
                user_messages.append({"role": msg.role.value, "content": msg.content})

        payload: dict = {
            "model":      model,
            "max_tokens": request.max_tokens or 4096,
            "messages":   user_messages or [{"role": "user", "content": "Hello"}],
            "stream":     stream,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        return payload

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        payload = self._build_payload(request, stream=False)
        model   = payload["model"]

        client = self._get_client()
        try:
            resp = await client.post("/messages", json=payload)
            resp.raise_for_status()
        finally:
            if not self._http_client:
                await client.aclose()

        data    = resp.json()
        content = data["content"][0]["text"] if data.get("content") else ""
        usage   = data.get("usage", {})
        input_tok  = usage.get("input_tokens",  0)
        output_tok = usage.get("output_tokens", 0)

        return CompletionResponse(
            request_id=request.request_id or str(uuid.uuid4()),
            provider=self.name,
            model_used=model,
            choices=[
                CompletionChoice(
                    index=0,
                    message_role="assistant",
                    message_content=content,
                    finish_reason=data.get("stop_reason"),
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
        """Stream via Anthropic SSE protocol.

        Anthropic SSE events of interest:
          content_block_delta  → carries text delta
          message_delta        → carries stop_reason + output token count
          message_stop         → signals end of stream
        """
        payload    = self._build_payload(request, stream=True)
        model      = payload["model"]
        request_id = request.request_id or str(uuid.uuid4())
        input_tok  = 0
        output_tok = 0

        client = self._get_client()
        try:
            async with client.stream("POST", "/messages", json=payload) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    import logging as _log
                    _log.getLogger(__name__).error(
                        "Anthropic %d: %s | payload model=%s msgs=%d",
                        resp.status_code, body.decode()[:300],
                        payload.get("model"), len(payload.get("messages", []))
                    )
                resp.raise_for_status()
                async for raw_line in resp.aiter_lines():
                    if not raw_line or raw_line.startswith(":"):
                        continue

                    if raw_line.startswith("data: "):
                        data_str = raw_line[len("data: "):]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            event_data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        event_type = event_data.get("type", "")

                        if event_type == "message_start":
                            usage = event_data.get("message", {}).get("usage", {})
                            input_tok = usage.get("input_tokens", 0)

                        elif event_type == "content_block_delta":
                            delta_obj = event_data.get("delta", {})
                            delta_text = delta_obj.get("text", "") if delta_obj.get("type") == "text_delta" else ""
                            if delta_text:
                                yield StreamChunk(
                                    request_id=request_id,
                                    provider=self.name,
                                    model_used=model,
                                    delta=delta_text,
                                    finish_reason=None,
                                    usage=None,
                                    estimated_cost_usd=None,
                                )

                        elif event_type == "message_delta":
                            delta_obj  = event_data.get("delta", {})
                            usage_obj  = event_data.get("usage", {})
                            output_tok = usage_obj.get("output_tokens", output_tok)
                            stop_reason = delta_obj.get("stop_reason")

                            if stop_reason:
                                yield StreamChunk(
                                    request_id=request_id,
                                    provider=self.name,
                                    model_used=model,
                                    delta="",
                                    finish_reason=stop_reason,
                                    usage=UsageStats(
                                        token_count_input=input_tok,
                                        token_count_output=output_tok,
                                        total_tokens=input_tok + output_tok,
                                    ),
                                    estimated_cost_usd=estimate_cost(model, input_tok, output_tok),
                                )
        finally:
            if not self._http_client:
                await client.aclose()

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """Anthropic has no native embedding endpoint.

        Falls back to a simple mean-pool of token IDs as a stub so the service
        starts without crashing. For real embeddings, set EMBEDDING_BACKEND=openai_gateway
        and point it at the LLM Gateway with an OpenAI key.
        """
        raise NotImplementedError(
            "Anthropic does not provide an embeddings endpoint. "
            "Set EMBEDDING_BACKEND=openai_gateway or sentence_transformers in your .env."
        )
