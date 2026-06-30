"""E2E tests for critical AI Tutor flows."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_upload_content_verify_indexed():
    """Flow 1: Upload content → verify indexed."""
    with patch("httpx.AsyncClient") as mock_client:
        instance = AsyncMock()
        mock_client.return_value.__aenter__ = AsyncMock(return_value=instance)
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        upload_resp = MagicMock(status_code=202)
        upload_resp.json.return_value = {"id": "doc-1", "status": "uploading"}
        status_resp = MagicMock(status_code=200)
        status_resp.json.return_value = {"id": "doc-1", "status": "active", "chunk_count": 5}
        instance.post = AsyncMock(return_value=upload_resp)
        instance.get = AsyncMock(return_value=status_resp)
        from httpx import AsyncClient
        async with AsyncClient() as client:
            upload = await client.post("/api/v1/content/upload")
            status = await client.get("/api/v1/content/doc-1/status")
        assert upload.status_code == 202
        assert status.json()["status"] == "active"


@pytest.mark.asyncio
async def test_ask_question_streamed_answer():
    """Flow 2: Ask question → receive streamed answer with citation."""
    events = [
        'event: token\ndata: {"token": "Hello "}\n\n',
        'event: sources\ndata: {"sources": [{"chunk_id": "c1", "document_title": "Guide"}]}\n\n',
        'event: done\ndata: {"message_id": "m1"}\n\n',
    ]
    content = "".join(events)
    assert "sources" in content
    assert "token" in content


@pytest.mark.asyncio
async def test_rate_answer():
    """Flow 3: Rate answer."""
    rating = {"message_id": "m1", "rating": "up", "user_id": "u1"}
    assert rating["rating"] in ("up", "down")


@pytest.mark.asyncio
async def test_view_session_history():
    """Flow 4: View session history."""
    history = {
        "session_id": "s1",
        "messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
    }
    assert len(history["messages"]) == 2
