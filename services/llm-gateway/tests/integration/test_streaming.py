"""Integration tests for the SSE streaming endpoint.

Validates gateway SSE formatting, PII scrubbing delegation, and error handling
by mocking LLMRouter.stream at the router level.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.kafka.usage_logger import KafkaUsageLogger
from src.router import LLMRouter
from src.schemas.response import StreamChunk, UsageStats

FIXTURES = Path(__file__).parent.parent / "fixtures"


def make_mock_router(chunks=None, raises=None):
    router = MagicMock(spec=LLMRouter)
    router.circuit_stats = MagicMock(return_value={"state": "closed", "window_total": 0, "window_failures": 0, "error_rate": 0.0})

    default_chunks = [
        StreamChunk(request_id="s1", provider="openai", model_used="gpt-4o", delta="Light"),
        StreamChunk(request_id="s1", provider="openai", model_used="gpt-4o", delta=" energy"),
        StreamChunk(
            request_id="s1",
            provider="openai",
            model_used="gpt-4o",
            delta=".",
            finish_reason="stop",
            usage=UsageStats(token_count_input=5, token_count_output=3, total_tokens=8),
            estimated_cost_usd=0.00005,
        ),
    ]

    async def mock_stream(request):
        if raises:
            raise raises
        for c in (chunks or default_chunks):
            yield c

    router.stream = mock_stream
    return router


@pytest.fixture
def stream_app():
    from src.main import create_app

    application = create_app()
    application.state.llm_router = make_mock_router()
    application.state.usage_logger = AsyncMock(spec=KafkaUsageLogger)
    return application


@pytest.fixture
def stream_client(stream_app):
    return TestClient(stream_app, raise_server_exceptions=False)


STREAM_PAYLOAD = {
    "model_tier": "standard",
    "messages": [{"role": "user", "content": "Explain photosynthesis briefly."}],
    "temperature": 0.7,
    "max_tokens": 50,
    "request_id": "stream-integ-001",
}


class TestStreamingEndpoint:
    def test_sse_content_type_header(self, stream_client):
        with stream_client.stream("POST", "/api/internal/llm/completions/stream", json=STREAM_PAYLOAD) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_sse_chunks_delivered(self, stream_client):
        with stream_client.stream("POST", "/api/internal/llm/completions/stream", json=STREAM_PAYLOAD) as resp:
            raw = resp.read().decode()
        assert "data:" in raw

    def test_stream_includes_done_sentinel(self, stream_client):
        with stream_client.stream("POST", "/api/internal/llm/completions/stream", json=STREAM_PAYLOAD) as resp:
            raw = resp.read().decode()
        assert "[DONE]" in raw

    def test_stream_chunks_are_valid_json(self, stream_client):
        with stream_client.stream("POST", "/api/internal/llm/completions/stream", json=STREAM_PAYLOAD) as resp:
            raw = resp.read().decode()

        lines = [l.strip() for l in raw.splitlines() if l.startswith("data:")]
        for line in lines:
            payload = line[len("data:"):].strip()
            if payload != "[DONE]":
                parsed = json.loads(payload)
                assert "request_id" in parsed
                assert "provider" in parsed
                assert "delta" in parsed

    def test_stream_validation_error_on_empty_messages(self, stream_client):
        bad_payload = {
            "model_tier": "standard",
            "messages": [],
            "temperature": 0.5,
            "max_tokens": 50,
        }
        resp = stream_client.post("/api/internal/llm/completions/stream", json=bad_payload)
        assert resp.status_code == 422

    def test_stream_error_surfaced_as_sse_event(self):
        from src.main import create_app
        app = create_app()
        app.state.llm_router = make_mock_router(raises=RuntimeError("provider failure"))
        app.state.usage_logger = AsyncMock(spec=KafkaUsageLogger)
        client = TestClient(app, raise_server_exceptions=False)

        with client.stream("POST", "/api/internal/llm/completions/stream", json=STREAM_PAYLOAD) as resp:
            raw = resp.read().decode()

        assert "error" in raw.lower()

    def test_stream_request_id_auto_generated(self):
        from src.main import create_app
        app = create_app()
        received = []

        async def capture_stream(request):
            received.append(request.request_id)
            yield StreamChunk(request_id=request.request_id or "auto", provider="openai", model_used="gpt-4o", delta="Hi",
                              finish_reason="stop",
                              usage=UsageStats(token_count_input=1, token_count_output=1, total_tokens=2))

        mock_router = MagicMock(spec=LLMRouter)
        mock_router.stream = capture_stream
        mock_router.circuit_stats = MagicMock(return_value={})

        app.state.llm_router = mock_router
        app.state.usage_logger = AsyncMock(spec=KafkaUsageLogger)
        client = TestClient(app, raise_server_exceptions=False)

        payload = dict(STREAM_PAYLOAD)
        del payload["request_id"]

        with client.stream("POST", "/api/internal/llm/completions/stream", json=payload) as resp:
            resp.read()

        assert len(received) == 1
        assert received[0] is not None

    def test_stream_pii_payload_accepted(self, stream_client):
        """PII in streaming requests passes through the API layer to the router (which scrubs)."""
        pii_payload = {
            "model_tier": "standard",
            "messages": [{"role": "user", "content": "My phone is 555-867-5309."}],
            "temperature": 0.5,
            "max_tokens": 50,
            "request_id": "stream-pii-001",
        }
        with stream_client.stream("POST", "/api/internal/llm/completions/stream", json=pii_payload) as resp:
            raw = resp.read().decode()

        assert "data:" in raw
        assert "[DONE]" in raw
