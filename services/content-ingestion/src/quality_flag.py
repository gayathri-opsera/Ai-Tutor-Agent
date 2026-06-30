"""Transcription quality flagging."""
from __future__ import annotations

from dataclasses import dataclass

from src.transcription import TranscriptSegment


@dataclass
class QualityFlag:
    flagged: bool
    reason: str | None = None
    avg_confidence: float = 1.0


def flag_transcription(
    segments: list[TranscriptSegment],
    threshold: float = 0.7,
) -> QualityFlag:
    if not segments:
        return QualityFlag(flagged=True, reason="empty_transcription", avg_confidence=0.0)
    avg = sum(s.confidence for s in segments) / len(segments)
    if avg < threshold:
        return QualityFlag(flagged=True, reason="low_confidence", avg_confidence=avg)
    return QualityFlag(flagged=False, avg_confidence=avg)
