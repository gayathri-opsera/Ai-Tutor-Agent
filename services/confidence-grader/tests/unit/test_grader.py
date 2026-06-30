"""Confidence grader tests."""
import pytest
from httpx import ASGITransport, AsyncClient

from src.grader import Reliability, classify_chunk, evaluate
from src.main import create_app


def test_classify_chunk():
    assert classify_chunk(0.8) == Reliability.RELIABLE
    assert classify_chunk(0.5) == Reliability.AMBIGUOUS
    assert classify_chunk(0.2) == Reliability.UNRELIABLE


def test_evaluate_unreliable():
    result = evaluate("some answer", [{"chunk_id": "c1", "text": "unrelated", "score": 0.1}])
    assert "don't have enough information" in result.answer
    assert result.confidence == 0.0


def test_evaluate_reliable():
    result = evaluate(
        "machine learning is great",
        [{"chunk_id": "c1", "text": "machine learning is a subset of AI", "score": 0.9}],
    )
    assert result.verified is True


@pytest.mark.asyncio
async def test_grader_api():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/internal/grader/evaluate", json={
            "answer": "test", "chunks": [{"chunk_id": "1", "text": "test content", "score": 0.8}]
        })
    assert resp.status_code == 200
    assert "confidence" in resp.json()
