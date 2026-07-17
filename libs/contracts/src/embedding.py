"""Shared Pydantic contract models for the Embedding Service.

Migrated from services/embedding-service/src/schemas.py (WO-014).
Import as:
    from libs.contracts.src.embedding import EmbedRequest, EmbedResponse
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class EmbedRequest(BaseModel):
    """Request body for POST /api/internal/embeddings/generate."""

    texts: list[str] = Field(..., min_length=1, description="Text chunks to embed.")
    model: str | None = Field(
        default=None,
        description="Optional model override. Uses the configured default when omitted.",
    )


class EmbedResponse(BaseModel):
    """Response envelope for POST /api/internal/embeddings/generate."""

    embeddings: list[list[float]]
    model: str
    dimensions: int
    backend: str


__all__ = ["EmbedRequest", "EmbedResponse"]
