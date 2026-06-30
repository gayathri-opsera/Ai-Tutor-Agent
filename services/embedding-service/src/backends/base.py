"""Abstract base class for embedding backends."""
from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingBackend(ABC):
    """Common interface all embedding backends must implement."""

    name: str = "base"

    @abstractmethod
    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """Return one embedding vector per input text."""

    @abstractmethod
    def default_model(self) -> str:
        """Return the default model identifier for this backend."""

    @abstractmethod
    def dimensions_for(self, model: str) -> int:
        """Return the embedding dimensionality for the given model."""
