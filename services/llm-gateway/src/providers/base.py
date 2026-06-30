"""Abstract provider interface — all concrete adapters implement this contract."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from src.schemas.request import CompletionRequest
from src.schemas.response import CompletionResponse, StreamChunk

# Cost per 1 000 tokens in USD — updated periodically; override via env.
COST_TABLE: dict[str, dict[str, float]] = {
    # model_name: {input: $/1k, output: $/1k}
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    "text-embedding-ada-002": {"input": 0.0001, "output": 0.0},
    # Azure deployments re-use the same cost table
    "gpt-4o-azure": {"input": 0.005, "output": 0.015},
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return estimated USD cost; falls back to 0 for unknown models."""
    rates = COST_TABLE.get(model, COST_TABLE.get(model.split("/")[-1], {}))
    if not rates:
        return 0.0
    return (input_tokens / 1000 * rates.get("input", 0.0)) + (
        output_tokens / 1000 * rates.get("output", 0.0)
    )


class LLMProvider(ABC):
    """Strategy interface for LLM provider adapters."""

    name: str = "base"

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Synchronous (non-streaming) completion."""

    @abstractmethod
    async def stream(
        self, request: CompletionRequest
    ) -> AsyncIterator[StreamChunk]:
        """Streaming completion — yields one StreamChunk per token batch."""

    @abstractmethod
    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """Embedding generation."""

    def resolve_model(self, tier: str) -> str:  # noqa: ARG002
        """Map abstract ModelTier to a concrete model string for this provider."""
        raise NotImplementedError
