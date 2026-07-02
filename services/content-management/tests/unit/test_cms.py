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
        # UPDATE ... RETURNING patterns
        if "UPDATE knowledge_bases" in sql and "RETURNING" in sql:
            kb_id = str(args[0])
            if kb_id not in self.kbs:
                return None
            row = self.kbs[kb_id]
            if "is_active = false" in sql:
                row["is_active"] = False
            elif "is_active = true" in sql:
                row["is_active"] = True
            elif "name" in sql and len(args) >= 2:
                if args[1] is not None:
                    row["name"] = str(args[1])
                if len(args) >= 3 and args[2] is not None:
                    row["description"] = str(args[2])
            return row
        if "UPDATE documents" in sql and "RETURNING" in sql:
            doc_id = str(args[0])
            if doc_id not in self.docs:
                return None
            row = self.docs[doc_id]
            row["is_active"] = False
            row["retired_at"] = datetime.datetime.utcnow()
            row["status"] = "retired"
            return row
        if "knowledge_bases" in sql and "WHERE id" in sql:
            return self.kbs.get(str(args[0]))
        if "documents" in sql and "WHERE id" in sql:
            return self.docs.get(str(args[0]))
        return None

    async def fetch(self, sql, *args):
        if "knowledge_bases" in sql:
            org = str(args[0]) if args else None
            rows = [r for r in self.kbs.values() if not org or r["organization_id"] == org]
            # include_archived behaviour: if sql has no "is_active = true" filter, include all
            if "is_active = true" in sql:
                rows = [r for r in rows if r.get("is_active", True)]
            return rows
        if "documents" in sql:
            kb_id = str(args[0]) if args else None
            rows = [r for r in self.docs.values() if not kb_id or r["knowledge_base_id"] == kb_id]
            if "status != 'retired'" in sql:
                rows = [r for r in rows if r.get("status") != "retired"]
            return rows
        return []

    def transaction(self):
        """Return self so `async with pool.transaction()` works in tests."""
        return self

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
        elif "DELETE FROM knowledge_bases WHERE id" in sql:
            kb_id = str(args[0])
            existed = kb_id in self.kbs
            self.kbs.pop(kb_id, None)
            # Also delete associated documents (cascade)
            self.docs = {k: v for k, v in self.docs.items() if v.get("knowledge_base_id") != kb_id}
            return "DELETE 1" if existed else "DELETE 0"
        elif "DELETE FROM" in sql or "UPDATE local_topic_progress" in sql:
            # no-op for other cascade cleanup tables in the mock
            return "DELETE 0"

    async def fetchval(self, sql, *args):
        return None


# ── Service-level tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_list_kb():
    pool = _InMemoryPool()
    svc = ContentManagementService(pool=pool)
    created = await svc.create_kb("Test KB", "org1", "desc")
    assert created.name == "Test KB"
    assert created.organization_id == "org1"


@pytest.mark.asyncio
async def test_list_kbs_active_only_by_default():
    pool = _InMemoryPool()
    svc = ContentManagementService(pool=pool)
    await svc.create_kb("Active KB", "org1", "")
    # Manually add an archived KB to the pool
    archived_id = str(uuid.uuid4())
    pool.kbs[archived_id] = {"id": archived_id, "name": "Archived KB", "description": "",
                              "organization_id": "org1", "is_active": False, "created_at": datetime.datetime.utcnow()}
    active = await svc.list_kbs("org1", include_archived=False)
    assert all(kb.is_active for kb in active)


@pytest.mark.asyncio
async def test_list_kbs_include_archived():
    pool = _InMemoryPool()
    svc = ContentManagementService(pool=pool)
    await svc.create_kb("Active KB", "org1", "")
    archived_id = str(uuid.uuid4())
    pool.kbs[archived_id] = {"id": archived_id, "name": "Archived KB", "description": "",
                              "organization_id": "org1", "is_active": False, "created_at": datetime.datetime.utcnow()}
    all_kbs = await svc.list_kbs("org1", include_archived=True)
    assert len(all_kbs) == 2


@pytest.mark.asyncio
async def test_update_kb():
    pool = _InMemoryPool()
    svc = ContentManagementService(pool=pool)
    kb = await svc.create_kb("Old Name", "org1", "Old desc")
    updated = await svc.update_kb(kb.id, name="New Name", description="New desc")
    assert updated is not None
    assert updated.name == "New Name"
    assert updated.description == "New desc"


@pytest.mark.asyncio
async def test_update_kb_not_found():
    pool = _InMemoryPool()
    svc = ContentManagementService(pool=pool)
    result = await svc.update_kb("nonexistent-id")
    assert result is None


@pytest.mark.asyncio
async def test_archive_and_unarchive_kb():
    pool = _InMemoryPool()
    svc = ContentManagementService(pool=pool)
    kb = await svc.create_kb("My Course", "org1", "")
    archived = await svc.archive_kb(kb.id)
    assert archived is not None
    assert archived.is_active is False
    restored = await svc.unarchive_kb(kb.id)
    assert restored is not None
    assert restored.is_active is True


@pytest.mark.asyncio
async def test_retire_document():
    pool = _InMemoryPool()
    svc = ContentManagementService(pool=pool)
    kb = await svc.create_kb("KB", "org1", "")
    doc = await svc.create_document(kb.id, "Doc 1", "text")
    retired = await svc.retire_document(doc.id)
    assert retired is not None
    assert retired.is_active is False


@pytest.mark.asyncio
async def test_retire_document_not_found():
    pool = _InMemoryPool()
    svc = ContentManagementService(pool=pool)
    result = await svc.retire_document("nonexistent")
    assert result is None


# ── API-level tests ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cms_api_create_kb():
    pool = _InMemoryPool()
    app.state.cms = ContentManagementService(pool=pool)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/knowledge-bases",
            json={"name": "Test KB", "organization_id": "org1"},
        )
    assert resp.status_code in (200, 201)
    assert "id" in resp.json()


@pytest.mark.asyncio
async def test_cms_api_update_kb():
    pool = _InMemoryPool()
    app.state.cms = ContentManagementService(pool=pool)
    kb = await ContentManagementService(pool=pool).create_kb("Old", "org1", "")
    # Re-set the pool state on app
    app.state.cms._pool = pool

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(
            f"/api/v1/knowledge-bases/{kb.id}",
            json={"name": "New Name"},
        )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


@pytest.mark.asyncio
async def test_cms_api_archive_and_unarchive():
    pool = _InMemoryPool()
    svc = ContentManagementService(pool=pool)
    kb = await svc.create_kb("Course", "org1", "")
    app.state.cms = svc

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.post(f"/api/v1/knowledge-bases/{kb.id}/archive")
        assert r1.status_code == 200
        assert r1.json()["is_active"] is False

        r2 = await client.post(f"/api/v1/knowledge-bases/{kb.id}/unarchive")
        assert r2.status_code == 200
        assert r2.json()["is_active"] is True


@pytest.mark.asyncio
async def test_cms_api_delete_kb():
    pool = _InMemoryPool()
    svc = ContentManagementService(pool=pool)
    kb = await svc.create_kb("To Delete", "org1", "")
    app.state.cms = svc

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete(f"/api/v1/knowledge-bases/{kb.id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_cms_api_list_kbs_include_archived():
    pool = _InMemoryPool()
    svc = ContentManagementService(pool=pool)
    await svc.create_kb("Active", "org1", "")
    archived_id = str(uuid.uuid4())
    pool.kbs[archived_id] = {"id": archived_id, "name": "Archived", "description": "",
                              "organization_id": "org1", "is_active": False,
                              "created_at": datetime.datetime.utcnow()}
    app.state.cms = svc

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Without flag — only active
        r1 = await client.get("/api/v1/knowledge-bases?organization_id=org1")
        assert r1.status_code == 200
        assert all(k["is_active"] for k in r1.json()["items"])

        # With flag — include archived
        r2 = await client.get("/api/v1/knowledge-bases?organization_id=org1&include_archived=true")
        assert r2.status_code == 200
        assert len(r2.json()["items"]) == 2


@pytest.mark.asyncio
async def test_cms_api_retire_document():
    pool = _InMemoryPool()
    svc = ContentManagementService(pool=pool)
    kb = await svc.create_kb("KB", "org1", "")
    doc = await svc.create_document(kb.id, "Doc", "text")
    app.state.cms = svc

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(f"/api/v1/documents/{doc.id}/retire")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


# ── 404 / error-path coverage ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cms_api_get_kb_not_found():
    pool = _InMemoryPool()
    app.state.cms = ContentManagementService(pool=pool)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/knowledge-bases/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cms_api_update_kb_not_found():
    pool = _InMemoryPool()
    app.state.cms = ContentManagementService(pool=pool)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(
            "/api/v1/knowledge-bases/nonexistent-id",
            json={"name": "Ghost"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cms_api_archive_kb_not_found():
    pool = _InMemoryPool()
    app.state.cms = ContentManagementService(pool=pool)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/knowledge-bases/nonexistent-id/archive")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cms_api_unarchive_kb_not_found():
    pool = _InMemoryPool()
    app.state.cms = ContentManagementService(pool=pool)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/knowledge-bases/nonexistent-id/unarchive")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cms_api_delete_kb_not_found():
    pool = _InMemoryPool()
    app.state.cms = ContentManagementService(pool=pool)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete("/api/v1/knowledge-bases/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cms_api_list_documents_kb_not_found():
    pool = _InMemoryPool()
    app.state.cms = ContentManagementService(pool=pool)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/knowledge-bases/nonexistent-id/documents")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cms_api_create_doc_kb_not_found():
    pool = _InMemoryPool()
    app.state.cms = ContentManagementService(pool=pool)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/knowledge-bases/nonexistent-id/documents",
            json={"title": "Doc"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cms_api_retire_document_not_found():
    pool = _InMemoryPool()
    app.state.cms = ContentManagementService(pool=pool)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/documents/nonexistent-id/retire")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cms_api_list_documents_with_docs():
    """Cover list_documents happy path including status field."""
    pool = _InMemoryPool()
    svc = ContentManagementService(pool=pool)
    kb = await svc.create_kb("KB", "org1", "")
    await svc.create_document(kb.id, "Doc 1", "text")
    app.state.cms = svc

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/knowledge-bases/{kb.id}/documents")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert "status" in items[0]


@pytest.mark.asyncio
async def test_cms_api_create_doc_happy_path():
    """Cover create_doc success path."""
    pool = _InMemoryPool()
    svc = ContentManagementService(pool=pool)
    kb = await svc.create_kb("KB", "org1", "")
    app.state.cms = svc

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/knowledge-bases/{kb.id}/documents",
            json={"title": "New Doc", "content_type": "pdf"},
        )
    assert resp.status_code == 201
    assert resp.json()["title"] == "New Doc"


# ── hard_delete_kb tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hard_delete_kb_removes_row():
    """hard_delete_kb returns True and removes the KB from the store."""
    pool = _InMemoryPool()
    svc = ContentManagementService(pool=pool)
    kb = await svc.create_kb("To Delete", "org1")
    assert kb.id in pool.kbs

    deleted = await svc.hard_delete_kb(kb.id)
    assert deleted is True
    assert kb.id not in pool.kbs


@pytest.mark.asyncio
async def test_hard_delete_kb_cascades_documents():
    """hard_delete_kb also removes associated documents."""
    pool = _InMemoryPool()
    svc = ContentManagementService(pool=pool)
    kb = await svc.create_kb("KB With Docs", "org1")
    await svc.create_document(kb.id, "Doc 1", "pdf")
    await svc.create_document(kb.id, "Doc 2", "text")
    assert len([d for d in pool.docs.values() if d["knowledge_base_id"] == kb.id]) == 2

    await svc.hard_delete_kb(kb.id)
    remaining = [d for d in pool.docs.values() if d["knowledge_base_id"] == kb.id]
    assert remaining == []


@pytest.mark.asyncio
async def test_hard_delete_kb_not_found_returns_false():
    """hard_delete_kb returns False when the KB does not exist."""
    pool = _InMemoryPool()
    svc = ContentManagementService(pool=pool)
    result = await svc.hard_delete_kb("nonexistent-id")
    assert result is False


@pytest.mark.asyncio
async def test_cms_api_delete_kb_returns_204():
    """DELETE /api/v1/knowledge-bases/{id} returns 204 and removes the KB."""
    pool = _InMemoryPool()
    svc = ContentManagementService(pool=pool)
    kb = await svc.create_kb("Delete Me", "org1")
    app.state.cms = svc

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete(f"/api/v1/knowledge-bases/{kb.id}")
    assert resp.status_code == 204
    assert kb.id not in pool.kbs


@pytest.mark.asyncio
async def test_cms_api_delete_kb_not_found_returns_404():
    """DELETE /api/v1/knowledge-bases/{id} returns 404 for unknown KB."""
    pool = _InMemoryPool()
    app.state.cms = ContentManagementService(pool=pool)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete("/api/v1/knowledge-bases/does-not-exist")
    assert resp.status_code == 404
