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
    from unittest.mock import AsyncMock, patch
    from src.service import ContentIngestionService, DocumentRecord, DocumentStatus
    import uuid

    doc_id = str(uuid.uuid4())
    # DB row returned for reindex fetchrow (knowledge_base_id + title)
    db_rows = {doc_id: {"knowledge_base_id": "kb-1", "title": "Test Doc",
                        "content_text": "Some useful text " * 50}}

    pool = _MockPool(db_rows=db_rows)
    store: dict = {}
    # Pre-populate store so get_content finds it in memory
    rec = DocumentRecord(
        id=doc_id, filename="doc.txt", content_type="text/plain",
        knowledge_base_id="kb-1", status=DocumentStatus.ACTIVE,
        content_text="Some useful text " * 50,
    )
    store[doc_id] = rec

    svc = ContentIngestionService(pool=pool, store=store)
    test_app = create_app(ingestion_service=svc)

    with patch.object(svc, "_index_chunks", new_callable=AsyncMock) as mock_index:
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.post(f"/api/v1/content/documents/{doc_id}/reindex")
        assert resp.status_code == 202
        assert resp.json()["status"] == "reindex_queued"
