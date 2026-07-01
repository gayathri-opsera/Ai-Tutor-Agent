"""Unit tests for provider adapters (OpenAI, Azure OpenAI, Ollama).

Uses httpx transport mocking to avoid real network calls.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from httpx import Response

from src.providers.azure_openai_provider import AzureOpenAIProvider
from src.providers.ollama_provider import OllamaProvider
from src.providers.openai_provider import OpenAIProvider
from src.schemas.request import CompletionRequest, Message, MessageRole, ModelTier

FIXTURES = Path(__file__).parent.parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def make_request(tier: ModelTier = ModelTier.STANDARD) -> CompletionRequest:
    return CompletionRequest(
        model_tier=tier,
        messages=[Message(role=MessageRole.USER, content="Explain photosynthesis.")],
        temperature=0.5,
        max_tokens=100,
        request_id="test-req-001",
    )


# ── OpenAI Provider ──────────────────────────────────────────────────────────

class TestOpenAIProviderModelResolution:
    def test_resolve_standard_tier(self):
        p = OpenAIProvider(api_key="fake")
        assert p.resolve_model("standard") == "gpt-4o-mini"

    def test_resolve_small_tier(self):
        p = OpenAIProvider(api_key="fake")
        assert p.resolve_model("small") == "gpt-4o-mini"

    def test_resolve_embedding_tier(self):
        p = OpenAIProvider(api_key="fake")
        assert p.resolve_model("embedding") == "text-embedding-ada-002"


class TestOpenAIProviderComplete:
    @pytest.mark.asyncio
    async def test_successful_completion(self):
        fixture = load_fixture("openai_response.json")
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = fixture
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        provider = OpenAIProvider(api_key="fake", http_client=mock_client)
        result = await provider.complete(make_request())

        assert result.provider == "openai"
        assert result.model_used == "gpt-4o-mini"
        assert result.usage.token_count_input == 15
        assert result.usage.token_count_output == 14
        assert result.choices[0].message_content != ""
        assert result.estimated_cost_usd > 0

    @pytest.mark.asyncio
    async def test_propagates_http_error(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        error_resp = httpx.Response(500, content=b'{"error": "server error"}')
        mock_client.post = AsyncMock(side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=error_resp))

        provider = OpenAIProvider(api_key="fake", http_client=mock_client)
        with pytest.raises(httpx.HTTPStatusError):
            await provider.complete(make_request())


class TestOpenAIProviderStream:
    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self):
        stream_lines = (FIXTURES / "openai_stream_chunks.txt").read_text().split("\n")

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.raise_for_status = MagicMock()

        async def fake_lines():
            for line in stream_lines:
                if line:
                    yield line

        mock_resp.aiter_lines = fake_lines
        mock_client.stream = MagicMock(return_value=mock_resp)

        provider = OpenAIProvider(api_key="fake", http_client=mock_client)
        chunks = []
        async for chunk in provider.stream(make_request()):
            chunks.append(chunk)

        assert len(chunks) > 0
        assert any(c.delta for c in chunks)
        final = [c for c in chunks if c.finish_reason == "stop"]
        assert len(final) == 1


# ── Azure OpenAI Provider ────────────────────────────────────────────────────

class TestAzureOpenAIProviderModelResolution:
    def test_resolve_standard_uses_default_deployment(self):
        p = AzureOpenAIProvider(
            api_key="fake",
            endpoint="https://myazure.openai.azure.com",
            deployment="gpt-4o",
        )
        assert p.resolve_model("standard") == "gpt-4o"

    def test_resolve_large_tier(self):
        p = AzureOpenAIProvider(
            api_key="fake",
            endpoint="https://myazure.openai.azure.com",
        )
        assert p.resolve_model("large") == "gpt-4o"


class TestAzureOpenAIProviderComplete:
    @pytest.mark.asyncio
    async def test_successful_completion(self):
        fixture = load_fixture("azure_openai_response.json")
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = fixture
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        provider = AzureOpenAIProvider(
            api_key="fake",
            endpoint="https://myazure.openai.azure.com",
            http_client=mock_client,
        )
        result = await provider.complete(make_request())

        assert result.provider == "azure"
        assert result.usage.token_count_input == 12
        assert result.usage.token_count_output == 10

    @pytest.mark.asyncio
    async def test_propagates_http_error(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        error_resp = httpx.Response(500, content=b'{"error": "azure error"}')
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=error_resp)
        )
        provider = AzureOpenAIProvider(
            api_key="fake",
            endpoint="https://myazure.openai.azure.com",
            http_client=mock_client,
        )
        with pytest.raises(httpx.HTTPStatusError):
            await provider.complete(make_request())


# ── Ollama Provider ──────────────────────────────────────────────────────────

class TestOllamaProviderModelResolution:
    def test_resolve_small_tier(self):
        p = OllamaProvider()
        assert p.resolve_model("small") == "llama3.2:3b"

    def test_resolve_standard_tier(self):
        p = OllamaProvider()
        assert p.resolve_model("standard") == "llama3.2"

    def test_resolve_embedding_tier(self):
        p = OllamaProvider()
        assert p.resolve_model("embedding") == "nomic-embed-text"


class TestOllamaProviderComplete:
    @pytest.mark.asyncio
    async def test_successful_completion(self):
        ollama_response = {
            "model": "llama3.2",
            "message": {"role": "assistant", "content": "Photosynthesis converts light into energy."},
            "done": True,
            "eval_count": 8,
            "prompt_eval_count": 5,
        }
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock()
        mock_resp.json.return_value = ollama_response
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        provider = OllamaProvider(http_client=mock_client)
        result = await provider.complete(make_request())

        assert result.provider == "ollama"
        assert result.estimated_cost_usd == 0.0
        assert result.usage.token_count_output == 8
        assert result.usage.token_count_input == 5
