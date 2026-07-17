"""Unit tests for libs/contracts/src/embedding.py and src/llm.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.embedding import EmbedRequest, EmbedResponse
from src.llm import (
    CompletionChoice,
    CompletionRequest,
    CompletionResponse,
    Message,
    MessageRole,
    ModelTier,
    StreamChunk,
    UsageStats,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ── EmbedRequest ─────────────────────────────────────────────────────────────

class TestEmbedRequest:
    def test_instantiation(self):
        req = EmbedRequest(texts=["Hello world"])
        assert req.texts == ["Hello world"]
        assert req.model is None

    def test_with_model_override(self):
        req = EmbedRequest(texts=["t1", "t2"], model="text-embedding-3-small")
        assert req.model == "text-embedding-3-small"
        assert len(req.texts) == 2

    def test_empty_texts_rejected(self):
        with pytest.raises(ValidationError):
            EmbedRequest(texts=[])

    def test_serialization(self):
        req = EmbedRequest(texts=["a", "b"])
        d = req.model_dump(exclude_none=True)
        assert d["texts"] == ["a", "b"]
        assert "model" not in d

    def test_deserialization_from_fixture(self):
        fixture = json.loads((FIXTURES / "embed_request.json").read_text())
        req = EmbedRequest(**fixture)
        assert len(req.texts) > 0


# ── EmbedResponse ─────────────────────────────────────────────────────────────

class TestEmbedResponse:
    def test_instantiation(self):
        resp = EmbedResponse(
            embeddings=[[0.1, 0.2, 0.3]],
            model="text-embedding-ada-002",
            dimensions=3,
            backend="openai",
        )
        assert len(resp.embeddings) == 1
        assert resp.dimensions == 3

    def test_deserialization_from_fixture(self):
        fixture = json.loads((FIXTURES / "embed_response.json").read_text())
        resp = EmbedResponse(**fixture)
        assert len(resp.embeddings) > 0

    def test_serialization(self):
        resp = EmbedResponse(embeddings=[[0.1]], model="m", dimensions=1, backend="openai")
        d = resp.model_dump()
        assert "embeddings" in d
        assert d["backend"] == "openai"


# ── ModelTier ─────────────────────────────────────────────────────────────────

class TestModelTier:
    def test_values(self):
        assert ModelTier.SMALL == "small"
        assert ModelTier.STANDARD == "standard"
        assert ModelTier.LARGE == "large"
        assert ModelTier.EMBEDDING == "embedding"

    def test_from_string(self):
        assert ModelTier("standard") == ModelTier.STANDARD

    def test_invalid_tier(self):
        with pytest.raises(ValueError):
            ModelTier("ultra")


# ── MessageRole ───────────────────────────────────────────────────────────────

class TestMessageRole:
    def test_values(self):
        assert MessageRole.SYSTEM == "system"
        assert MessageRole.USER == "user"
        assert MessageRole.ASSISTANT == "assistant"


# ── Message ───────────────────────────────────────────────────────────────────

class TestMessage:
    def test_instantiation(self):
        msg = Message(role=MessageRole.USER, content="What is ML?")
        assert msg.role == MessageRole.USER

    def test_invalid_role(self):
        with pytest.raises(ValidationError):
            Message(role="god", content="hello")


# ── CompletionRequest ─────────────────────────────────────────────────────────

class TestCompletionRequest:
    def test_defaults(self):
        req = CompletionRequest(
            messages=[Message(role=MessageRole.USER, content="hi")]
        )
        assert req.model_tier == ModelTier.STANDARD
        assert req.temperature == 0.7
        assert req.max_tokens == 1024
        assert req.request_id is None

    def test_temperature_out_of_range(self):
        with pytest.raises(ValidationError):
            CompletionRequest(
                messages=[Message(role=MessageRole.USER, content="hi")],
                temperature=3.0,
            )

    def test_max_tokens_out_of_range(self):
        with pytest.raises(ValidationError):
            CompletionRequest(
                messages=[Message(role=MessageRole.USER, content="hi")],
                max_tokens=99999,
            )

    def test_empty_messages_rejected(self):
        with pytest.raises(ValidationError):
            CompletionRequest(messages=[])

    def test_serialization(self):
        req = CompletionRequest(
            messages=[Message(role=MessageRole.SYSTEM, content="You are a tutor.")],
            model_tier=ModelTier.LARGE,
            temperature=0.3,
            max_tokens=2048,
        )
        d = req.model_dump(mode="json")
        assert d["model_tier"] == "large"
        assert d["temperature"] == 0.3
        assert len(d["messages"]) == 1

    def test_deserialization_from_fixture(self):
        fixture = json.loads((FIXTURES / "completion_request.json").read_text())
        req = CompletionRequest(**fixture)
        assert len(req.messages) > 0

    def test_provider_override(self):
        req = CompletionRequest(
            messages=[Message(role=MessageRole.USER, content="hi")],
            provider_override="openai",
        )
        assert req.provider_override == "openai"

    def test_invalid_provider_override(self):
        with pytest.raises(ValidationError):
            CompletionRequest(
                messages=[Message(role=MessageRole.USER, content="hi")],
                provider_override="unknown-provider",
            )


# ── UsageStats ────────────────────────────────────────────────────────────────

class TestUsageStats:
    def test_defaults(self):
        u = UsageStats()
        assert u.token_count_input == 0
        assert u.total_tokens == 0

    def test_populated(self):
        u = UsageStats(token_count_input=10, token_count_output=20, total_tokens=30)
        assert u.total_tokens == 30


# ── CompletionChoice ──────────────────────────────────────────────────────────

class TestCompletionChoice:
    def test_instantiation(self):
        c = CompletionChoice(message_content="Hello!")
        assert c.index == 0
        assert c.message_role == "assistant"
        assert c.finish_reason is None


# ── CompletionResponse ────────────────────────────────────────────────────────

class TestCompletionResponse:
    def test_instantiation(self):
        resp = CompletionResponse(
            request_id="req-1",
            provider="openai",
            model_used="gpt-4o",
            choices=[CompletionChoice(message_content="Answer")],
        )
        assert resp.estimated_cost_usd == 0.0
        assert len(resp.choices) == 1

    def test_deserialization_from_fixture(self):
        fixture = json.loads((FIXTURES / "completion_response.json").read_text())
        resp = CompletionResponse(**fixture)
        assert resp.request_id is not None

    def test_serialization(self):
        resp = CompletionResponse(
            request_id="r", provider="azure", model_used="gpt-4",
            choices=[CompletionChoice(message_content="hi")]
        )
        d = resp.model_dump()
        assert d["provider"] == "azure"


# ── StreamChunk ───────────────────────────────────────────────────────────────

class TestStreamChunk:
    def test_instantiation(self):
        chunk = StreamChunk(
            request_id="r-1", provider="openai", model_used="gpt-4o", delta="Hello"
        )
        assert chunk.finish_reason is None
        assert chunk.usage is None

    def test_final_chunk_with_usage(self):
        chunk = StreamChunk(
            request_id="r-1",
            provider="openai",
            model_used="gpt-4o",
            delta="",
            finish_reason="stop",
            usage=UsageStats(token_count_input=5, token_count_output=10, total_tokens=15),
            estimated_cost_usd=0.002,
        )
        assert chunk.usage is not None
        assert chunk.usage.total_tokens == 15


# ── __init__ re-exports ───────────────────────────────────────────────────────

def test_init_reexports_all_embedding_llm_models():
    """Verify src/__init__.py re-exports all embedding and LLM models."""
    from src import (
        CompletionChoice,
        CompletionRequest,
        CompletionResponse,
        EmbedRequest,
        EmbedResponse,
        Message,
        MessageRole,
        ModelTier,
        StreamChunk,
        UsageStats,
    )
    assert EmbedRequest is not None
    assert CompletionRequest is not None
    assert StreamChunk is not None
