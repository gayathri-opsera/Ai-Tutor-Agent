"""Embedding backend using a locally-loaded sentence-transformers model.

Intended for GPU nodes (g5.xlarge) and offline environments. The model is
loaded once at startup and reused for all requests.

sentence-transformers is an optional dependency — it is NOT listed in
requirements.txt because it pulls in PyTorch (~2 GB). Install separately:

    pip install sentence-transformers==3.3.1

When the package is not installed this backend raises ImportError on
construction, allowing the factory to fall back gracefully.
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from src.config import settings
from src.backends.base import EmbeddingBackend

logger = logging.getLogger(__name__)

_DIMENSIONS: dict[str, int] = {
    "all-MiniLM-L6-v2": 384,
    "all-mpnet-base-v2": 768,
    "paraphrase-multilingual-MiniLM-L12-v2": 384,
}

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="st-embed")


class SentenceTransformersBackend(EmbeddingBackend):
    """Wraps a sentence-transformers model for local/offline embedding.

    encode() is CPU/GPU-bound and blocking, so it runs in a thread pool
    to avoid blocking the asyncio event loop.
    """

    name = "sentence_transformers"

    def __init__(self, model_name: str | None = None) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is not installed. "
                "Run: pip install sentence-transformers==3.3.1"
            ) from exc

        self._model_name = model_name or settings.st_model_name
        logger.info("Loading sentence-transformers model: %s", self._model_name)
        self._model = SentenceTransformer(self._model_name)

    def default_model(self) -> str:
        return self._model_name

    def dimensions_for(self, model: str) -> int:
        return _DIMENSIONS.get(model, 384)

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        loop = asyncio.get_event_loop()
        encode = partial(self._model.encode, texts, convert_to_numpy=True)
        vectors = await loop.run_in_executor(_executor, encode)
        return [v.tolist() for v in vectors]
