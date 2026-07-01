"""Groq provider adapter.

Groq exposes an OpenAI-compatible chat-completions API so this is a thin
subclass of OpenAIProvider with a different base URL, key, and model map.
"""
from __future__ import annotations

from src.config import settings
from src.providers.openai_provider import OpenAIProvider
from src.schemas.request import ModelTier

_GROQ_API_BASE = "https://api.groq.com/openai/v1"

_TIER_TO_MODEL: dict[ModelTier, str] = {
    ModelTier.SMALL:     "llama-3.1-8b-instant",
    ModelTier.STANDARD:  "llama-3.3-70b-versatile",
    ModelTier.LARGE:     "llama-3.3-70b-versatile",
    ModelTier.EMBEDDING: "llama-3.1-8b-instant",
}


class GroqProvider(OpenAIProvider):
    """Adapter for the Groq inference API (OpenAI-compatible)."""

    name = "groq"

    def __init__(self, api_key: str | None = None, timeout: float | None = None) -> None:
        super().__init__(
            api_key=api_key or settings.groq_api_key,
            api_base=_GROQ_API_BASE,
            timeout=timeout,
        )

    def resolve_model(self, tier: str) -> str:
        return _TIER_TO_MODEL.get(ModelTier(tier), "llama-3.3-70b-versatile")

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        raise NotImplementedError(
            "Groq does not provide an embeddings endpoint. "
            "Set EMBEDDING_BACKEND=sentence_transformers in your .env."
        )
