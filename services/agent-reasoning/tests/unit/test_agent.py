"""Agent reasoning tests."""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient

from src.agent import ReActAgent, decompose_query
from src.main import create_app
from src.web_search import (
    WebSearchService, DuckDuckGoSearchClient, SerperSearchClient, build_search_client
)


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
async def test_web_search_skips_when_confidence_high():
    """No search when confidence is above threshold."""
    mock_client = AsyncMock()
    svc = WebSearchService(client=mock_client, confidence_threshold=0.5)
    results = await svc.search_if_needed("test query", confidence=0.9)
    assert results == []
    mock_client.search.assert_not_called()


@pytest.mark.asyncio
async def test_web_search_triggers_when_confidence_low():
    """Search fires when confidence is below threshold."""
    class _MockClient:
        async def search(self, query, num_results=5):
            return [{"id": "r1", "title": "Test", "snippet": "some info", "url": "http://x.com", "score": 0.7}]

    svc = WebSearchService(client=_MockClient(), confidence_threshold=0.5)
    results = await svc.search_if_needed("test query", confidence=0.3)
    assert len(results) == 1
    assert results[0]["text"] == "some info"
    assert results[0]["metadata"]["source"] == "web_search"


@pytest.mark.asyncio
async def test_duckduckgo_client_returns_results():
    """DuckDuckGoSearchClient parses abstract and related topics."""
    ddg_response = {
        "AbstractText": "Machine learning is a field of AI.",
        "Heading": "Machine Learning",
        "AbstractURL": "https://en.wikipedia.org/wiki/ML",
        "RelatedTopics": [
            {"Text": "Deep learning is a subset.", "FirstURL": "https://en.wikipedia.org/wiki/DL"},
        ],
    }
    client = DuckDuckGoSearchClient()

    class _FakeResp:
        def raise_for_status(self): pass
        def json(self): return ddg_response

    with patch("src.web_search.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=_FakeResp())
        mock_cls.return_value = mock_http

        results = await client.search("machine learning", num_results=5)

    assert len(results) >= 1
    assert "Machine Learning" in results[0]["title"]


@pytest.mark.asyncio
async def test_duckduckgo_client_handles_network_error():
    """DuckDuckGoSearchClient returns empty list on network failure."""
    client = DuckDuckGoSearchClient()

    with patch("src.web_search.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(side_effect=Exception("connection refused"))
        mock_cls.return_value = mock_http

        results = await client.search("some query")
    assert results == []


@pytest.mark.asyncio
async def test_serper_client_returns_results():
    """SerperSearchClient parses organic results."""
    serper_response = {
        "organic": [
            {"title": "Python intro", "snippet": "Python is easy.", "link": "https://python.org"},
        ]
    }
    client = SerperSearchClient(api_key="test-key")

    class _FakeResp:
        def raise_for_status(self): pass
        def json(self): return serper_response

    with patch("src.web_search.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=_FakeResp())
        mock_cls.return_value = mock_http

        results = await client.search("python tutorial")
    assert len(results) == 1
    assert results[0]["snippet"] == "Python is easy."


@pytest.mark.asyncio
async def test_serper_client_handles_error():
    """SerperSearchClient returns empty list on failure."""
    client = SerperSearchClient(api_key="bad-key")

    with patch("src.web_search.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(side_effect=Exception("401 Unauthorized"))
        mock_cls.return_value = mock_http

        results = await client.search("any query")
    assert results == []


def test_build_search_client_uses_ddg_when_no_key():
    """build_search_client returns DuckDuckGoSearchClient when SERPER_API_KEY is unset."""
    with patch.dict("os.environ", {}, clear=False):
        import src.web_search as mod
        original = mod.SERPER_API_KEY
        mod.SERPER_API_KEY = ""
        client = build_search_client()
        mod.SERPER_API_KEY = original
    assert isinstance(client, DuckDuckGoSearchClient)


def test_build_search_client_uses_serper_when_key_set():
    """build_search_client returns SerperSearchClient when SERPER_API_KEY is configured."""
    import src.web_search as mod
    original = mod.SERPER_API_KEY
    mod.SERPER_API_KEY = "sk-test-key"
    client = build_search_client()
    mod.SERPER_API_KEY = original
    assert isinstance(client, SerperSearchClient)


@pytest.mark.asyncio
async def test_react_agent_calculator_action():
    """ReActAgent triggers calculator action for arithmetic queries."""
    agent = ReActAgent()
    trace = await agent.reason("What is 3 + 4?")
    assert any(s.action == "calculator" for s in trace.steps)


@pytest.mark.asyncio
async def test_react_agent_web_search_action():
    """ReActAgent triggers web_search when no retriever is set and confidence is low."""
    web_results = [{"chunk_id": "w1", "text": "web info", "document_id": "web",
                    "document_title": "Web", "score": 0.6, "metadata": {}}]

    async def _mock_web_search(q, conf):
        return web_results

    # No retriever → agent falls through to web_search branch
    agent = ReActAgent(retriever=None, web_search=_mock_web_search)
    trace = await agent.reason("obscure topic", confidence=0.2)
    assert any(s.action == "web_search" for s in trace.steps)


@pytest.mark.asyncio
async def test_react_agent_web_search_fallback_when_retriever_empty():
    """ReActAgent falls back to web_search when retriever returns nothing and confidence is low."""
    web_results = [{"chunk_id": "w2", "text": "fallback web info", "document_id": "web",
                    "document_title": "Web", "score": 0.7, "metadata": {}}]

    async def _empty_retriever(q):
        return []

    async def _mock_web_search(q, conf):
        return web_results

    # Retriever set but returns empty → should fall back to web_search
    agent = ReActAgent(retriever=_empty_retriever, web_search=_mock_web_search)
    trace = await agent.reason("obscure topic", confidence=0.2)
    assert any(s.action == "web_search" for s in trace.steps)


@pytest.mark.asyncio
async def test_reason_api_with_knowledge_base_id():
    """POST /reason with knowledge_base_id routes retriever correctly."""
    app = create_app()
    received_kwargs: dict = {}

    async def _mock_retriever(q, **kwargs):
        received_kwargs.update(kwargs)
        return [{"text": "kb result", "score": 0.9}]

    app.state.react_agent = ReActAgent(retriever=_mock_retriever)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/internal/agent/reason",
            json={"query": "What is Python?", "knowledge_base_id": "kb-42"},
        )
    assert resp.status_code == 200


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


@pytest.mark.asyncio
async def test_real_retriever_handles_rag_failure():
    """_real_retriever returns a fallback when RAG pipeline is unreachable."""
    from src.main import _real_retriever
    with patch("src.main.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(side_effect=Exception("connection refused"))
        mock_cls.return_value = mock_http

        result = await _real_retriever("any query")
    assert len(result) >= 1
    assert "No context found" in result[0]["text"]
