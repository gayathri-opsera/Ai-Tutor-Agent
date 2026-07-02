"""Local Whisper transcription via faster-whisper (no API key required).

The faster-whisper model is pre-downloaded into the Docker image at build time,
so transcription works fully offline in both local and deployed environments.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import tempfile
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)

# Supported media extensions (video and audio)
SUPPORTED_AUDIO_TYPES = {"mp4", "mp3", "wav", "webm", "m4a", "ogg"}

# Quality threshold: segments with avg_logprob below this are considered low-quality.
# faster-whisper returns avg_logprob per segment; values closer to 0 are better.
QUALITY_THRESHOLD = float(os.getenv("WHISPER_QUALITY_THRESHOLD", "-1.0"))

# Model size: "tiny" (~75MB), "base" (~145MB), "small" (~465MB)
# The Dockerfile pre-downloads WHISPER_MODEL so this env var must match.
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")


@dataclass
class TranscriptSegment:
    start: float          # seconds
    end: float            # seconds
    text: str
    confidence: float = 1.0   # exp(avg_logprob), clamped to [0, 1]
    avg_logprob: float = 0.0  # raw Whisper quality score


@dataclass
class TranscriptionResult:
    segments: list[TranscriptSegment]
    full_text: str
    avg_quality: float          # mean avg_logprob across all segments
    is_low_quality: bool        # True when avg_quality < QUALITY_THRESHOLD
    language: str = "en"


class WhisperClientProtocol(Protocol):
    async def transcribe(self, audio_path: str) -> TranscriptionResult: ...


class FasterWhisperClient:
    """
    Runs Whisper inference locally via faster-whisper.

    The model is loaded once and reused across calls (lazy singleton).
    Inference is CPU-based (int8 quantization) so it works without a GPU.
    The synchronous model.transcribe() call is offloaded to a thread pool
    to avoid blocking the async event loop.
    """

    _model = None  # module-level singleton to avoid reloading on every request

    def _load_model(self):
        if FasterWhisperClient._model is None:
            from faster_whisper import WhisperModel
            logger.info("Loading faster-whisper model '%s'...", WHISPER_MODEL_SIZE)
            FasterWhisperClient._model = WhisperModel(
                WHISPER_MODEL_SIZE,
                device="cpu",
                compute_type="int8",
            )
            logger.info("faster-whisper model loaded.")
        return FasterWhisperClient._model

    def _run_transcription(self, audio_path: str) -> TranscriptionResult:
        model = self._load_model()
        raw_segments, info = model.transcribe(
            audio_path,
            beam_size=5,
            vad_filter=True,  # skip silent sections
        )

        segments: list[TranscriptSegment] = []
        for seg in raw_segments:
            avg_lp = float(getattr(seg, "avg_logprob", 0.0))
            confidence = min(1.0, max(0.0, math.exp(avg_lp)))
            segments.append(TranscriptSegment(
                start=float(seg.start),
                end=float(seg.end),
                text=seg.text.strip(),
                confidence=confidence,
                avg_logprob=avg_lp,
            ))

        full_text = " ".join(s.text for s in segments)
        avg_quality = (
            sum(s.avg_logprob for s in segments) / len(segments)
            if segments else 0.0
        )
        return TranscriptionResult(
            segments=segments,
            full_text=full_text,
            avg_quality=avg_quality,
            is_low_quality=avg_quality < QUALITY_THRESHOLD,
            language=getattr(info, "language", "en") or "en",
        )

    async def transcribe(self, audio_path: str) -> TranscriptionResult:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._run_transcription, audio_path)


class MockWhisperClient:
    """In-process mock used in unit tests — no model loading, instant response."""

    def __init__(self, avg_logprob: float = -0.3, text: str = "mock transcript") -> None:
        self._avg_logprob = avg_logprob
        self._text = text

    async def transcribe(self, audio_path: str) -> TranscriptionResult:
        confidence = min(1.0, max(0.0, math.exp(self._avg_logprob)))
        seg = TranscriptSegment(
            start=0.0, end=5.0,
            text=self._text,
            confidence=confidence,
            avg_logprob=self._avg_logprob,
        )
        return TranscriptionResult(
            segments=[seg],
            full_text=self._text,
            avg_quality=self._avg_logprob,
            is_low_quality=self._avg_logprob < QUALITY_THRESHOLD,
        )


async def extract_audio_from_video(video_bytes: bytes, suffix: str = ".mp4") -> str:
    """
    Write video bytes to a temp file, extract audio track to WAV via ffmpeg.
    Returns path to the extracted WAV file (caller must delete it).
    """
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as vf:
        vf.write(video_bytes)
        video_path = vf.name

    audio_path = video_path + "_audio.wav"
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn",                   # no video
        "-acodec", "pcm_s16le",  # uncompressed PCM
        "-ar", "16000",          # 16 kHz sample rate (Whisper optimum)
        "-ac", "1",              # mono
        audio_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        os.unlink(video_path)
        raise RuntimeError(f"ffmpeg failed: {stderr.decode()[:300]}")

    os.unlink(video_path)
    logger.info("Extracted audio from video to %s", audio_path)
    return audio_path


class WhisperTranscriber:
    """
    Orchestrates audio/video → transcription pipeline using faster-whisper locally.

    For video files (mp4, webm) it first extracts the audio track via ffmpeg,
    then sends the audio to the local Whisper model. For pure audio (mp3, wav,
    m4a, ogg) it sends the bytes directly. No external API key is required.
    """

    def __init__(self, client: WhisperClientProtocol | None = None) -> None:
        # Inject a mock client in tests; default to local faster-whisper
        self._client = client if client is not None else FasterWhisperClient()

    async def transcribe_bytes(
        self, file_bytes: bytes, filename: str
    ) -> TranscriptionResult:
        name_lower = filename.lower()
        ext = name_lower.rsplit(".", 1)[-1] if "." in name_lower else ""

        if ext not in SUPPORTED_AUDIO_TYPES:
            raise ValueError(f"Unsupported media type: .{ext}")

        tmp_audio_path: str | None = None
        try:
            # Video files need audio extraction first
            if ext in {"mp4", "webm"}:
                tmp_audio_path = await extract_audio_from_video(file_bytes, suffix=f".{ext}")
            else:
                # Pure audio — write directly to temp file
                with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as af:
                    af.write(file_bytes)
                    tmp_audio_path = af.name

            result = await self._client.transcribe(tmp_audio_path)
            logger.info(
                "Transcribed %s: %d segments, avg_logprob=%.3f, low_quality=%s",
                filename, len(result.segments), result.avg_quality, result.is_low_quality,
            )
            return result
        finally:
            if tmp_audio_path and os.path.exists(tmp_audio_path):
                os.unlink(tmp_audio_path)

    # Keep backward-compat signature used by existing tests
    async def transcribe(self, file_path: str, content_type: str) -> list[TranscriptSegment]:
        ext = content_type.lower().lstrip(".")
        if ext not in SUPPORTED_AUDIO_TYPES:
            raise ValueError(f"Unsupported audio type: {content_type}")
        result = await self._client.transcribe(file_path)
        return result.segments
