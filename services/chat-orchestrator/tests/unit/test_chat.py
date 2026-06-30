"""Chat orchestrator tests."""
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import create_app
from src.service import ChatOrchestratorService, InMemorySessionCache, MockSessionRepository, Message, Session


@pytest.mark.asyncio
async def test_create_session():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/chat/sessions", json={"user_id": "u1"})
    assert resp.status_code == 200
    assert "id" in resp.json()


@pytest.mark.asyncio
async def test_build_prompt():
    svc = ChatOrchestratorService(InMemorySessionCache(), MockSessionRepository())
    session = Session(id="s1", user_id="u1", messages=[Message(role="user", content="hi")])
    prompt = svc.build_prompt(session, "context chunk")
    assert "context chunk" in prompt
    assert "hi" in prompt


@pytest.mark.asyncio
async def test_history():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/api/v1/chat/sessions", json={"user_id": "u1"})
        sid = created.json()["id"]
        hist = await client.get(f"/api/v1/chat/sessions/{sid}/history")
    assert hist.status_code == 200
