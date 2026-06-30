"""Tests for semantic cache."""
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api import create_cache_router
from src.semantic_cache import InMemorySemanticCache, cosine_similarity


def test_cosine_similarity_identical():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_cache_hit():
    cache = InMemorySemanticCache(similarity_threshold=0.9)
    emb = [1.0, 0.0, 0.0]
    await cache.store("hello", emb, {"answer": "world"}, ttl_seconds=3600)
    hit, response, score = await cache.check([0.99, 0.01, 0.0])
    assert hit is True
    assert response == {"answer": "world"}
    assert score >= 0.9


@pytest.mark.asyncio
async def test_cache_miss():
    cache = InMemorySemanticCache(similarity_threshold=0.99)
    await cache.store("hello", [1.0, 0.0], {"answer": "world"}, ttl_seconds=3600)
    hit, response, _ = await cache.check([0.0, 1.0])
    assert hit is False
    assert response is None


@pytest.mark.asyncio
async def test_cache_api():
    cache = InMemorySemanticCache()
    app = FastAPI()
    app.include_router(create_cache_router(cache))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/internal/cache/store", json={
            "query": "q", "embedding": [1, 0], "response": {"a": 1}, "ttl_seconds": 60
        })
        resp = await client.post("/api/internal/cache/check", json={"embedding": [1, 0]})
    assert resp.status_code == 200
    assert resp.json()["hit"] is True
