"""Unit tests for chat session ownership enforcement and user-scoping (WO-179)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.chat import router


@dataclass
class FakeUser:
    sub: str
    roles: list[str] = field(default_factory=list)


def _make_app(svc_mock) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.chat_service = svc_mock
        yield

    app = FastAPI(lifespan=lifespan)
    app.include_router(router)
    return app


def _inject_user(app: FastAPI, sub: str, roles: list[str] | None = None) -> None:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response

    _roles = roles or ["Learner"]

    class InjectUser(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next) -> Response:
            request.state.user = FakeUser(sub=sub, roles=_roles)
            return await call_next(request)

    app.add_middleware(InjectUser)


def _fake_session(user_id: str = "user-1", session_id: str = "sess-1") -> MagicMock:
    s = MagicMock()
    s.id = session_id
    s.user_id = user_id
    s.title = "Test Session"
    s.knowledge_base_id = None
    return s


# ── list_sessions: user-scoping ────────────────────────────────────────────────

def test_list_sessions_scoped_to_caller():
    svc = AsyncMock()
    svc.list_sessions.return_value = [{"id": "sess-1", "title": "s1"}]
    app = _make_app(svc)
    _inject_user(app, sub="user-1")

    with TestClient(app) as client:
        resp = client.get("/api/v1/chat/sessions?user_id=other-user")

    assert resp.status_code == 200
    # Should be called with the authenticated user's sub, not 'other-user'
    svc.list_sessions.assert_called_once_with("user-1")


def test_admin_can_list_any_users_sessions():
    svc = AsyncMock()
    svc.list_sessions.return_value = []
    app = _make_app(svc)
    _inject_user(app, sub="admin-sub", roles=["Admin"])

    with TestClient(app) as client:
        resp = client.get("/api/v1/chat/sessions?user_id=other-user")

    assert resp.status_code == 200
    svc.list_sessions.assert_called_once_with("other-user")


# ── history: ownership enforcement ────────────────────────────────────────────

def test_owner_can_access_history():
    svc = AsyncMock()
    svc.get_session.return_value = _fake_session(user_id="user-1")
    svc.get_history.return_value = []
    app = _make_app(svc)
    _inject_user(app, sub="user-1")

    with TestClient(app) as client:
        resp = client.get("/api/v1/chat/sessions/sess-1/history")

    assert resp.status_code == 200


def test_non_owner_cannot_access_history():
    svc = AsyncMock()
    svc.get_session.return_value = _fake_session(user_id="user-1")
    app = _make_app(svc)
    _inject_user(app, sub="different-user")

    with TestClient(app) as client:
        resp = client.get("/api/v1/chat/sessions/sess-1/history")

    assert resp.status_code == 403


def test_admin_can_access_any_history():
    svc = AsyncMock()
    svc.get_session.return_value = _fake_session(user_id="user-1")
    svc.get_history.return_value = []
    app = _make_app(svc)
    _inject_user(app, sub="admin-sub", roles=["Admin"])

    with TestClient(app) as client:
        resp = client.get("/api/v1/chat/sessions/sess-1/history")

    assert resp.status_code == 200


# ── rename: ownership enforcement ────────────────────────────────────────────

def test_owner_can_rename_session():
    svc = AsyncMock()
    svc.get_session.return_value = _fake_session(user_id="user-1")
    svc.rename_session.return_value = True
    app = _make_app(svc)
    _inject_user(app, sub="user-1")

    with TestClient(app) as client:
        resp = client.patch("/api/v1/chat/sessions/sess-1", json={"title": "New Name"})

    assert resp.status_code == 200


def test_non_owner_cannot_rename_session():
    svc = AsyncMock()
    svc.get_session.return_value = _fake_session(user_id="user-1")
    app = _make_app(svc)
    _inject_user(app, sub="hacker")

    with TestClient(app) as client:
        resp = client.patch("/api/v1/chat/sessions/sess-1", json={"title": "Hijacked"})

    assert resp.status_code == 403
