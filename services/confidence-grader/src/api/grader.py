"""Confidence grader API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.grader import evaluate

router = APIRouter(prefix="/api/internal/grader", tags=["grader"])


class EvaluateRequest(BaseModel):
    answer: str
    chunks: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/evaluate")
async def grader_evaluate(body: EvaluateRequest):
    result = evaluate(body.answer, body.chunks)
    return {
        "confidence": result.confidence,
        "answer": result.answer,
        "verified": result.verified,
        "chunk_grades": [
            {"chunk_id": g.chunk_id, "reliability": g.reliability.value, "score": g.score}
            for g in result.chunk_grades
        ],
    }
