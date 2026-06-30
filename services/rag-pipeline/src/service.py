"""Core RAG retrieval service."""
from __future__ import annotations

from typing import Any, Protocol

import httpx

from src.hybrid_search import hybrid_search
from src.reranker import reciprocal_rank_fusion


class VectorDBClientProtocol(Protocol):
    async def query_vectors(
        self, query_vector: list[float], top_k: int, filters: dict | None, namespace: str
    ) -> list[Any]: ...


class RAGPipelineService:
    """Orchestrates embedding, vector search, filtering, and re-ranking."""

    def __init__(
        self,
        vector_client: VectorDBClientProtocol,
        embedding_url: str = "http://localhost:8002",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.vector_client = vector_client
        self.embedding_url = embedding_url.rstrip("/")
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
        client = self._http or httpx.AsyncClient()
        close_client = self._http is None
        try:
            resp = await client.post(
                f"{self.embedding_url}/api/v1/embeddings",
                json={"texts": [text]},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["embeddings"][0]
        finally:
            if close_client:
                await client.aclose()
