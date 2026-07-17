"""Unit tests for KB ownership enforcement in content.py (WO-178)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.content import router


@dataclass
class FakeUser:
    sub: str
    roles: list[str] = field(default_factory=list)


def _make_app(svc_mock) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.cms = svc_mock
        yield

    app = FastAPI(lifespan=lifespan)
    app.include_router(router)
    return app


def _inject_user(app: FastAPI, sub: str, roles: list[str]) -> None:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response

    class InjectUser(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next) -> Response:
            request.state.user = FakeUser(sub=sub, roles=roles)
            return await call_next(request)

    app.add_middleware(InjectUser)


def _mock_svc(owner_keycloak_id: str | None) -> AsyncMock:
    svc = AsyncMock()
    kb = MagicMock()
    kb.id = "kb-1"
    kb.name = "Test Course"
    kb.description = "Desc"
    kb.organization_id = "default"
    kb.is_active = True
    kb.age_group = "adults"
    kb.created_by_keycloak_id = owner_keycloak_id
    svc.get_kb.return_value = kb
    svc.get_kb_raw.return_value = {"id": "kb-1", "created_by_keycloak_id": owner_keycloak_id}
    svc.update_kb.return_value = kb
    svc.hard_delete_kb.return_value = True
    return svc


# ── Ownership: owner can update ───────────────────────────────────────────────

def test_owner_can_update_their_kb():
    svc = _mock_svc(owner_keycloak_id="creator-sub-1")
    app = _make_app(svc)
    _inject_user(app, sub="creator-sub-1", roles=["Creator"])

    with TestClient(app) as client:
        resp = client.put("/api/v1/knowledge-bases/kb-1",
                         json={"name": "Updated Name"})

    assert resp.status_code == 200


def test_non_owner_cannot_update_kb():
    svc = _mock_svc(owner_keycloak_id="creator-sub-1")
    app = _make_app(svc)
    _inject_user(app, sub="different-creator", roles=["Creator"])

    with TestClient(app) as client:
        resp = client.put("/api/v1/knowledge-bases/kb-1",
                         json={"name": "Hijacked Name"})

    assert resp.status_code == 403


def test_admin_can_update_any_kb():
    svc = _mock_svc(owner_keycloak_id="creator-sub-1")
    app = _make_app(svc)
    _inject_user(app, sub="admin-sub", roles=["Admin"])

    with TestClient(app) as client:
        resp = client.put("/api/v1/knowledge-bases/kb-1",
                         json={"name": "Admin Override"})

    assert resp.status_code == 200


# ── Ownership: owner can delete ────────────────────────────────────────────────

def test_owner_can_delete_their_kb():
    svc = _mock_svc(owner_keycloak_id="creator-sub-1")
    app = _make_app(svc)
    _inject_user(app, sub="creator-sub-1", roles=["Creator"])

    with TestClient(app) as client:
        resp = client.delete("/api/v1/knowledge-bases/kb-1")

    assert resp.status_code == 204


def test_non_owner_cannot_delete_kb():
    svc = _mock_svc(owner_keycloak_id="creator-sub-1")
    app = _make_app(svc)
    _inject_user(app, sub="another-user", roles=["Creator"])

    with TestClient(app) as client:
        resp = client.delete("/api/v1/knowledge-bases/kb-1")

    assert resp.status_code == 403


def test_admin_can_delete_any_kb():
    svc = _mock_svc(owner_keycloak_id="creator-sub-1")
    app = _make_app(svc)
    _inject_user(app, sub="admin-sub", roles=["Admin"])

    with TestClient(app) as client:
        resp = client.delete("/api/v1/knowledge-bases/kb-1")

    assert resp.status_code == 204


# ── Age-group field ───────────────────────────────────────────────────────────

def test_create_kb_persists_age_group():
    svc = AsyncMock()
    kb = MagicMock()
    kb.id = "kb-new"
    kb.name = "Kids Python"
    kb.description = ""
    kb.age_group = "children"
    svc.create_kb.return_value = kb
    app = _make_app(svc)
    _inject_user(app, sub="creator-1", roles=["Creator"])

    with TestClient(app) as client:
        resp = client.post("/api/v1/knowledge-bases",
                          json={"name": "Kids Python", "organization_id": "default",
                                "age_group": "children"})

    assert resp.status_code == 201
    svc.create_kb.assert_called_once_with(
        "Kids Python", "default", "",
        age_group="children",
        created_by_keycloak_id="creator-1",
    )
