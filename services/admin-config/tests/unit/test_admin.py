"""Admin config unit tests — mocked asyncpg pool."""
import datetime
import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app
from src.retention import RetentionService
from src.service import AdminConfigService


class _InMemoryPool:
    def __init__(self):
        self._store: dict[tuple, dict] = {}

    def acquire(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def fetchrow(self, sql, *args):
        key = (str(args[0]), str(args[1])) if len(args) >= 2 else None
        return self._store.get(key)

    async def fetch(self, sql, *args):
        org = str(args[0]) if args else None
        return [v for k, v in self._store.items() if not org or k[0] == org]

    async def execute(self, sql, *args):
        now = datetime.datetime.utcnow()
        if "INSERT INTO local_admin_config" in sql or "ON CONFLICT" in sql:
            key = (str(args[0]), str(args[1]))
            self._store[key] = {
                "org_id": str(args[0]), "config_key": str(args[1]),
                "config_value": args[2], "description": str(args[3]) if len(args) > 3 else "",
                "updated_at": now,
            }
        elif "DELETE FROM local_admin_config" in sql:
            key = (str(args[0]), str(args[1]))
            self._store.pop(key, None)


@pytest.mark.asyncio
async def test_admin_config_crud():
    pool = _InMemoryPool()
    svc = AdminConfigService(pool=pool)
    await svc.set("org1", "retention_days", 90, "desc")
    result = await svc.get("org1", "retention_days")
    assert result is not None
    all_configs = await svc.list_all("org1")
    assert len(all_configs) == 1
    deleted = await svc.delete("org1", "retention_days")
    assert deleted is True


def test_retention_purge():
    from datetime import timedelta, timezone
    old = datetime.datetime.now(timezone.utc) - datetime.timedelta(days=400)
    store = [{"created_at": old, "email": "test@example.com"}]
    svc = RetentionService(store=store)
    purged = svc.purge(retention_days=365, sensitive_fields=["email"])
    assert purged == 1
    assert len(svc.audit_entries) == 1


@pytest.mark.asyncio
async def test_config_api():
    pool = _InMemoryPool()
    app.state.admin_config = AdminConfigService(pool=pool)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(
            "/api/v1/admin/config/max_tokens?organization_id=default",
            json={"value": 4096},
        )
        assert resp.status_code == 200
        get = await client.get("/api/v1/admin/config/max_tokens?organization_id=default")
        assert get.status_code == 200
