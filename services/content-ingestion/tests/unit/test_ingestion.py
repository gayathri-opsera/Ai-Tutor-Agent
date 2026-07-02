"""Content ingestion tests."""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient

from src.chunking import chunk_text
from src.dedup import compute_minhash, find_duplicate
from src.main import create_app
from src.quality_flag import flag_transcription
from src.transcription import (
    TranscriptSegment, TranscriptionResult, WhisperTranscriber,
    MockWhisperClient, QUALITY_THRESHOLD,
)
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
    # Inject MockWhisperClient to avoid loading the local model in unit tests
    transcriber = WhisperTranscriber(client=MockWhisperClient())
    segments = await transcriber.transcribe("test.mp3", "mp3")
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


class _MockPool:
    """Minimal asyncpg pool mock for content-ingestion tests."""
    def __init__(self, db_rows=None):
        self._rows = db_rows or {}

    def acquire(self): return self
    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass
    async def execute(self, *_a, **_kw): pass

    async def fetchrow(self, sql, *args):
        doc_id = str(args[0]) if args else None
        return self._rows.get(doc_id)


@pytest.mark.asyncio
async def test_upload_api():
    from src.service import ContentIngestionService

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


@pytest.mark.asyncio
async def test_upload_api_unsupported_file():
    """Cover the 400 path for unsupported file types."""
    from src.service import ContentIngestionService

    svc = ContentIngestionService(pool=_MockPool(), store={})
    test_app = create_app(ingestion_service=svc)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/content/upload",
            data={"knowledge_base_id": "kb-1"},
            files={"file": ("test.exe", b"binary", "application/octet-stream")},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_status_db_fallback():
    """Cover the DB fallback path in get_status when doc not in memory store."""
    from src.service import ContentIngestionService

    # DB has a row for doc-999
    db_rows = {"doc-999": {"id": "doc-999", "status": "active", "chunk_count": 3}}
    pool = _MockPool(db_rows=db_rows)
    svc = ContentIngestionService(pool=pool, store={})
    test_app = create_app(ingestion_service=svc)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/v1/content/doc-999/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


@pytest.mark.asyncio
async def test_get_status_not_found():
    """Cover the 404 path when doc is in neither memory nor DB."""
    from src.service import ContentIngestionService

    svc = ContentIngestionService(pool=_MockPool(), store={})
    test_app = create_app(ingestion_service=svc)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/v1/content/nonexistent-doc/status")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_document_content_not_found():
    """Cover the 404 path in get_document_content."""
    from src.service import ContentIngestionService

    svc = ContentIngestionService(pool=_MockPool(), store={})
    test_app = create_app(ingestion_service=svc)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/v1/content/documents/nonexistent/content")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_document_content_found():
    """Cover the success path in get_document_content."""
    from src.service import ContentIngestionService, DocumentRecord, DocumentStatus

    store: dict = {}
    svc = ContentIngestionService(pool=_MockPool(), store=store)
    # Manually inject a record with content_text
    import uuid
    doc_id = str(uuid.uuid4())
    rec = DocumentRecord(
        id=doc_id,
        filename="sample.txt",
        content_type="text/plain",
        knowledge_base_id="kb-1",
        status=DocumentStatus.ACTIVE,
        content_text="Hello world content",
    )
    store[doc_id] = rec
    test_app = create_app(ingestion_service=svc)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/content/documents/{doc_id}/content")
    assert resp.status_code == 200
    assert "content" in resp.json()


@pytest.mark.asyncio
async def test_reindex_document_not_found():
    """Cover the 404 path in reindex_document."""
    from src.service import ContentIngestionService

    svc = ContentIngestionService(pool=_MockPool(), store={})
    test_app = create_app(ingestion_service=svc)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.post("/api/v1/content/documents/nonexistent/reindex")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_status_db_exception():
    """Cover the except-pass path in get_status DB fallback."""
    from src.service import ContentIngestionService

    class _BrokenPool:
        def acquire(self): return self
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def execute(self, *_, **__): pass
        async def fetchrow(self, *_, **__):
            raise Exception("DB connection refused")

    svc = ContentIngestionService(pool=_BrokenPool(), store={})
    test_app = create_app(ingestion_service=svc)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/v1/content/any-doc-id/status")
    # Should return 404 even when DB throws (exception is silenced)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_service_status_lifecycle():
    """Cover mark_processing, mark_active, mark_error on the service."""
    from src.service import ContentIngestionService, DocumentStatus

    store: dict = {}
    svc = ContentIngestionService(pool=_MockPool(), store=store)
    test_app = create_app(ingestion_service=svc)

    # Upload to get a real doc in the store
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/content/upload",
            data={"knowledge_base_id": "kb-1"},
            files={"file": ("hello.txt", b"Hello world text content here for testing", "text/plain")},
        )
    assert resp.status_code == 202
    doc_id = resp.json()["id"]

    # Exercise service lifecycle methods
    await svc.mark_processing(doc_id)
    assert store[doc_id].status == DocumentStatus.PROCESSING

    await svc.mark_active(doc_id, ["chunk-1", "chunk-2"])
    assert store[doc_id].status == DocumentStatus.ACTIVE
    assert len(store[doc_id].chunks) == 2

    await svc.mark_error(doc_id, "test error")
    assert store[doc_id].status == DocumentStatus.ERROR
    assert store[doc_id].error == "test error"


@pytest.mark.asyncio
async def test_get_content_from_db():
    """Cover get_content DB fallback path."""
    from src.service import ContentIngestionService

    db_rows = {"doc-abc": {"content_text": "DB content here", "title": "My Doc"}}
    pool = _MockPool(db_rows=db_rows)
    svc = ContentIngestionService(pool=pool, store={})

    result = await svc.get_content("doc-abc")
    assert result == "DB content here"


@pytest.mark.asyncio
async def test_get_content_from_db_empty_text():
    """Cover get_content DB path with empty content_text."""
    from src.service import ContentIngestionService

    db_rows = {"doc-xyz": {"content_text": "", "title": "Empty Doc"}}
    pool = _MockPool(db_rows=db_rows)
    svc = ContentIngestionService(pool=pool, store={})

    result = await svc.get_content("doc-xyz")
    assert "Empty Doc" in result


@pytest.mark.asyncio
async def test_get_content_not_in_db():
    """Cover get_content returning None when no DB row."""
    from src.service import ContentIngestionService

    svc = ContentIngestionService(pool=_MockPool(), store={})
    result = await svc.get_content("does-not-exist")
    assert result is None


@pytest.mark.asyncio
async def test_reindex_with_content():
    """Cover the reindex endpoint when doc has content — queues and runs background task."""
    from src.service import ContentIngestionService, DocumentRecord, DocumentStatus
    import uuid

    doc_id = str(uuid.uuid4())
    db_rows = {doc_id: {"knowledge_base_id": "kb-1", "title": "Test Doc",
                        "content_text": "Some useful text " * 50}}

    pool = _MockPool(db_rows=db_rows)
    store: dict = {}
    rec = DocumentRecord(
        id=doc_id, filename="doc.txt", content_type="text/plain",
        knowledge_base_id="kb-1", status=DocumentStatus.ACTIVE,
        content_text="Some useful text " * 50,
    )
    store[doc_id] = rec

    svc = ContentIngestionService(pool=pool, store=store)
    test_app = create_app(ingestion_service=svc)

    with patch.object(svc, "_index_chunks", new_callable=AsyncMock):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.post(f"/api/v1/content/documents/{doc_id}/reindex")
        assert resp.status_code == 202
        assert resp.json()["status"] == "reindex_queued"


# ── Transcription (WO-011) ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mock_whisper_client_good_quality():
    """MockWhisperClient returns a result above the quality threshold."""
    client = MockWhisperClient(avg_logprob=-0.3)
    result = await client.transcribe("dummy.mp3")
    assert isinstance(result, TranscriptionResult)
    assert result.full_text == "mock transcript"
    assert result.is_low_quality is False


@pytest.mark.asyncio
async def test_mock_whisper_client_low_quality():
    """avg_logprob below QUALITY_THRESHOLD → is_low_quality=True."""
    client = MockWhisperClient(avg_logprob=-2.0)
    result = await client.transcribe("dummy.mp3")
    assert result.is_low_quality is True


@pytest.mark.asyncio
async def test_whisper_transcriber_bytes_audio():
    """WhisperTranscriber.transcribe_bytes for an MP3 calls the mock client."""
    mock_client = MockWhisperClient(avg_logprob=-0.5, text="hello world")
    transcriber = WhisperTranscriber(client=mock_client)
    result = await transcriber.transcribe_bytes(b"fake audio bytes", "lecture.mp3")
    assert result.full_text == "hello world"
    assert len(result.segments) == 1


@pytest.mark.asyncio
async def test_whisper_transcriber_bytes_unsupported():
    """Unsupported extension raises ValueError."""
    transcriber = WhisperTranscriber(client=MockWhisperClient())
    with pytest.raises(ValueError, match="Unsupported"):
        await transcriber.transcribe_bytes(b"data", "file.xyz")


@pytest.mark.asyncio
async def test_upload_video_file_good_quality():
    """Uploading an MP4 with good transcription → status active, chunks indexed."""
    from src.service import ContentIngestionService

    mock_client = MockWhisperClient(avg_logprob=-0.3, text="This is a lecture about Python. " * 30)
    transcriber = WhisperTranscriber(client=mock_client)
    store: dict = {}
    svc = ContentIngestionService(pool=_MockPool(), store=store, transcriber=transcriber)
    test_app = create_app(ingestion_service=svc)

    with patch.object(svc, "_index_chunks", new_callable=AsyncMock):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/content/upload",
                data={"knowledge_base_id": "kb-1"},
                files={"file": ("lecture.mp3", b"fake audio", "audio/mpeg")},
            )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "active"
    assert data["chunk_count"] > 0


@pytest.mark.asyncio
async def test_upload_video_file_low_quality_sets_pending_review():
    """Uploading an MP4 with low-quality transcription → status pending_review, NOT indexed."""
    from src.service import ContentIngestionService

    mock_client = MockWhisperClient(avg_logprob=-2.5, text="garbled noisy text " * 10)
    transcriber = WhisperTranscriber(client=mock_client)
    store: dict = {}
    svc = ContentIngestionService(pool=_MockPool(), store=store, transcriber=transcriber)
    test_app = create_app(ingestion_service=svc)

    with patch.object(svc, "_index_chunks", new_callable=AsyncMock) as mock_idx:
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/content/upload",
                data={"knowledge_base_id": "kb-1"},
                files={"file": ("noisy.mp3", b"fake audio", "audio/mpeg")},
            )
    assert resp.status_code == 202
    assert resp.json()["status"] == "pending_review"
    mock_idx.assert_not_called()   # must NOT index low-quality content


@pytest.mark.asyncio
async def test_upload_unsupported_media_type():
    """Unknown extension returns 400."""
    from src.service import ContentIngestionService
    svc = ContentIngestionService(pool=_MockPool(), store={})
    test_app = create_app(ingestion_service=svc)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/content/upload",
            data={"knowledge_base_id": "kb-1"},
            files={"file": ("file.avi", b"data", "video/avi")},
        )
    assert resp.status_code == 400


# ── Transcription review API (WO-024) ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_transcription_in_memory():
    """GET /{doc_id}/transcription returns segments when record is in memory."""
    from src.service import ContentIngestionService, DocumentRecord, DocumentStatus
    import uuid

    doc_id = str(uuid.uuid4())
    store = {
        doc_id: DocumentRecord(
            id=doc_id, filename="lec.mp3", content_type="audio/mpeg",
            knowledge_base_id="kb-1", status=DocumentStatus.PENDING_REVIEW,
            content_text="transcribed text",
            transcription_segments=[{"start": 0.0, "end": 5.0, "text": "hi", "confidence": 0.4, "avg_logprob": -2.0}],
            transcription_quality=-2.0,
        )
    }
    svc = ContentIngestionService(pool=_MockPool(), store=store)
    test_app = create_app(ingestion_service=svc)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/content/{doc_id}/transcription")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending_review"
    assert len(data["segments"]) == 1


@pytest.mark.asyncio
async def test_get_transcription_no_segments_returns_404():
    """GET transcription returns 404 when no transcription_segments."""
    from src.service import ContentIngestionService, DocumentRecord, DocumentStatus
    import uuid

    doc_id = str(uuid.uuid4())
    store = {
        doc_id: DocumentRecord(
            id=doc_id, filename="doc.pdf", content_type="application/pdf",
            knowledge_base_id="kb-1", status=DocumentStatus.ACTIVE,
        )
    }
    svc = ContentIngestionService(pool=_MockPool(), store=store)
    test_app = create_app(ingestion_service=svc)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/content/{doc_id}/transcription")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_put_transcription_approve():
    """PUT transcription with approve=true → status active and re-indexed."""
    from src.service import ContentIngestionService, DocumentRecord, DocumentStatus
    import uuid

    doc_id = str(uuid.uuid4())
    store = {
        doc_id: DocumentRecord(
            id=doc_id, filename="lec.mp3", content_type="audio/mpeg",
            knowledge_base_id="kb-1", status=DocumentStatus.PENDING_REVIEW,
            content_text="garbled", transcription_segments=[],
            transcription_quality=-2.0,
        )
    }
    db_rows = {doc_id: {"knowledge_base_id": "kb-1", "title": "lec.mp3"}}
    svc = ContentIngestionService(pool=_MockPool(db_rows=db_rows), store=store)
    test_app = create_app(ingestion_service=svc)

    with patch.object(svc, "_index_chunks", new_callable=AsyncMock) as mock_idx:
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.put(
                f"/api/v1/content/{doc_id}/transcription",
                json={"text": "This is the corrected lecture transcript. " * 20, "approve": True},
            )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"
    mock_idx.assert_called_once()


@pytest.mark.asyncio
async def test_put_transcription_save_no_approve():
    """PUT transcription with approve=false → status stays pending_review."""
    from src.service import ContentIngestionService, DocumentRecord, DocumentStatus
    import uuid

    doc_id = str(uuid.uuid4())
    store = {
        doc_id: DocumentRecord(
            id=doc_id, filename="lec.mp3", content_type="audio/mpeg",
            knowledge_base_id="kb-1", status=DocumentStatus.PENDING_REVIEW,
            content_text="garbled", transcription_segments=[],
        )
    }
    svc = ContentIngestionService(pool=_MockPool(), store=store)
    test_app = create_app(ingestion_service=svc)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.put(
            f"/api/v1/content/{doc_id}/transcription",
            json={"text": "Still editing...", "approve": False},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending_review"


@pytest.mark.asyncio
async def test_put_transcription_not_found():
    """PUT transcription for unknown doc → 404."""
    from src.service import ContentIngestionService
    svc = ContentIngestionService(pool=_MockPool(), store={})
    test_app = create_app(ingestion_service=svc)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.put(
            "/api/v1/content/nonexistent/transcription",
            json={"text": "fixed", "approve": True},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_transcription_db_fallback():
    """GET transcription falls back to DB when not in memory."""
    from src.service import ContentIngestionService
    import uuid

    doc_id = str(uuid.uuid4())
    db_rows = {doc_id: {"id": doc_id, "status": "pending_review", "content_text": "some text"}}
    svc = ContentIngestionService(pool=_MockPool(db_rows=db_rows), store={})
    test_app = create_app(ingestion_service=svc)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/content/{doc_id}/transcription")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending_review"


@pytest.mark.asyncio
async def test_get_transcription_not_found():
    """GET transcription returns 404 when not in memory or DB."""
    from src.service import ContentIngestionService
    svc = ContentIngestionService(pool=_MockPool(), store={})
    test_app = create_app(ingestion_service=svc)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/v1/content/no-such-doc/transcription")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_put_transcription_wrong_status():
    """PUT transcription for a document in 'error' status → 400."""
    from src.service import ContentIngestionService, DocumentRecord, DocumentStatus
    import uuid

    doc_id = str(uuid.uuid4())
    store = {
        doc_id: DocumentRecord(
            id=doc_id, filename="lec.mp3", content_type="audio/mpeg",
            knowledge_base_id="kb-1", status=DocumentStatus.ERROR,
        )
    }
    svc = ContentIngestionService(pool=_MockPool(), store=store)
    test_app = create_app(ingestion_service=svc)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.put(
            f"/api/v1/content/{doc_id}/transcription",
            json={"text": "fixed", "approve": True},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upload_transcription_error_status():
    """If transcriber raises an exception, document gets error status."""
    from src.service import ContentIngestionService

    class _FailingClient:
        async def transcribe(self, audio_path):
            raise RuntimeError("Whisper API down")

    transcriber = WhisperTranscriber(client=_FailingClient())
    svc = ContentIngestionService(pool=_MockPool(), store={}, transcriber=transcriber)
    test_app = create_app(ingestion_service=svc)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/content/upload",
            data={"knowledge_base_id": "kb-1"},
            files={"file": ("lecture.mp3", b"fake", "audio/mpeg")},
        )
    assert resp.status_code == 202
    assert resp.json()["status"] == "error"


@pytest.mark.asyncio
async def test_whisper_transcriber_video_mocks_ffmpeg():
    """WhisperTranscriber.transcribe_bytes for MP4 calls extract_audio then transcribes."""
    import tempfile, os
    mock_client = MockWhisperClient(avg_logprob=-0.5, text="video lecture")
    transcriber = WhisperTranscriber(client=mock_client)

    # Patch ffmpeg subprocess so we don't need a real ffmpeg in CI
    async def _fake_extract(video_bytes, suffix=".mp4"):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"fake wav")
            return f.name

    with patch("src.transcription.extract_audio_from_video", side_effect=_fake_extract):
        result = await transcriber.transcribe_bytes(b"fake video", "demo.mp4")
    assert result.full_text == "video lecture"


@pytest.mark.asyncio
async def test_whisper_transcriber_backward_compat_transcribe():
    """The legacy transcribe(file_path, content_type) API still works."""
    mock_client = MockWhisperClient(avg_logprob=-0.3, text="legacy")
    transcriber = WhisperTranscriber(client=mock_client)
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(b"fake")
        path = f.name
    try:
        segments = await transcriber.transcribe(path, "mp3")
        assert len(segments) >= 1
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_whisper_transcriber_backward_compat_unsupported():
    """Legacy transcribe raises ValueError for unsupported types."""
    transcriber = WhisperTranscriber(client=MockWhisperClient())
    with pytest.raises(ValueError):
        await transcriber.transcribe("file.avi", "avi")


@pytest.mark.asyncio
async def test_extract_audio_ffmpeg_failure():
    """extract_audio_from_video raises RuntimeError when ffmpeg exits non-zero."""
    import asyncio
    from src.transcription import extract_audio_from_video

    async def _fake_exec(*args, **kwargs):
        class _Proc:
            returncode = 1
            async def communicate(self):
                return (b"", b"ffmpeg error message")
        return _Proc()

    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        with pytest.raises(RuntimeError, match="ffmpeg failed"):
            await extract_audio_from_video(b"fake video bytes", ".mp4")


@pytest.mark.asyncio
async def test_index_chunks_with_segment_metadata():
    """_index_chunks passes start/end timestamp metadata per chunk."""
    from src.service import ContentIngestionService

    svc = ContentIngestionService(pool=_MockPool(), store={})
    payload_sent = {}

    async def _fake_post(url, json, **_):
        payload_sent.update(json)
        class _Resp:
            def raise_for_status(self): pass
            def json(self): return {"indexed": 1}
        return _Resp()

    with patch("src.service.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(side_effect=_fake_post)
        mock_cls.return_value = mock_http

        await svc._index_chunks(
            doc_id="d1", knowledge_base_id="kb1", document_title="lec.mp4",
            chunks=["chunk one"], segment_metadata=[{"start": 0.0, "end": 5.0}],
        )
    assert payload_sent["chunks"][0]["start_time"] == 0.0
    assert payload_sent["chunks"][0]["end_time"] == 5.0


# ── MinIO / media storage tests ───────────────────────────────────────────────

def test_upload_to_minio_returns_false_when_unavailable():
    """_upload_to_minio gracefully returns False when MinIO is unreachable."""
    import src.service as svc_mod
    with patch.object(svc_mod, "_get_minio_client", return_value=None):
        result = svc_mod._upload_to_minio("kb/doc/file.mp4", b"bytes", "video/mp4")
    assert result is False


def test_upload_to_minio_returns_false_on_put_error():
    """_upload_to_minio returns False when put_object raises."""
    import src.service as svc_mod

    class _FakeClient:
        def put_object(self, *a, **kw):
            raise RuntimeError("network error")

    with patch.object(svc_mod, "_get_minio_client", return_value=_FakeClient()):
        result = svc_mod._upload_to_minio("kb/doc/file.mp4", b"bytes", "video/mp4")
    assert result is False


def test_get_minio_url_returns_none_when_unavailable():
    """get_minio_url returns None gracefully when MinIO is unreachable."""
    import src.service as svc_mod
    with patch.object(svc_mod, "_get_minio_client", return_value=None):
        url = svc_mod.get_minio_url("kb/doc/file.mp4")
    assert url is None


def test_get_minio_url_returns_url_via_client():
    """get_minio_url returns a URL when minio client is available."""
    import src.service as svc_mod
    from datetime import timedelta

    class _FakeClient:
        def presigned_get_object(self, bucket, key, expires):
            return f"http://minio/{bucket}/{key}?presigned=1"

    with patch.object(svc_mod, "_get_minio_client", return_value=_FakeClient()):
        url = svc_mod.get_minio_url("kb/doc/file.mp4")
    assert url == "http://minio/ai-tutor-content/kb/doc/file.mp4?presigned=1"


def test_get_minio_url_returns_none_on_client_error():
    """get_minio_url returns None when presigned_get_object raises."""
    import src.service as svc_mod

    class _FakeClient:
        def presigned_get_object(self, *a, **kw):
            raise RuntimeError("access denied")

    with patch.object(svc_mod, "_get_minio_client", return_value=_FakeClient()):
        url = svc_mod.get_minio_url("kb/doc/file.mp4")
    assert url is None


def test_get_minio_client_returns_none_on_import_error():
    """_get_minio_client returns None when minio package is unavailable."""
    import src.service as svc_mod
    import builtins, importlib
    original_import = builtins.__import__
    def _block_minio(name, *args, **kwargs):
        if name == "minio":
            raise ImportError("no module minio")
        return original_import(name, *args, **kwargs)
    with patch("builtins.__import__", side_effect=_block_minio):
        result = svc_mod._get_minio_client()
    assert result is None


@pytest.mark.asyncio
async def test_get_media_url_returns_none_for_non_media():
    """get_media_url returns None for non-media documents."""
    from src.service import ContentIngestionService, DocumentRecord, DocumentStatus
    store: dict = {
        "doc-text": DocumentRecord(
            id="doc-text", filename="readme.txt", content_type="text/plain",
            knowledge_base_id="kb1", status=DocumentStatus.ACTIVE,
        )
    }
    svc = ContentIngestionService(pool=_MockPool(), store=store)
    result = await svc.get_media_url("doc-text")
    assert result is None


@pytest.mark.asyncio
async def test_get_media_url_uses_presigned_url_for_media():
    """get_media_url returns presigned URL for in-memory media records."""
    import src.service as svc_mod
    from src.service import ContentIngestionService, DocumentRecord, DocumentStatus
    store: dict = {
        "doc-vid": DocumentRecord(
            id="doc-vid", filename="lesson.mp4", content_type="video/mp4",
            knowledge_base_id="kb1", s3_key="kb1/doc-vid/lesson.mp4",
            status=DocumentStatus.ACTIVE,
        )
    }
    svc = ContentIngestionService(pool=_MockPool(), store=store)
    with patch.object(svc_mod, "get_minio_url", return_value="http://minio/presigned"):
        result = await svc.get_media_url("doc-vid")
    assert result == "http://minio/presigned"


@pytest.mark.asyncio
async def test_media_endpoint_detects_content_type_from_db():
    """GET /media falls back to DB title for content-type detection when doc not in store."""
    import src.service as svc_mod
    from src.service import ContentIngestionService

    class _DBPool(_MockPool):
        async def fetchrow(self, sql, *args):
            # Return s3_key for get_media_url, and title for content-type detection
            if "s3_key" in sql:
                return {"s3_key": "kb1/d/vid.mp4"}
            return {"title": "vid.mp4"}

    svc = ContentIngestionService(pool=_DBPool(), store={})
    test_app = create_app(ingestion_service=svc)

    with patch.object(svc_mod, "get_minio_url", return_value="http://minio/url"):
        with patch("src.api.content._httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_resp = AsyncMock()
            mock_resp.content = b"video data"
            mock_resp.status_code = 200
            mock_resp.headers = {}
            mock_resp.raise_for_status = lambda: None
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
                resp = await client.get("/api/v1/content/doc-db-vid/media")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_media_endpoint_forwards_range_header():
    """GET /media forwards the Range header and returns 206 for partial content."""
    import src.service as svc_mod
    from src.service import ContentIngestionService, DocumentRecord, DocumentStatus
    store: dict = {
        "doc-wav": DocumentRecord(
            id="doc-wav", filename="audio.wav", content_type="audio/wav",
            knowledge_base_id="kb1", s3_key="kb1/doc-wav/audio.wav",
            status=DocumentStatus.ACTIVE,
        )
    }
    svc = ContentIngestionService(pool=_MockPool(), store=store)
    test_app = create_app(ingestion_service=svc)

    with patch.object(svc_mod, "get_minio_url", return_value="http://minio/audio-url"):
        with patch("src.api.content._httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_resp = AsyncMock()
            mock_resp.content = b"audio bytes"
            mock_resp.status_code = 206
            mock_resp.headers = {"Content-Range": "bytes 0-100/500", "Content-Length": "101"}
            mock_resp.raise_for_status = lambda: None
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
                resp = await client.get("/api/v1/content/doc-wav/media",
                                        headers={"Range": "bytes=0-100"})
    assert resp.status_code == 206
    assert resp.headers.get("Content-Range") == "bytes 0-100/500"


@pytest.mark.asyncio
async def test_media_endpoint_handles_minio_fetch_error():
    """GET /media returns 502 when MinIO fetch fails."""
    import src.service as svc_mod
    from src.service import ContentIngestionService, DocumentRecord, DocumentStatus
    store: dict = {
        "doc-err": DocumentRecord(
            id="doc-err", filename="broken.mp4", content_type="video/mp4",
            knowledge_base_id="kb1", s3_key="kb1/doc-err/broken.mp4",
            status=DocumentStatus.ACTIVE,
        )
    }
    svc = ContentIngestionService(pool=_MockPool(), store=store)
    test_app = create_app(ingestion_service=svc)

    with patch.object(svc_mod, "get_minio_url", return_value="http://minio/broken"):
        with patch("src.api.content._httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=RuntimeError("connection refused"))
            mock_cls.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
                resp = await client.get("/api/v1/content/doc-err/media")
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_media_endpoint_returns_404_when_no_url():
    """GET /api/v1/content/{id}/media returns 404 when media not stored."""
    from src.service import ContentIngestionService
    svc = ContentIngestionService(pool=_MockPool(), store={})
    test_app = create_app(ingestion_service=svc)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/v1/content/nonexistent/media", follow_redirects=False)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_media_url_falls_back_to_db():
    """get_media_url falls back to DB s3_key lookup when not in memory store."""
    import src.service as svc_mod
    from src.service import ContentIngestionService

    class _DBPool(_MockPool):
        async def fetchrow(self, sql, *args):
            return {"s3_key": "kb1/doc-db/vid.mp4"}

    svc = ContentIngestionService(pool=_DBPool(), store={})
    with patch.object(svc_mod, "get_minio_url", return_value="http://minio/db-url"):
        result = await svc.get_media_url("doc-db")
    assert result == "http://minio/db-url"


@pytest.mark.asyncio
async def test_get_media_url_returns_none_no_s3_key_in_db():
    """get_media_url returns None when DB row has no s3_key."""
    import src.service as svc_mod
    from src.service import ContentIngestionService

    class _DBPool(_MockPool):
        async def fetchrow(self, sql, *args):
            return {"s3_key": None}

    svc = ContentIngestionService(pool=_DBPool(), store={})
    result = await svc.get_media_url("doc-no-key")
    assert result is None


@pytest.mark.asyncio
async def test_media_endpoint_streams_content():
    """GET /api/v1/content/{id}/media proxies media bytes from MinIO."""
    import src.service as svc_mod
    from src.service import ContentIngestionService, DocumentRecord, DocumentStatus
    store: dict = {
        "doc-mp4": DocumentRecord(
            id="doc-mp4", filename="lesson.mp4", content_type="video/mp4",
            knowledge_base_id="kb1", s3_key="kb1/doc-mp4/lesson.mp4",
            status=DocumentStatus.ACTIVE,
        )
    }
    svc = ContentIngestionService(pool=_MockPool(), store=store)
    test_app = create_app(ingestion_service=svc)

    # Mock get_minio_url to return a URL and patch httpx.AsyncClient used in media endpoint
    with patch.object(svc_mod, "get_minio_url", return_value="http://minio/presigned-url"):
        with patch("src.api.content._httpx") as mock_httpx_mod:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_resp = AsyncMock()
            mock_resp.content = b"fake video bytes"
            mock_resp.status_code = 200
            mock_resp.headers = {"Content-Length": "16"}
            mock_resp.raise_for_status = lambda: None
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_httpx_mod.AsyncClient.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
                resp = await client.get("/api/v1/content/doc-mp4/media", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.content == b"fake video bytes"
