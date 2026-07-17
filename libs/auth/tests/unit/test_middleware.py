"""Unit tests for AuthMiddleware."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.config import AuthSettings
from src.jwt_validator import JWTValidator
from src.middleware import AuthMiddleware
from tests.conftest import ISSUER, generate_rsa_keypair, make_token


@pytest.fixture
def auth_app():
    private_pem, public_pem = generate_rsa_keypair()
    settings = AuthSettings(issuer=ISSUER, audience="ai-tutor-api")
    validator = JWTValidator(auth_settings=settings, public_key_pem=public_pem)

    app = FastAPI()
    app.add_middleware(AuthMiddleware, validator=validator)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/protected")
    async def protected():
        return {"status": "protected"}

    return app, private_pem


@pytest.fixture
def approval_app():
    """App with approval_checker wired in."""
    private_pem, public_pem = generate_rsa_keypair()
    settings = AuthSettings(issuer=ISSUER, audience="ai-tutor-api")
    validator = JWTValidator(auth_settings=settings, public_key_pem=public_pem)

    # In-memory approval store keyed by keycloak_id (token 'sub')
    approval_store: dict[str, str] = {}

    async def check_approval(keycloak_id: str) -> str:
        return approval_store.get(keycloak_id, "pending")

    app = FastAPI()
    app.add_middleware(
        AuthMiddleware,
        validator=validator,
        approval_checker=check_approval,
    )
    app.state.approval_store = approval_store

    @app.get("/api/v1/auth/register")
    async def register():
        return {"status": "registered"}

    @app.get("/api/v1/data")
    async def data():
        return {"status": "data"}

    return app, private_pem, approval_store


@pytest.mark.asyncio
async def test_middleware_allows_health_without_auth(auth_app):
    app, _ = auth_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_middleware_rejects_missing_token(auth_app):
    app, _ = auth_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/protected")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_middleware_rejects_invalid_token(auth_app):
    app, _ = auth_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/protected", headers={"Authorization": "Bearer invalid.token.here"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_middleware_accepts_valid_token(auth_app):
    app, private_pem = auth_app
    token = make_token(private_pem, roles=["Admin"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


# ── Approval-status gate tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approval_pending_returns_403(approval_app):
    """Users with pending status cannot access protected endpoints."""
    app, private_pem, store = approval_app
    token = make_token(private_pem, sub="user-pending", roles=["Learner"])
    store["user-pending"] = "pending"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/data", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Account pending approval"


@pytest.mark.asyncio
async def test_approval_rejected_returns_403(approval_app):
    """Users with rejected status cannot access protected endpoints."""
    app, private_pem, store = approval_app
    token = make_token(private_pem, sub="user-rejected", roles=["Learner"])
    store["user-rejected"] = "rejected"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/data", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Account rejected"


@pytest.mark.asyncio
async def test_approval_approved_passes(approval_app):
    """Users with approved status can access protected endpoints."""
    app, private_pem, store = approval_app
    token = make_token(private_pem, sub="user-approved", roles=["Learner"])
    store["user-approved"] = "approved"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/data", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_register_endpoint_exempt_from_approval_check(approval_app):
    """The /api/v1/auth/register path bypasses approval gate even for pending users."""
    app, private_pem, store = approval_app
    token = make_token(private_pem, sub="user-new", roles=[])
    store["user-new"] = "pending"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/auth/register",
            headers={"Authorization": f"Bearer {token}"},
        )
    # Endpoint is reachable (not blocked by approval gate)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_approval_checker_exception_fails_secure(approval_app):
    """If approval_checker raises an exception, middleware fails secure (403)."""
    private_pem, public_pem = generate_rsa_keypair()
    settings = AuthSettings(issuer=ISSUER, audience="ai-tutor-api")
    validator = JWTValidator(auth_settings=settings, public_key_pem=public_pem)

    async def buggy_checker(keycloak_id: str) -> str:
        raise RuntimeError("DB connection lost")

    from fastapi import FastAPI as _FastAPI
    broken_app = _FastAPI()
    broken_app.add_middleware(AuthMiddleware, validator=validator, approval_checker=buggy_checker)

    @broken_app.get("/api/v1/data")
    async def data():
        return {"ok": True}

    token = make_token(private_pem, sub="any-user", roles=[])
    async with AsyncClient(transport=ASGITransport(app=broken_app), base_url="http://test") as client:
        resp = await client.get("/api/v1/data", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Account pending approval"
