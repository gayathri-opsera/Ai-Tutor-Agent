"""Shared Pydantic contract models for the LLM Gateway.

Migrated from services/llm-gateway/src/schemas/request.py and response.py (WO-014).
Import as:
    from libs.contracts.src.llm import CompletionRequest, CompletionResponse
    from libs.contracts.src.llm import Message, MessageRole, ModelTier
    from libs.contracts.src.llm import StreamChunk, UsageStats, CompletionChoice
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ModelTier(str, Enum):
    """Abstract model capability tiers — decoupled from vendor model names."""

    SMALL = "small"          # e.g. gpt-4o-mini, claude-haiku
    STANDARD = "standard"    # e.g. gpt-4o, claude-sonnet
    LARGE = "large"          # e.g. o1, claude-opus
    EMBEDDING = "embedding"  # text-embedding-ada-002, etc.


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    role: MessageRole
    content: str


class CompletionRequest(BaseModel):
    """Unified, provider-agnostic completion request (ADR-001)."""

    model_tier: ModelTier = Field(
        default=ModelTier.STANDARD,
        description="Abstract capability tier; gateway maps to concrete model.",
    )
    messages: list[Message] = Field(..., min_length=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=32768)
    request_id: str | None = Field(
        default=None,
        description="Caller-supplied idempotency / trace ID.",
    )
    provider_override: Literal["openai", "azure", "ollama"] | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class UsageStats(BaseModel):
    token_count_input: int = 0
    token_count_output: int = 0
    total_tokens: int = 0


class CompletionChoice(BaseModel):
    index: int = 0
    message_role: str = "assistant"
    message_content: str
    finish_reason: str | None = None


class CompletionResponse(BaseModel):
    """Unified response returned to all callers regardless of upstream provider."""

    request_id: str
    provider: str
    model_used: str
    choices: list[CompletionChoice]
    usage: UsageStats = Field(default_factory=UsageStats)
    estimated_cost_usd: float = 0.0


class StreamChunk(BaseModel):
    """Individual SSE token chunk delivered during streaming."""

    request_id: str
    provider: str
    model_used: str
    delta: str
    finish_reason: str | None = None
    usage: UsageStats | None = None
    estimated_cost_usd: float | None = None


__all__ = [
    "ModelTier",
    "MessageRole",
    "Message",
    "CompletionRequest",
    "UsageStats",
    "CompletionChoice",
    "CompletionResponse",
    "StreamChunk",
]
