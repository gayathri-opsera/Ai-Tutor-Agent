import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app
from src.service import LearnerProfileService

@pytest.mark.asyncio
async def test_profile_crud():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/learner/profile")
        assert resp.status_code == 200
        upd = await client.put("/api/v1/learner/profile", json={"display_name": "Test User"})
        assert upd.status_code == 200

def test_progress_tracking():
    svc = LearnerProfileService()
    svc.update_topic("u1", "math", "mastered", 0.95)
    progress = svc.get_progress("u1")
    assert "math" in progress["mastered"]
