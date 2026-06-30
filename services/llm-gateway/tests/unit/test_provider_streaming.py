"""Unit tests for provider streaming and embedding methods."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.providers.azure_openai_provider import AzureOpenAIProvider
from src.providers.ollama_provider import OllamaProvider
from src.providers.openai_provider import OpenAIProvider
from src.schemas.request import CompletionRequest, Message, MessageRole, ModelTier

FIXTURES = Path(__file__).parent.parent / "fixtures"

AZURE_SSE_LINES = [
    'data: {"id":"az1","object":"chat.completion.chunk","model":"gpt-4o","choices":[{"index":0,"delta":{"role":"assistant","content":"Hello"},"finish_reason":null}]}',
    'data: {"id":"az1","object":"chat.completion.chunk","model":"gpt-4o","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":"stop"}]}',
    "data: [DONE]",
]

OLLAMA_STREAM_LINES = [
    '{"model":"llama3.2","message":{"role":"assistant","content":"Hi"},"done":false}',
    '{"model":"llama3.2","message":{"role":"assistant","content":" there"},"done":false}',
    '{"model":"llama3.2","message":{"role":"assistant","content":""},"done":true,"eval_count":5,"prompt_eval_count":3}',
]


def make_request() -> CompletionRequest:
    return CompletionRequest(
        model_tier=ModelTier.STANDARD,
        messages=[Message(role=MessageRole.USER, content="Test")],
        request_id="stream-test-001",
    )


# ── Azure OpenAI streaming ───────────────────────────────────────────────────

class TestAzureStreamingProvider:
    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.raise_for_status = MagicMock()

        async def fake_lines():
            for line in AZURE_SSE_LINES:
                if line:
                    yield line

        mock_resp.aiter_lines = fake_lines
        mock_client.stream = MagicMock(return_value=mock_resp)

        provider = AzureOpenAIProvider(
            api_key="fake",
            endpoint="https://test.openai.azure.com",
            http_client=mock_client,
        )
        chunks = []
        async for chunk in provider.stream(make_request()):
            chunks.append(chunk)

        assert len(chunks) >= 1
        assert any(c.delta for c in chunks)
        final = [c for c in chunks if c.finish_reason == "stop"]
        assert len(final) == 1
        assert final[0].usage is not None

    @pytest.mark.asyncio
    async def test_embed_returns_vectors(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [{"embedding": [0.1, 0.2, 0.3]}, {"embedding": [0.4, 0.5, 0.6]}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        provider = AzureOpenAIProvider(
            api_key="fake",
            endpoint="https://test.openai.azure.com",
            http_client=mock_client,
        )
        result = await provider.embed(["Hello world", "Test sentence"])
        assert len(result) == 2
        assert result[0] == [0.1, 0.2, 0.3]


# ── Ollama streaming ─────────────────────────────────────────────────────────

class TestOllamaStreamingProvider:
    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.raise_for_status = MagicMock()

        async def fake_lines():
            for line in OLLAMA_STREAM_LINES:
                yield line

        mock_resp.aiter_lines = fake_lines
        mock_client.stream = MagicMock(return_value=mock_resp)

        provider = OllamaProvider(http_client=mock_client)
        chunks = []
        async for chunk in provider.stream(make_request()):
            chunks.append(chunk)

        assert len(chunks) >= 1
        content = "".join(c.delta for c in chunks)
        assert "Hi" in content
        final = [c for c in chunks if c.finish_reason == "stop"]
        assert len(final) == 1
        assert final[0].usage is not None

    @pytest.mark.asyncio
    async def test_embed_returns_vectors(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"embedding": [0.9, 0.8, 0.7]}
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        provider = OllamaProvider(http_client=mock_client)
        result = await provider.embed(["Hello"])
        assert len(result) == 1
        assert result[0] == [0.9, 0.8, 0.7]


# ── OpenAI embed ─────────────────────────────────────────────────────────────

class TestOpenAIEmbed:
    @pytest.mark.asyncio
    async def test_embed_returns_vectors(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [{"embedding": [0.1, 0.2, 0.3]}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        provider = OpenAIProvider(api_key="fake", http_client=mock_client)
        result = await provider.embed(["Hello"])
        assert len(result) == 1
        assert result[0] == [0.1, 0.2, 0.3]
