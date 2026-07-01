"""Content management unit tests — uses an in-memory asyncpg mock."""
import datetime
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.service import ContentManagementService, Document, KnowledgeBase


class _InMemoryPool:
    """Minimal asyncpg pool that satisfies ContentManagementService queries."""

    def __init__(self):
        self.kbs: dict[str, dict] = {}
        self.docs: dict[str, dict] = {}

    def acquire(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def fetchrow(self, sql, *args):
        if "knowledge_bases" in sql and len(args) == 1:
            row = self.kbs.get(str(args[0]))
            return row
        if "documents" in sql and "WHERE id" in sql:
            row = self.docs.get(str(args[0]))
            return row
        return None

    async def fetch(self, sql, *args):
        if "knowledge_bases" in sql:
            org = str(args[0]) if args else None
            return [r for r in self.kbs.values() if not org or r["organization_id"] == org]
        if "documents" in sql:
            kb_id = str(args[0]) if args else None
            return [r for r in self.docs.values() if not kb_id or r["knowledge_base_id"] == kb_id]
        return []

    async def execute(self, sql, *args):
        now = datetime.datetime.utcnow()
        if "INSERT INTO knowledge_bases" in sql:
            self.kbs[str(args[0])] = {
                "id": str(args[0]), "name": str(args[1]), "description": str(args[2]),
                "organization_id": str(args[3]), "is_active": True, "created_at": now,
            }
        elif "INSERT INTO documents" in sql:
            self.docs[str(args[0])] = {
                "id": str(args[0]), "knowledge_base_id": str(args[1]),
                "title": str(args[2]), "content_type": str(args[3]),
                "status": "active", "chunk_count": 0, "is_active": True,
                "retired_at": None, "created_at": now,
            }
        elif "UPDATE documents" in sql:
            doc_id = str(args[-1])
            if doc_id in self.docs:
                self.docs[doc_id]["is_active"] = False
                self.docs[doc_id]["retired_at"] = now
                self.docs[doc_id]["status"] = "retired"

    async def fetchval(self, sql, *args):
        return None


@pytest.mark.asyncio
async def test_create_and_list_kb():
    pool = _InMemoryPool()
    svc = ContentManagementService(pool=pool)
    # create_kb returns a KnowledgeBase dataclass
    created = await svc.create_kb("Test KB", "org1", "desc")
    assert created.name == "Test KB"
    assert created.organization_id == "org1"


@pytest.mark.asyncio
async def test_cms_api():
    pool = _InMemoryPool()
    app.state.cms = ContentManagementService(pool=pool)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/knowledge-bases",
            json={"name": "Test KB", "organization_id": "org1"},
        )
    assert resp.status_code in (200, 201)
    assert "id" in resp.json()
