"""Request/response schemas for the Embedding Service."""
from __future__ import annotations

from pydantic import BaseModel, Field


class EmbedRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, description="Text chunks to embed.")
    model: str | None = Field(
        default=None,
        description="Optional model override. Uses the configured default when omitted.",
    )


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    model: str
    dimensions: int
    backend: str
