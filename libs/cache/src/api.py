"""Cache API routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from src.semantic_cache import InMemorySemanticCache


class CacheCheckRequest(BaseModel):
    embedding: list[float]


class CacheCheckResponse(BaseModel):
    hit: bool
    response: Any | None = None
    similarity: float = 0.0


class CacheStoreRequest(BaseModel):
    query: str
    embedding: list[float]
    response: Any
    ttl_seconds: int = Field(default=3600, ge=1)


def create_cache_router(cache: InMemorySemanticCache | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/internal/cache", tags=["cache"])
    _cache = cache or InMemorySemanticCache()

    @router.post("/check", response_model=CacheCheckResponse)
    async def check_cache(body: CacheCheckRequest, request: Request):
        request.app.state.semantic_cache = _cache
        hit, response, similarity = await _cache.check(body.embedding)
        return CacheCheckResponse(hit=hit, response=response, similarity=similarity)

    @router.post("/store")
    async def store_cache(body: CacheStoreRequest):
        await _cache.store(body.query, body.embedding, body.response, body.ttl_seconds)
        return {"stored": True}

    return router
