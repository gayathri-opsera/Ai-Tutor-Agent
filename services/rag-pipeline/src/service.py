"""Core RAG retrieval service."""
from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

from embedding import EmbedRequest  # shared contract from libs/contracts (WO-014)
from src.hybrid_search import hybrid_search
from src.reranker import reciprocal_rank_fusion
from provider import ModelProvider  # libs/model/src/ in PYTHONPATH via Dockerfile
from gateway_provider import GatewayModelProvider  # libs/model/src/ in PYTHONPATH via Dockerfile

logger = logging.getLogger(__name__)


class VectorDBClientProtocol(Protocol):
    async def query_vectors(
        self, query_vector: list[float], top_k: int, filters: dict | None, namespace: str
    ) -> list[Any]: ...


class RAGPipelineService:
    """Orchestrates embedding, vector search, filtering, and re-ranking.

    Parameters
    ----------
    vector_client:
        Any object satisfying ``VectorDBClientProtocol``.
    embedding_url:
        Fallback URL for the embedding service when no ``model_provider`` is
        supplied.  Ignored when ``model_provider`` is set.
    model_provider:
        Optional :class:`~libs.model.src.provider.ModelProvider` implementation.
        When provided, embeddings are generated via
        ``model_provider.embed()`` rather than a raw httpx call — removing
        the hardcoded embedding-service URL dependency (Strike #3).
    http_client:
        Optional injectable ``httpx.AsyncClient`` used for the legacy
        embedding endpoint fallback path.
    """

    def __init__(
        self,
        vector_client: VectorDBClientProtocol,
        embedding_url: str = "http://localhost:8002",
        model_provider: Any | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.vector_client = vector_client
        self.embedding_url = embedding_url.rstrip("/")
        # Prefer the injected provider; fall back to GatewayModelProvider (routes via llm-gateway).
        self._model_provider: ModelProvider = model_provider if model_provider is not None else GatewayModelProvider()
        self._http = http_client

    async def retrieve(
        self,
        query: str,
        knowledge_base_id: str,
        top_k: int = 5,
        filters: dict | None = None,
        use_hybrid: bool = True,
    ) -> dict[str, Any]:
        embedding = await self._embed(query)
        merged_filters = {"knowledge_base_id": knowledge_base_id, **(filters or {})}
        raw_results = await self.vector_client.query_vectors(
            embedding, top_k=top_k * 2, filters=merged_filters, namespace="default"
        )
        chunks = [
            {
                "chunk_id": r.id,
                "text": r.metadata.get("text", ""),
                "document_id": r.metadata.get("document_id", ""),
                "document_title": r.metadata.get("document_title", ""),
                "score": r.score,
                "metadata": r.metadata,
            }
            for r in raw_results
        ]
        if use_hybrid and chunks:
            ranked = hybrid_search(query, chunks, top_k=top_k)
        elif len(chunks) > 1:
            ranked = reciprocal_rank_fusion([chunks])[:top_k]
        else:
            ranked = chunks[:top_k]
        return {"chunks": ranked, "query_embedding": embedding}

    async def _embed(self, text: str) -> list[float]:
        # Route through GatewayModelProvider (via llm-gateway) — removes the
        # hardcoded embedding-service URL dependency (Strike #3).
        try:
            vectors = await self._model_provider.embed([text])
            return vectors[0]
        except Exception as exc:
            logger.warning("ModelProvider.embed failed (%s) — falling back to direct embedding-service call", exc)

        # Fallback: call the embedding-service directly via httpx.
        client = self._http or httpx.AsyncClient()
        close_client = self._http is None
        try:
            resp = await client.post(
                f"{self.embedding_url}/api/internal/embeddings/generate",
                json=EmbedRequest(texts=[text]).model_dump(exclude_none=True),
            )
            resp.raise_for_status()
            data = resp.json()
            return data["embeddings"][0]
        finally:
            if close_client:
                await client.aclose()

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in one call (batch of up to 100)."""
        client = self._http or httpx.AsyncClient(timeout=60.0)
        close_client = self._http is None
        results: list[list[float]] = []
        try:
            for start in range(0, len(texts), 100):
                batch = texts[start:start + 100]
                resp = await client.post(
                    f"{self.embedding_url}/api/internal/embeddings/generate",
                    json=EmbedRequest(texts=batch).model_dump(exclude_none=True),
                )
                resp.raise_for_status()
                data = resp.json()
                results.extend(data["embeddings"])
        except Exception as exc:
            logger.warning("Embedding batch failed, using zero vectors: %s", exc)
            dim = len(results[0]) if results else 1536
            results.extend([[0.0] * dim for _ in range(len(texts) - len(results))])
        finally:
            if close_client:
                await client.aclose()
        return results
