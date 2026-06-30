"""Unit tests for request/response schema validation."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas.request import CompletionRequest, Message, MessageRole, ModelTier
from src.schemas.response import CompletionChoice, CompletionResponse, StreamChunk, UsageStats


class TestCompletionRequestValidation:
    def test_valid_request(self):
        req = CompletionRequest(
            model_tier=ModelTier.STANDARD,
            messages=[Message(role=MessageRole.USER, content="Hi")],
        )
        assert req.model_tier == ModelTier.STANDARD
        assert req.temperature == 0.7
        assert req.max_tokens == 1024

    def test_empty_messages_rejected(self):
        with pytest.raises(ValidationError):
            CompletionRequest(model_tier=ModelTier.STANDARD, messages=[])

    def test_temperature_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            CompletionRequest(
                model_tier=ModelTier.STANDARD,
                messages=[Message(role=MessageRole.USER, content="Hi")],
                temperature=3.0,
            )

    def test_negative_temperature_rejected(self):
        with pytest.raises(ValidationError):
            CompletionRequest(
                model_tier=ModelTier.STANDARD,
                messages=[Message(role=MessageRole.USER, content="Hi")],
                temperature=-0.1,
            )

    def test_max_tokens_minimum(self):
        with pytest.raises(ValidationError):
            CompletionRequest(
                model_tier=ModelTier.STANDARD,
                messages=[Message(role=MessageRole.USER, content="Hi")],
                max_tokens=0,
            )

    def test_max_tokens_maximum(self):
        with pytest.raises(ValidationError):
            CompletionRequest(
                model_tier=ModelTier.STANDARD,
                messages=[Message(role=MessageRole.USER, content="Hi")],
                max_tokens=99999,
            )

    def test_all_model_tiers_valid(self):
        for tier in ModelTier:
            req = CompletionRequest(
                model_tier=tier,
                messages=[Message(role=MessageRole.USER, content="Hi")],
            )
            assert req.model_tier == tier

    def test_provider_override_valid_values(self):
        for provider in ["openai", "azure", "ollama"]:
            req = CompletionRequest(
                model_tier=ModelTier.STANDARD,
                messages=[Message(role=MessageRole.USER, content="Hi")],
                provider_override=provider,
            )
            assert req.provider_override == provider

    def test_invalid_provider_override_rejected(self):
        with pytest.raises(ValidationError):
            CompletionRequest(
                model_tier=ModelTier.STANDARD,
                messages=[Message(role=MessageRole.USER, content="Hi")],
                provider_override="gemini",
            )

    def test_request_id_optional(self):
        req = CompletionRequest(
            model_tier=ModelTier.STANDARD,
            messages=[Message(role=MessageRole.USER, content="Hi")],
        )
        assert req.request_id is None

    def test_system_and_user_messages(self):
        req = CompletionRequest(
            model_tier=ModelTier.STANDARD,
            messages=[
                Message(role=MessageRole.SYSTEM, content="You are a tutor."),
                Message(role=MessageRole.USER, content="Teach me Python."),
            ],
        )
        assert len(req.messages) == 2


class TestCompletionResponseValidation:
    def test_valid_response(self):
        resp = CompletionResponse(
            request_id="req-1",
            provider="openai",
            model_used="gpt-4o",
            choices=[
                CompletionChoice(
                    index=0,
                    message_role="assistant",
                    message_content="Hello!",
                    finish_reason="stop",
                )
            ],
            usage=UsageStats(token_count_input=10, token_count_output=5, total_tokens=15),
            estimated_cost_usd=0.000125,
        )
        assert resp.provider == "openai"
        assert resp.usage.total_tokens == 15

    def test_default_usage_zeros(self):
        resp = CompletionResponse(
            request_id="req-2",
            provider="ollama",
            model_used="llama3.2",
            choices=[
                CompletionChoice(index=0, message_role="assistant", message_content="Hi")
            ],
        )
        assert resp.usage.token_count_input == 0
        assert resp.estimated_cost_usd == 0.0


class TestStreamChunkValidation:
    def test_valid_intermediate_chunk(self):
        chunk = StreamChunk(
            request_id="req-3",
            provider="openai",
            model_used="gpt-4o",
            delta="Hello",
        )
        assert chunk.finish_reason is None
        assert chunk.usage is None

    def test_valid_final_chunk(self):
        chunk = StreamChunk(
            request_id="req-3",
            provider="openai",
            model_used="gpt-4o",
            delta="!",
            finish_reason="stop",
            usage=UsageStats(token_count_input=5, token_count_output=3, total_tokens=8),
            estimated_cost_usd=0.0001,
        )
        assert chunk.finish_reason == "stop"
        assert chunk.usage.total_tokens == 8
