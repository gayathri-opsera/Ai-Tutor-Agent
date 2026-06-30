from datetime import datetime, timedelta, timezone
import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app
from src.retention import RetentionService
from src.service import AdminConfigService

def test_admin_config_crud():
    svc = AdminConfigService()
    svc.set("org1", "retention_days", 90)
    assert svc.get("org1", "retention_days").value == 90

def test_retention_purge():
    old = datetime.now(timezone.utc) - timedelta(days=400)
    store = [{"created_at": old, "email": "test@example.com"}]
    svc = RetentionService(store=store)
    purged = svc.purge(retention_days=365, sensitive_fields=["email"])
    assert purged == 1
    assert len(svc.audit_entries) == 1

@pytest.mark.asyncio
async def test_config_api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put("/api/v1/admin/config/max_tokens", json={"value": 4096})
        assert resp.status_code == 200
        get = await client.get("/api/v1/admin/config/max_tokens")
        assert get.json()["value"] == 4096
