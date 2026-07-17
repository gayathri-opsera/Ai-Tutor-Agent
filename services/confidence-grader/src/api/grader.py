"""Confidence grader API."""
from __future__ import annotations

from fastapi import APIRouter

from grader import EvaluateRequest  # noqa: F401 — re-export from libs/contracts (WO-015)
from src.grader import evaluate

router = APIRouter(prefix="/api/internal/grader", tags=["grader"])


@router.post("/evaluate")
async def grader_evaluate(body: EvaluateRequest):
    result = evaluate(body.answer, body.chunks)
    return {
        "confidence": result.confidence,
        "answer": result.answer,
        "verified": result.verified,
        "source_type": result.source_type.value,
        "chunk_grades": [
            {"chunk_id": g.chunk_id, "reliability": g.reliability.value, "score": g.score}
            for g in result.chunk_grades
        ],
    }
