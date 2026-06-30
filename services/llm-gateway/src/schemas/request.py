"""Provider-agnostic LLM request schema (ADR-001)."""
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
    """Unified, provider-agnostic completion request."""
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
    # Optional provider override — useful for canary testing
    provider_override: Literal["openai", "azure", "ollama"] | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
