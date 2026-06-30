import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app
from src.service import ContentManagementService

def test_retire_document():
    svc = ContentManagementService()
    kb = svc.create_kb("KB1", "org1")
    doc = svc.create_document(kb.id, "Doc1")
    retired = svc.retire_document(doc.id)
    assert retired.is_active is False
    assert retired.retired_at is not None

@pytest.mark.asyncio
async def test_cms_api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        kb = await client.post("/api/v1/content-mgmt/knowledge-bases", json={"name": "Test KB", "organization_id": "org1"})
        assert kb.status_code == 200
