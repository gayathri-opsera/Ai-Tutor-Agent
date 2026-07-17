"""Shared Pydantic contract models for RAG pipeline inter-service communication.

Migrated from services/rag-pipeline/src/api/rag.py (WO-013).
Import as:
    from libs.contracts.src.rag import RetrieveRequest, RetrieveResponse, ChunkResult
    from libs.contracts.src.rag import IngestRequest, IngestChunk
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RetrieveRequest(BaseModel):
    """Request body for POST /api/internal/rag/retrieve."""

    query: str
    knowledge_base_id: str
    top_k: int = Field(default=5, ge=1, le=50)
    filters: dict[str, Any] | None = None
    use_hybrid: bool = True


class ChunkResult(BaseModel):
    """A single document chunk returned by the RAG retrieval endpoint."""

    chunk_id: str
    text: str
    document_id: str
    document_title: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrieveResponse(BaseModel):
    """Response envelope for POST /api/internal/rag/retrieve."""

    chunks: list[ChunkResult]
    query_embedding: list[float]


class IngestChunk(BaseModel):
    """A single text chunk submitted for embedding and vector-store upsert."""

    text: str
    chunk_index: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestRequest(BaseModel):
    """Request body for POST /api/internal/rag/ingest."""

    document_id: str
    knowledge_base_id: str
    document_title: str
    chunks: list[IngestChunk]


__all__ = [
    "RetrieveRequest",
    "ChunkResult",
    "RetrieveResponse",
    "IngestChunk",
    "IngestRequest",
]
