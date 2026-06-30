"""Unified provider-agnostic LLM response schema (ADR-001)."""
from __future__ import annotations

from pydantic import BaseModel, Field


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
    provider: str                 # "openai" | "azure" | "ollama"
    model_used: str               # Concrete model name resolved by the gateway
    choices: list[CompletionChoice]
    usage: UsageStats = Field(default_factory=UsageStats)
    estimated_cost_usd: float = 0.0


class StreamChunk(BaseModel):
    """Individual SSE token chunk delivered during streaming."""
    request_id: str
    provider: str
    model_used: str
    delta: str                    # Token or partial text
    finish_reason: str | None = None
    usage: UsageStats | None = None   # Populated only on the final chunk
    estimated_cost_usd: float | None = None
