"""Shared Pydantic contract models for the Confidence Grader service.

Migrated from services/confidence-grader/src/api/grader.py (WO-015).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EvaluateRequest(BaseModel):
    """Request body for POST /api/internal/grader/evaluate."""

    answer: str
    chunks: list[dict[str, Any]] = Field(default_factory=list)


class ChunkGrade(BaseModel):
    """Per-chunk grading result returned by the confidence grader."""

    chunk_id: str
    reliability: str
    score: float


class EvaluateResponse(BaseModel):
    """Response envelope for POST /api/internal/grader/evaluate."""

    confidence: float
    answer: str
    verified: bool
    source_type: str
    chunk_grades: list[ChunkGrade] = Field(default_factory=list)


__all__ = ["EvaluateRequest", "ChunkGrade", "EvaluateResponse"]
