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
