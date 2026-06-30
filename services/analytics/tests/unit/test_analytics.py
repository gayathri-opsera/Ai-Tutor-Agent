import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app
from src.service import AnalyticsService

@pytest.mark.asyncio
async def test_analytics_summary():
    svc = AnalyticsService()
    await svc.consume({"event_type": "session.created", "user_id": "u1"})
    await svc.consume({"event_type": "query.submitted", "user_id": "u1", "topic": "math"})
    await svc.consume({"event_type": "rating.submitted", "user_id": "u1", "rating": 5})
    summary = svc.summary()
    assert summary["session_count"] == 1
    assert summary["query_volume"] == 1

@pytest.mark.asyncio
async def test_analytics_api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/analytics/summary")
        assert resp.status_code == 200
