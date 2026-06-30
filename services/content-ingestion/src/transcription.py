"""Whisper transcription via OpenAI API."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    confidence: float = 1.0


class WhisperClientProtocol(Protocol):
    async def transcribe(self, file_path: str, content_type: str) -> list[TranscriptSegment]: ...


SUPPORTED_AUDIO_TYPES = {"mp4", "mp3", "wav", "webm"}


class WhisperTranscriber:
    """Calls OpenAI Whisper API (mockable)."""

    def __init__(self, client: WhisperClientProtocol | None = None) -> None:
        self._client = client

    async def transcribe(self, file_path: str, content_type: str) -> list[TranscriptSegment]:
        ext = content_type.lower().lstrip(".")
        if ext not in SUPPORTED_AUDIO_TYPES:
            raise ValueError(f"Unsupported audio type: {content_type}")
        if self._client is None:
            return [TranscriptSegment(0.0, 1.0, "mock transcript", confidence=0.95)]
        return await self._client.transcribe(file_path, content_type)
