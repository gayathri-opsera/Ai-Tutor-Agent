"""Corrective RAG confidence grader."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Reliability(str, Enum):
    RELIABLE = "reliable"
    AMBIGUOUS = "ambiguous"
    UNRELIABLE = "unreliable"


@dataclass
class ChunkGrade:
    chunk_id: str
    reliability: Reliability
    score: float


@dataclass
class GraderResult:
    confidence: float
    chunk_grades: list[ChunkGrade]
    answer: str
    verified: bool


def classify_chunk(score: float) -> Reliability:
    if score >= 0.7:
        return Reliability.RELIABLE
    if score >= 0.4:
        return Reliability.AMBIGUOUS
    return Reliability.UNRELIABLE


def verify_answer(answer: str, chunks: list[dict[str, Any]]) -> float:
    """Check answer overlap with source chunks."""
    if not chunks:
        return 0.0
    answer_tokens = set(re.findall(r"\w+", answer.lower()))
    if not answer_tokens:
        return 0.0
    overlaps = []
    for chunk in chunks:
        chunk_tokens = set(re.findall(r"\w+", chunk.get("text", "").lower()))
        if not chunk_tokens:
            overlaps.append(0.0)
            continue
        overlap = len(answer_tokens & chunk_tokens) / max(len(answer_tokens), 1)
        overlaps.append(overlap)
    return max(overlaps) if overlaps else 0.0


def evaluate(
    answer: str,
    chunks: list[dict[str, Any]],
) -> GraderResult:
    grades: list[ChunkGrade] = []
    for chunk in chunks:
        score = float(chunk.get("score", 0.5))
        grades.append(ChunkGrade(
            chunk_id=str(chunk.get("chunk_id", "")),
            reliability=classify_chunk(score),
            score=score,
        ))
    all_unreliable = all(g.reliability == Reliability.UNRELIABLE for g in grades) if grades else True
    verification_score = verify_answer(answer, chunks)
    confidence = verification_score if not all_unreliable else 0.0

    if all_unreliable:
        final_answer = "I don't have enough information to answer this question confidently."
        verified = False
    else:
        final_answer = answer
        verified = confidence >= 0.4

    return GraderResult(
        confidence=round(confidence, 3),
        chunk_grades=grades,
        answer=final_answer,
        verified=verified,
    )
