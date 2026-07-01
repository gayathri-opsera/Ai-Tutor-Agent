"""Content ingestion tests."""
import pytest
from httpx import ASGITransport, AsyncClient

from src.chunking import chunk_text
from src.dedup import compute_minhash, find_duplicate
from src.main import create_app
from src.quality_flag import flag_transcription
from src.transcription import TranscriptSegment, WhisperTranscriber
from src.url_ingestion import URLIngestionService


def test_chunk_text_overlap():
    text = "word " * 300 + "\n\n" + "para " * 300
    chunks = chunk_text(text, min_words=200, max_words=500, overlap_words=50)
    assert len(chunks) >= 1


def test_dedup_detects_similar():
    sig_a = compute_minhash("the quick brown fox jumps over the lazy dog")
    sig_b = compute_minhash("the quick brown fox jumps over lazy dog")
    dup = find_duplicate(
        ["the quick brown fox jumps over the lazy dog"],
        [("doc-1", sig_a)],
        threshold=0.5,
    )
    assert dup == "doc-1"


@pytest.mark.asyncio
async def test_whisper_transcriber():
    segments = await WhisperTranscriber().transcribe("test.mp3", "mp3")
    assert len(segments) == 1


def test_quality_flag_low_confidence():
    segs = [TranscriptSegment(0, 1, "hi", confidence=0.3)]
    flag = flag_transcription(segs, threshold=0.7)
    assert flag.flagged is True


@pytest.mark.asyncio
async def test_url_ingestion():
    class MockClient:
        async def get(self, url, **kwargs):
            class R:
                status_code = 200
                text = "<html><body><p>Hello world content here</p></body></html>"
                def raise_for_status(self): pass
            return R()
        async def aclose(self): pass
    chunks = await URLIngestionService(http_client=MockClient()).fetch_and_chunk("http://example.com")
    assert len(chunks) >= 1


@pytest.mark.asyncio
async def test_upload_api():
    from unittest.mock import AsyncMock, MagicMock
    from src.service import ContentIngestionService

    # Minimal pool mock — execute is a no-op, all state lives in the in-memory store
    class _MockPool:
        def acquire(self): return self
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def execute(self, *_a, **_kw): pass

    store: dict = {}
    svc = ContentIngestionService(pool=_MockPool(), store=store)
    test_app = create_app(ingestion_service=svc)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/content/upload",
            data={"knowledge_base_id": "kb-1"},
            files={"file": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    assert resp.status_code == 202
    doc_id = resp.json()["id"]

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        status = await client.get(f"/api/v1/content/{doc_id}/status")
    assert status.status_code == 200
