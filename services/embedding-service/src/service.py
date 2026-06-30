"""EmbeddingService — validates inputs, selects backend, returns vectors."""
from __future__ import annotations

import logging

from src.backends.base import EmbeddingBackend
from src.config import settings
from src.schemas import EmbedRequest, EmbedResponse

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Coordinates input validation, backend selection, and response assembly."""

    def __init__(self, backend: EmbeddingBackend) -> None:
        self._backend = backend

    @property
    def backend(self) -> EmbeddingBackend:
        return self._backend

    async def generate(self, request: EmbedRequest) -> EmbedResponse:
        self._validate(request)

        model = request.model or self._backend.default_model()
        embeddings = await self._backend.embed(request.texts, model=model)

        dims = len(embeddings[0]) if embeddings else self._backend.dimensions_for(model)
        return EmbedResponse(
            embeddings=embeddings,
            model=model,
            dimensions=dims,
            backend=self._backend.name,
        )

    def _validate(self, request: EmbedRequest) -> None:
        if not request.texts:
            raise ValueError("texts must not be empty")

        if len(request.texts) > settings.max_texts_per_batch:
            raise ValueError(
                f"Batch size {len(request.texts)} exceeds limit of "
                f"{settings.max_texts_per_batch} texts per request."
            )

        for i, text in enumerate(request.texts):
            if not text or not text.strip():
                raise ValueError(f"texts[{i}] is empty or whitespace-only.")
            if len(text) > settings.max_text_length_chars:
                raise ValueError(
                    f"texts[{i}] length {len(text)} exceeds limit of "
                    f"{settings.max_text_length_chars} characters."
                )


def make_backend(backend_name: str | None = None) -> EmbeddingBackend:
    """Factory: instantiate the configured or requested backend."""
    name = backend_name or settings.embedding_backend

    if name == "openai_gateway":
        from src.backends.openai_gateway import OpenAIGatewayBackend
        return OpenAIGatewayBackend()

    if name == "sentence_transformers":
        from src.backends.sentence_transformers import SentenceTransformersBackend
        return SentenceTransformersBackend()

    if name == "mock":
        from src.backends.mock import MockEmbeddingBackend
        return MockEmbeddingBackend()

    raise ValueError(
        f"Unknown embedding backend: '{name}'. "
        "Choose one of: openai_gateway, sentence_transformers, mock"
    )
