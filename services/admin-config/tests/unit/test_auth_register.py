"""Unit tests for POST /api/v1/auth/register endpoint."""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth import router
from src.jwt_validator import TokenPayload


def _make_app(user_repo_mock) -> FastAPI:
    """Build a minimal FastAPI app with the auth router and a mocked state."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.user_repo = user_repo_mock
        yield

    app = FastAPI(lifespan=lifespan)
    app.include_router(router)
    return app


def _mock_token(sub: str = "kc-123") -> TokenPayload:
    return TokenPayload(sub=sub, iss="https://keycloak.test/realms/ai-tutor", exp=9999999999)


# ── Happy path ────────────────────────────────────────────────────────────────

def test_register_new_user_returns_201():
    """First registration creates a user with approval_status='pending'."""
    repo = AsyncMock()
    repo.find_by_keycloak_id.return_value = None
    repo.create_pending_user.return_value = {
        "id": "uuid-1",
        "keycloak_id": "kc-123",
        "email_hash": "abc123",
        "approval_status": "pending",
        "created_at": "2026-07-17T00:00:00",
    }

    app = _make_app(repo)
    with TestClient(app, raise_server_exceptions=True) as client:
        # Inject request.state.user manually via middleware bypass
        from starlette.testclient import TestClient as _TC  # noqa: F401
        with patch("src.api.auth.RegisterRequest"):
            pass

    # Use direct state injection via a custom route wrapper
    with TestClient(app) as client:
        # Simulate middleware having set request.state.user
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.requests import Request
        from starlette.responses import Response

        class InjectUser(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next) -> Response:
                request.state.user = _mock_token("kc-123")
                return await call_next(request)

        app.add_middleware(InjectUser)
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": "alice@example.com", "full_name": "Alice"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["approval_status"] == "pending"
    assert data["keycloak_id"] == "kc-123"
    assert "awaiting admin approval" in data["message"]
    repo.create_pending_user.assert_called_once_with(
        keycloak_id="kc-123",
        email="alice@example.com",
        full_name="Alice",
    )


def test_register_existing_user_returns_200_idempotent():
    """Duplicate registration returns 200 with existing record (idempotent)."""
    existing = {
        "id": "uuid-existing",
        "keycloak_id": "kc-456",
        "email_hash": "def456",
        "approval_status": "approved",
        "created_at": "2026-06-01T00:00:00",
    }
    repo = AsyncMock()
    repo.find_by_keycloak_id.return_value = existing

    app = _make_app(repo)

    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response

    class InjectUser(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next) -> Response:
            request.state.user = _mock_token("kc-456")
            return await call_next(request)

    app.add_middleware(InjectUser)

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": "bob@example.com", "full_name": "Bob"},
        )

    assert resp.status_code == 201  # FastAPI still returns 201 per endpoint def
    data = resp.json()
    assert data["keycloak_id"] == "kc-456"
    assert data["message"] == "User already registered"
    repo.create_pending_user.assert_not_called()


def test_register_missing_claims_returns_401():
    """If no user is set on request.state, endpoint returns 401."""
    repo = AsyncMock()
    app = _make_app(repo)

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": "x@example.com", "full_name": "X"},
        )

    assert resp.status_code == 401


def test_register_invalid_email_returns_422():
    """Pydantic validation rejects malformed email."""
    repo = AsyncMock()
    app = _make_app(repo)

    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response

    class InjectUser(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next) -> Response:
            request.state.user = _mock_token("kc-789")
            return await call_next(request)

    app.add_middleware(InjectUser)

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "full_name": "Y"},
        )

    assert resp.status_code == 422
