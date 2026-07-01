"""Agent reasoning tests."""
import pytest
from httpx import ASGITransport, AsyncClient

from src.agent import ReActAgent, decompose_query
from src.main import create_app
from src.web_search import WebSearchService


def test_decompose_query():
    parts = decompose_query("What is ML and how does it work?")
    assert len(parts) >= 1


@pytest.mark.asyncio
async def test_react_agent():
    async def retriever(q):
        return [{"text": f"info about {q}"}]
    agent = ReActAgent(retriever=retriever)
    trace = await agent.reason("What is machine learning?")
    assert len(trace.steps) >= 1
    assert trace.final_answer


@pytest.mark.asyncio
async def test_web_search_fallback():
    svc = WebSearchService(confidence_threshold=0.5)
    results = await svc.search_if_needed("test query", confidence=0.3)
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_reason_api():
    app = create_app()
    # ASGITransport does not trigger the lifespan, so inject the agent directly
    async def _mock_retriever(q, **_):
        return [{"text": f"info about {q}", "score": 0.8}]
    app.state.react_agent = ReActAgent(retriever=_mock_retriever)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/internal/agent/reason", json={"query": "What is AI?"})
    assert resp.status_code == 200
    assert "steps" in resp.json()
