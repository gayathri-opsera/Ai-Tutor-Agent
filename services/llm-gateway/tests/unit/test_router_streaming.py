"""Unit tests for LLMRouter streaming and fallback paths."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.circuit_breaker.circuit_breaker import CircuitBreaker
from src.kafka.usage_logger import KafkaUsageLogger
from src.middleware.pii_scrubber import PIIScrubber
from src.providers.azure_openai_provider import AzureOpenAIProvider
from src.providers.openai_provider import OpenAIProvider
from src.router import LLMRouter
from src.schemas.request import CompletionRequest, Message, MessageRole, ModelTier
from src.schemas.response import CompletionChoice, CompletionResponse, StreamChunk, UsageStats


def make_request() -> CompletionRequest:
    return CompletionRequest(
        model_tier=ModelTier.STANDARD,
        messages=[Message(role=MessageRole.USER, content="Explain DNA.")],
        request_id="router-stream-001",
    )


def make_stream_chunks(provider="openai"):
    return [
        StreamChunk(request_id="router-stream-001", provider=provider, model_used="gpt-4o", delta="D"),
        StreamChunk(request_id="router-stream-001", provider=provider, model_used="gpt-4o", delta="NA",
                    finish_reason="stop",
                    usage=UsageStats(token_count_input=3, token_count_output=2, total_tokens=5),
                    estimated_cost_usd=0.00003),
    ]


def make_router_with_stream(primary_chunks=None, primary_raises=None, fallback_chunks=None):
    primary = MagicMock(spec=OpenAIProvider)
    primary.name = "openai"

    async def primary_stream(req):
        if primary_raises:
            raise primary_raises
        for c in (primary_chunks or make_stream_chunks("openai")):
            yield c

    primary.stream = primary_stream

    fallback = MagicMock(spec=AzureOpenAIProvider)
    fallback.name = "azure"

    async def fallback_stream(req):
        for c in (fallback_chunks or make_stream_chunks("azure")):
            yield c

    fallback.stream = fallback_stream

    usage_logger = AsyncMock(spec=KafkaUsageLogger)
    usage_logger.log_usage = AsyncMock()

    return LLMRouter(
        primary=primary,
        fallback=fallback,
        circuit_breaker=CircuitBreaker(),
        pii_scrubber=PIIScrubber(),
        usage_logger=usage_logger,
    )


class TestRouterStreaming:
    @pytest.mark.asyncio
    async def test_stream_delivers_chunks(self):
        router = make_router_with_stream()
        chunks = []
        async for chunk in router.stream(make_request()):
            chunks.append(chunk)

        assert len(chunks) == 2
        assert chunks[0].delta == "D"
        assert chunks[1].finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_stream_records_cb_success(self):
        router = make_router_with_stream()
        async for _ in router.stream(make_request()):
            pass

        stats = router.circuit_stats()
        assert stats["window_total"] >= 1
        assert stats["window_failures"] == 0

    @pytest.mark.asyncio
    async def test_stream_fallback_on_5xx(self):
        error_resp = httpx.Response(500, content=b"{}")
        error = httpx.HTTPStatusError("500", request=MagicMock(), response=error_resp)

        router = make_router_with_stream(primary_raises=error)
        chunks = []
        async for chunk in router.stream(make_request()):
            chunks.append(chunk)

        # Should receive fallback chunks (provider=azure)
        providers = {c.provider for c in chunks}
        assert "azure" in providers

    @pytest.mark.asyncio
    async def test_stream_usage_logged_on_final_chunk(self):
        router = make_router_with_stream()
        async for _ in router.stream(make_request()):
            pass

        router._usage_logger.log_usage.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_pii_scrubbed_before_provider(self):
        primary = MagicMock(spec=OpenAIProvider)
        primary.name = "openai"
        received_content = []

        async def capture_stream(req):
            received_content.append(req.messages[0].content)
            yield StreamChunk(request_id="s1", provider="openai", model_used="gpt-4o", delta="ok",
                              finish_reason="stop",
                              usage=UsageStats(token_count_input=1, token_count_output=1, total_tokens=2))

        primary.stream = capture_stream

        fallback = MagicMock(spec=AzureOpenAIProvider)
        fallback.name = "azure"

        usage_logger = AsyncMock(spec=KafkaUsageLogger)
        usage_logger.log_usage = AsyncMock()

        router = LLMRouter(
            primary=primary,
            fallback=fallback,
            circuit_breaker=CircuitBreaker(),
            pii_scrubber=PIIScrubber(),
            usage_logger=usage_logger,
        )

        pii_req = CompletionRequest(
            model_tier=ModelTier.STANDARD,
            messages=[Message(role=MessageRole.USER, content="Email me at user@test.com")],
            request_id="pii-stream-001",
        )
        async for _ in router.stream(pii_req):
            pass

        assert "user@test.com" not in received_content[0]
        assert "[REDACTED-EMAIL]" in received_content[0]
