"""Unit tests for OpenAIGatewayBackend — mocked HTTP calls."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.backends.openai_gateway import OpenAIGatewayBackend


def _make_mock_response(embeddings: list) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"embeddings": embeddings}
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _mock_client(embeddings: list) -> AsyncMock:
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(return_value=_make_mock_response(embeddings))
    client.aclose = AsyncMock()
    return client


class TestOpenAIGatewayBackend:
    @pytest.mark.asyncio
    async def test_embed_calls_gateway_endpoint(self):
        expected = [[0.1] * 1536]
        client = _mock_client(expected)
        backend = OpenAIGatewayBackend(http_client=client)
        result = await backend.embed(["hello"])
        client.post.assert_called_once()
        call_args = client.post.call_args
        assert "/api/internal/llm/embed" in str(call_args)

    @pytest.mark.asyncio
    async def test_returns_embeddings_from_response(self):
        expected = [[0.1, 0.2, 0.3] * 512]
        client = _mock_client(expected)
        backend = OpenAIGatewayBackend(http_client=client)
        result = await backend.embed(["test text"])
        assert result == expected

    @pytest.mark.asyncio
    async def test_model_override_sent_in_payload(self):
        client = _mock_client([[0.0] * 1536])
        backend = OpenAIGatewayBackend(http_client=client)
        await backend.embed(["text"], model="text-embedding-3-small")
        _, kwargs = client.post.call_args
        payload = kwargs.get("json") or client.post.call_args[0][1]
        assert payload["model"] == "text-embedding-3-small"

    @pytest.mark.asyncio
    async def test_batch_texts_sent_to_gateway(self):
        texts = ["a", "b", "c"]
        client = _mock_client([[0.0] * 1536] * 3)
        backend = OpenAIGatewayBackend(http_client=client)
        await backend.embed(texts)
        _, kwargs = client.post.call_args
        sent_texts = (kwargs.get("json") or client.post.call_args[0][1])["texts"]
        assert sent_texts == texts

    def test_default_model(self):
        backend = OpenAIGatewayBackend()
        assert "embedding" in backend.default_model()

    def test_dimensions_for_ada(self):
        backend = OpenAIGatewayBackend()
        assert backend.dimensions_for("text-embedding-ada-002") == 1536

    def test_dimensions_for_large(self):
        backend = OpenAIGatewayBackend()
        assert backend.dimensions_for("text-embedding-3-large") == 3072

    def test_dimensions_default_1536_for_unknown(self):
        backend = OpenAIGatewayBackend()
        assert backend.dimensions_for("unknown-model") == 1536

    @pytest.mark.asyncio
    async def test_http_error_propagates(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post = AsyncMock(side_effect=httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        ))
        client.aclose = AsyncMock()
        backend = OpenAIGatewayBackend(http_client=client)
        with pytest.raises(httpx.HTTPStatusError):
            await backend.embed(["text"])
