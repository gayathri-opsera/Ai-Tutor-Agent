"""Corrective RAG confidence grader.

Calibrated for sentence-transformers cosine similarity scores (all-MiniLM-L6-v2
and similar models), which typically range 0.15–0.75 for relevant text pairs.

Thresholds are deliberately lower than raw cosine might suggest:
  - RELIABLE  : score >= 0.45  (strongly relevant chunk)
  - AMBIGUOUS : score >= 0.25  (possibly relevant)
  - UNRELIABLE: score <  0.25  (not grounding this answer)

source_type:
  - "documents"  : at least one chunk is RELIABLE or AMBIGUOUS
  - "ai_knowledge": all chunks are UNRELIABLE or no chunks were retrieved
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

# ── Thresholds ─────────────────────────────────────────────────────────────────
# Calibrated for sentence-transformers cosine similarity (0.0–1.0 scale).
# Typical scores: closely related sentences ~0.5–0.8, unrelated ~0.0–0.3.
_RELIABLE_THRESHOLD   = 0.45
_AMBIGUOUS_THRESHOLD  = 0.25


class Reliability(str, Enum):
    RELIABLE   = "reliable"
    AMBIGUOUS  = "ambiguous"
    UNRELIABLE = "unreliable"


class SourceType(str, Enum):
    DOCUMENTS   = "documents"     # answer grounded in uploaded content
    AI_KNOWLEDGE = "ai_knowledge" # LLM's parametric knowledge, no doc match


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
    source_type: SourceType


def classify_chunk(score: float) -> Reliability:
    """Map cosine similarity score to reliability tier."""
    if score >= _RELIABLE_THRESHOLD:
        return Reliability.RELIABLE
    if score >= _AMBIGUOUS_THRESHOLD:
        return Reliability.AMBIGUOUS
    return Reliability.UNRELIABLE


def _top_chunk_score(chunks: list[dict[str, Any]]) -> float:
    """Return the highest cosine similarity score among retrieved chunks."""
    if not chunks:
        return 0.0
    return max(float(c.get("score", 0.0)) for c in chunks)


def _compute_confidence(
    answer: str,
    chunks: list[dict[str, Any]],
    grades: list[ChunkGrade],
) -> float:
    """Blend cosine score with token overlap for a robust confidence value.

    The final score is a weighted combination:
      - 60 % top cosine similarity (retrieval confidence)
      - 40 % token overlap (answer actually uses the retrieved text)
    """
    if not chunks:
        return 0.0

    # Cosine component — use best chunk score, normalised to 0–1
    cosine_component = min(_top_chunk_score(chunks) / _RELIABLE_THRESHOLD, 1.0)

    # Token overlap component
    answer_tokens = set(re.findall(r"\w+", answer.lower()))
    if not answer_tokens:
        return round(cosine_component * 0.6, 3)

    best_overlap = 0.0
    for chunk in chunks:
        chunk_tokens = set(re.findall(r"\w+", chunk.get("text", "").lower()))
        if chunk_tokens:
            overlap = len(answer_tokens & chunk_tokens) / max(len(answer_tokens), 1)
            best_overlap = max(best_overlap, overlap)

    return round(cosine_component * 0.6 + best_overlap * 0.4, 3)


def evaluate(
    answer: str,
    chunks: list[dict[str, Any]],
) -> GraderResult:
    grades: list[ChunkGrade] = []
    for chunk in chunks:
        score = float(chunk.get("score", 0.0))
        grades.append(ChunkGrade(
            chunk_id=str(chunk.get("chunk_id", "")),
            reliability=classify_chunk(score),
            score=round(score, 4),
        ))

    has_grounding = any(
        g.reliability in (Reliability.RELIABLE, Reliability.AMBIGUOUS)
        for g in grades
    )

    source_type = SourceType.DOCUMENTS if has_grounding else SourceType.AI_KNOWLEDGE
    confidence  = _compute_confidence(answer, chunks, grades) if has_grounding else 0.0

    return GraderResult(
        confidence=confidence,
        chunk_grades=grades,
        answer=answer,           # always return the original answer
        verified=confidence >= 0.3,
        source_type=source_type,
    )
