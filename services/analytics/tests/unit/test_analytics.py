"""Analytics unit tests — mocked asyncpg pool."""
import json
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app
from src.service import AnalyticsService


class _InMemoryPool:
    def __init__(self):
        self._events: list[dict] = []

    def acquire(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def execute(self, sql, *args):
        if "INSERT INTO local_analytics_events" in sql:
            self._events.append({
                "id": str(args[0]),
                "event_type": str(args[1]),
                "user_id": str(args[2]),
                "topic": str(args[3]),
                "rating": args[4],
                "metadata": args[5],
            })

    async def fetchval(self, sql, *args):
        if "event_type = 'session.created'" in sql:
            return sum(1 for e in self._events if e["event_type"] == "session.created")
        if "event_type = 'query.submitted'" in sql:
            return sum(1 for e in self._events if e["event_type"] == "query.submitted")
        if "AVG(rating)" in sql:
            ratings = [e["rating"] for e in self._events if e["rating"] is not None]
            return sum(ratings) / len(ratings) if ratings else None
        return 0

    async def fetch(self, sql, *args):
        if "GROUP BY topic" in sql:
            counts: dict[str, int] = {}
            for e in self._events:
                t = e.get("topic", "")
                if t:
                    counts[t] = counts.get(t, 0) + 1
            return [{"topic": t, "cnt": c} for t, c in counts.items()]
        return list(self._events[-20:])


@pytest.mark.asyncio
async def test_analytics_summary():
    pool = _InMemoryPool()
    svc = AnalyticsService(pool=pool)
    await svc.consume({"event_type": "session.created", "user_id": "u1"})
    await svc.consume({"event_type": "query.submitted", "user_id": "u1", "topic": "math"})
    await svc.consume({"event_type": "rating.submitted", "user_id": "u1", "rating": 5})
    summary = await svc.summary()
    assert summary["session_count"] == 1
    assert summary["query_volume"] == 1


@pytest.mark.asyncio
async def test_analytics_api():
    pool = _InMemoryPool()
    app.state.analytics = AnalyticsService(pool=pool)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/analytics/summary")
    assert resp.status_code == 200
    assert "session_count" in resp.json()
