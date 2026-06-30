"""Deterministic mock backend for unit testing without a live model or gateway.

Returns pre-computed fixture vectors so tests are reproducible and fast.
Useful for local development, CI, and any context where no model is available.
"""
from __future__ import annotations

import hashlib

from src.backends.base import EmbeddingBackend

_DIM = 1536   # matches text-embedding-ada-002 for drop-in compatibility


def _deterministic_vector(text: str, dim: int) -> list[float]:
    """Produce a stable unit-ish vector from the text's hash."""
    seed = int(hashlib.md5(text.encode()).hexdigest(), 16)
    values = [(((seed >> i) & 0xFF) / 255.0) - 0.5 for i in range(dim)]
    return values


class MockEmbeddingBackend(EmbeddingBackend):
    """Returns deterministic vectors — same text always yields the same vector."""

    name = "mock"

    def __init__(self, dimensions: int = _DIM) -> None:
        self._dim = dimensions

    def default_model(self) -> str:
        return "mock-embedding-v1"

    def dimensions_for(self, model: str) -> int:
        return self._dim

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        return [_deterministic_vector(t, self._dim) for t in texts]
