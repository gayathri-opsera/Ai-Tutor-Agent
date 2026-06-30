"""Tests for metrics library."""
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.health import create_health_router
from src.metrics import MetricsRegistry


@pytest.mark.asyncio
async def test_health_endpoints():
    app = FastAPI()
    app.include_router(create_health_router())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        health = await client.get("/health")
        ready = await client.get("/ready")
        metrics = await client.get("/metrics")
    assert health.status_code == 200
    assert ready.status_code == 200
    assert metrics.status_code == 200
    assert b"http_requests_total" in metrics.content


def test_metrics_registry():
    reg = MetricsRegistry("test-svc")
    reg.record_request("GET", "/api", 200, 0.05)
    reg.record_tokens("gpt-4", "prompt", 100)
