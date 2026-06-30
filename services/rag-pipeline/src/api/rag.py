"""RAG Pipeline API routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field


class RetrieveRequest(BaseModel):
    query: str
    knowledge_base_id: str
    top_k: int = Field(default=5, ge=1, le=50)
    filters: dict[str, Any] | None = None
    use_hybrid: bool = True


class ChunkResult(BaseModel):
    chunk_id: str
    text: str
    document_id: str
    document_title: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrieveResponse(BaseModel):
    chunks: list[ChunkResult]
    query_embedding: list[float]


router = APIRouter(prefix="/api/internal/rag", tags=["rag"])


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(body: RetrieveRequest, request: Request):
    service = request.app.state.rag_service
    result = await service.retrieve(
        body.query,
        body.knowledge_base_id,
        top_k=body.top_k,
        filters=body.filters,
        use_hybrid=body.use_hybrid,
    )
    return RetrieveResponse(**result)
