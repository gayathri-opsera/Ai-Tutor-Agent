"""Tests for RAG pipeline."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.hybrid_search import hybrid_search
from src.main import create_app
from src.reranker import reciprocal_rank_fusion
from src.service import RAGPipelineService
from src.vector_client import VectorDBClient, VectorRecord


def test_rrf():
    list_a = [{"chunk_id": "a", "score": 1.0}, {"chunk_id": "b", "score": 0.5}]
    list_b = [{"chunk_id": "b", "score": 0.9}, {"chunk_id": "a", "score": 0.4}]
    fused = reciprocal_rank_fusion([list_a, list_b])
    assert len(fused) == 2


def test_hybrid_search():
    results = [
        {"chunk_id": "1", "text": "machine learning tutorial", "score": 0.9},
        {"chunk_id": "2", "text": "cooking recipes pasta", "score": 0.3},
    ]
    ranked = hybrid_search("machine learning", results, top_k=2)
    assert ranked[0]["chunk_id"] == "1"


@pytest.mark.asyncio
async def test_retrieve_service():
    store = {
        "default": {
            "c1": VectorRecord(
                id="c1", vector=[1.0, 0.0],
                metadata={"text": "machine learning basics", "document_id": "d1",
                          "document_title": "ML Guide", "knowledge_base_id": "kb1"},
            ),
            "c2": VectorRecord(
                id="c2", vector=[0.9, 0.1],
                metadata={"text": "deep learning networks", "document_id": "d2",
                          "document_title": "DL Guide", "knowledge_base_id": "kb1"},
            ),
        }
    }
    client = VectorDBClient(_mock_store=store)
    mock_http = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"embeddings": [[1.0, 0.0]]}
    mock_http.post = AsyncMock(return_value=mock_resp)

    svc = RAGPipelineService(client, http_client=mock_http)
    result = await svc.retrieve("machine learning", "kb1", top_k=2)
    assert len(result["chunks"]) >= 1
    assert result["query_embedding"] == [1.0, 0.0]


@pytest.mark.asyncio
async def test_retrieve_api():
    store = {
        "default": {
            "c1": VectorRecord(
                id="c1", vector=[1.0, 0.0],
                metadata={"text": "test chunk", "document_id": "d1",
                          "document_title": "Doc", "knowledge_base_id": "kb1"},
            ),
        }
    }
    app = create_app(VectorDBClient(_mock_store=store))
    mock_http = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"embeddings": [[1.0, 0.0]]}
    mock_http.post = AsyncMock(return_value=mock_resp)
    app.state.rag_service = RAGPipelineService(VectorDBClient(_mock_store=store), http_client=mock_http)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/internal/rag/retrieve", json={
            "query": "test", "knowledge_base_id": "kb1", "top_k": 3
        })
    assert resp.status_code == 200
    assert "chunks" in resp.json()
