"""Shared AI Model Provider abstraction layer.

Exposes the ``ModelProvider`` interface (strategy pattern) so any service
that needs to call an LLM can program to the abstraction rather than a
specific provider SDK.  Concrete implementations live in
``services/llm-gateway/src/providers/`` and are injected at runtime via the
``LLM_GATEWAY_URL`` environment variable — services never import a concrete
provider directly.

Switching from one LLM provider to another (or adding multi-model routing)
requires a single configuration change rather than edits across multiple
service files.

Usage (inside a service)::

    from libs.model.src.provider import ModelProvider, ProviderConfig

    # In production: delegate to LLM Gateway via HTTP
    # In tests: inject a mock that implements ModelProvider
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Any


class ModelProvider(ABC):
    """Strategy interface for AI model provider adapters.

    All concrete provider implementations must implement this interface.
    Services depend on ``ModelProvider`` — never on a concrete class.

    Methods
    -------
    complete(prompt, **kwargs)
        Single-shot completion; returns the full response text.
    stream(prompt, **kwargs)
        Streaming completion; yields text chunks as they arrive.
    embed(texts, model)
        Batch embedding generation; returns a list of float vectors.
    """

    name: str = "base"

    @abstractmethod
    async def complete(self, prompt: str, **kwargs: Any) -> str:
        """Return a complete response for *prompt*."""

    @abstractmethod
    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        """Yield streaming response chunks for *prompt*."""

    @abstractmethod
    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """Return embeddings for *texts*."""


class ProviderConfig:
    """Immutable provider configuration resolved from environment variables.

    Read at startup so missing config fails fast rather than at request time.

    Attributes
    ----------
    name : str
        Provider identifier, e.g. ``"anthropic"``, ``"openai"``, ``"groq"``.
    model : str
        Default model name for completions.
    embedding_model : str
        Default model name for embeddings.
    base_url : str | None
        Optional override for the provider base URL (e.g. Azure endpoint).
    """

    __slots__ = ("name", "model", "embedding_model", "base_url")

    def __init__(
        self,
        name: str,
        model: str,
        embedding_model: str = "text-embedding-ada-002",
        base_url: str | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.embedding_model = embedding_model
        self.base_url = base_url

    def __repr__(self) -> str:
        return (
            f"ProviderConfig(name={self.name!r}, model={self.model!r}, "
            f"base_url={self.base_url!r})"
        )
