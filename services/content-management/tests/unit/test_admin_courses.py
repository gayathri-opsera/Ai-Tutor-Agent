"""Unit tests for admin course approval API endpoints."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.admin_courses import router


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


def _inject_admin(app: FastAPI, sub: str = "admin-1", roles: list[str] | None = None) -> None:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request as SRequest
    from starlette.responses import Response

    _roles = roles if roles is not None else ["Admin"]

    class InjectUser(BaseHTTPMiddleware):
        async def dispatch(self, request: SRequest, call_next) -> Response:
            request.state.user = FakeUser(sub=sub, roles=_roles)
            return await call_next(request)

    app.add_middleware(InjectUser)


_SAMPLE_KB = {
    "id": "kb-1",
    "name": "Python 101",
    "description": "Learn Python",
    "organization_id": "default",
    "approval_status": "pending_review",
    "ai_overview": None,
    "created_at": "2026-07-17T00:00:00",
}


# ── GET /pending ──────────────────────────────────────────────────────────────

def test_list_pending_courses_admin():
    svc = AsyncMock()
    svc.list_by_approval_status.return_value = ([_SAMPLE_KB], 1)
    app = _make_app(svc)
    _inject_admin(app)

    with TestClient(app) as client:
        resp = client.get("/api/v1/admin/courses/pending")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["courses"][0]["name"] == "Python 101"


def test_list_pending_courses_non_admin_403():
    svc = AsyncMock()
    app = _make_app(svc)
    _inject_admin(app, roles=["Learner"])

    with TestClient(app) as client:
        resp = client.get("/api/v1/admin/courses/pending")

    assert resp.status_code == 403


# ── POST /approve ─────────────────────────────────────────────────────────────

def test_approve_course_success():
    svc = AsyncMock()
    svc.get_kb.return_value = type("KB", (), {"name": "Python 101", "description": ""})()
    svc.update_kb_field.return_value = None

    app = _make_app(svc)
    _inject_admin(app)

    with patch("src.api.admin_courses._emit_kafka_event", new=AsyncMock()):
        with TestClient(app) as client:
            resp = client.post("/api/v1/admin/courses/kb-1/approve")

    assert resp.status_code == 200
    assert resp.json()["approval_status"] == "approved"
    svc.update_kb_field.assert_any_call("kb-1", "approval_status", "approved")


def test_approve_nonexistent_course_404():
    svc = AsyncMock()
    svc.get_kb.return_value = None

    app = _make_app(svc)
    _inject_admin(app)

    with TestClient(app) as client:
        resp = client.post("/api/v1/admin/courses/missing/approve")

    assert resp.status_code == 404


# ── POST /reject ──────────────────────────────────────────────────────────────

def test_reject_course_with_reason():
    svc = AsyncMock()
    svc.get_kb.return_value = type("KB", (), {"name": "Bad Course", "description": ""})()
    svc.update_kb_field.return_value = None

    app = _make_app(svc)
    _inject_admin(app)

    with patch("src.api.admin_courses._emit_kafka_event", new=AsyncMock()):
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/admin/courses/kb-2/reject",
                json={"reason": "Content policy violation"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["approval_status"] == "rejected"
    svc.update_kb_field.assert_any_call("kb-2", "rejection_reason", "Content policy violation")


# ── POST /request-clarification ───────────────────────────────────────────────

def test_request_clarification():
    svc = AsyncMock()
    svc.get_kb.return_value = type("KB", (), {"name": "Unclear Course", "description": ""})()
    svc.update_kb_field.return_value = None

    app = _make_app(svc)
    _inject_admin(app)

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/admin/courses/kb-3/request-clarification",
            json={"message": "Please provide learning objectives"},
        )

    assert resp.status_code == 200
    assert resp.json()["approval_status"] == "clarification_requested"
    svc.update_kb_field.assert_any_call(
        "kb-3", "clarification_message", "Please provide learning objectives"
    )
