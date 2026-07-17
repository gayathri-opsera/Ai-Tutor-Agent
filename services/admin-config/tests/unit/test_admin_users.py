"""Unit tests for admin user approval API endpoints."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.admin_users import router


@dataclass
class FakeTokenPayload:
    sub: str
    roles: list[str] = field(default_factory=list)


def _make_app(user_repo_mock) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.user_repo = user_repo_mock
        yield

    app = FastAPI(lifespan=lifespan)
    app.include_router(router)
    return app


def _inject_user_middleware(app: FastAPI, sub: str, roles: list[str]) -> None:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response

    class InjectUser(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next) -> Response:
            request.state.user = FakeTokenPayload(sub=sub, roles=roles)
            return await call_next(request)

    app.add_middleware(InjectUser)


# ── GET /pending ──────────────────────────────────────────────────────────────

def test_list_pending_admin_can_see_users():
    repo = AsyncMock()
    repo.list_pending.return_value = (
        [
            {"id": "u1", "keycloak_id": "kc-1", "email_hash": "hash1",
             "approval_status": "pending", "created_at": "2026-07-17T00:00:00"},
        ],
        1,
    )
    app = _make_app(repo)
    _inject_user_middleware(app, sub="admin-1", roles=["Admin"])

    with TestClient(app) as client:
        resp = client.get("/api/v1/admin/users/pending")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["users"]) == 1
    assert data["users"][0]["approval_status"] == "pending"


def test_list_pending_non_admin_gets_403():
    repo = AsyncMock()
    app = _make_app(repo)
    _inject_user_middleware(app, sub="learner-1", roles=["Learner"])

    with TestClient(app) as client:
        resp = client.get("/api/v1/admin/users/pending")

    assert resp.status_code == 403


def test_list_pending_no_auth_returns_401():
    repo = AsyncMock()
    app = _make_app(repo)

    with TestClient(app) as client:
        resp = client.get("/api/v1/admin/users/pending")

    assert resp.status_code == 401


# ── POST /{user_id}/approve ────────────────────────────────────────────────────

def test_approve_user_success():
    repo = AsyncMock()
    repo.find_by_id.return_value = {
        "id": "u1", "keycloak_id": "kc-1", "email_hash": "hash1",
        "approval_status": "pending", "created_at": "2026-07-17T00:00:00",
    }
    repo.update_approval_status.return_value = {
        "id": "u1", "keycloak_id": "kc-1", "email_hash": "hash1",
        "approval_status": "approved", "created_at": "2026-07-17T00:00:00",
    }
    repo.assign_roles.return_value = None

    app = _make_app(repo)
    _inject_user_middleware(app, sub="admin-1", roles=["SuperAdmin"])

    with patch("src.api.admin_users.emit_approval_event", new=AsyncMock()):
        with patch("src.api.admin_users._post_audit_log", new=AsyncMock()):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/admin/users/u1/approve",
                    json={"roles": ["Learner", "Creator"]},
                )

    assert resp.status_code == 200
    data = resp.json()
    assert data["approval_status"] == "approved"
    assert "Learner" in data["roles_assigned"]
    repo.assign_roles.assert_called_once_with("u1", ["Learner", "Creator"])


def test_approve_nonexistent_user_returns_404():
    repo = AsyncMock()
    repo.find_by_id.return_value = None

    app = _make_app(repo)
    _inject_user_middleware(app, sub="admin-1", roles=["Admin"])

    with TestClient(app) as client:
        resp = client.post("/api/v1/admin/users/missing/approve", json={"roles": ["Learner"]})

    assert resp.status_code == 404


def test_approve_requires_admin_role():
    repo = AsyncMock()
    app = _make_app(repo)
    _inject_user_middleware(app, sub="learner-1", roles=["Learner"])

    with TestClient(app) as client:
        resp = client.post("/api/v1/admin/users/u1/approve", json={"roles": ["Learner"]})

    assert resp.status_code == 403


# ── POST /{user_id}/reject ────────────────────────────────────────────────────

def test_reject_user_success():
    repo = AsyncMock()
    repo.find_by_id.return_value = {
        "id": "u1", "keycloak_id": "kc-1", "email_hash": "hash1",
        "approval_status": "pending", "created_at": "2026-07-17T00:00:00",
    }
    repo.update_approval_status.return_value = {
        "id": "u1", "keycloak_id": "kc-1", "email_hash": "hash1",
        "approval_status": "rejected", "created_at": "2026-07-17T00:00:00",
    }

    app = _make_app(repo)
    _inject_user_middleware(app, sub="admin-1", roles=["Admin"])

    with patch("src.api.admin_users.emit_approval_event", new=AsyncMock()):
        with patch("src.api.admin_users._post_audit_log", new=AsyncMock()):
            with TestClient(app) as client:
                resp = client.post("/api/v1/admin/users/u1/reject")

    assert resp.status_code == 200
    data = resp.json()
    assert data["approval_status"] == "rejected"
    assert data["roles_assigned"] == []
    repo.update_approval_status.assert_called_once_with("u1", "rejected")


def test_reject_nonexistent_user_returns_404():
    repo = AsyncMock()
    repo.find_by_id.return_value = None

    app = _make_app(repo)
    _inject_user_middleware(app, sub="admin-1", roles=["Admin"])

    with TestClient(app) as client:
        resp = client.post("/api/v1/admin/users/missing/reject")

    assert resp.status_code == 404
