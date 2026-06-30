"""Unit tests for require_role decorator."""
from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from src.decorators import require_role
from src.jwt_validator import TokenPayload


def _make_app(user: TokenPayload | None) -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def inject_user(request: Request, call_next):
        if user:
            request.state.user = user
        return await call_next(request)

    @app.get("/admin")
    @require_role("Admin")
    async def admin_only(request: Request):
        return {"ok": True}

    @app.get("/learner")
    @require_role("Learner", "Admin")
    async def learner_or_admin(request: Request):
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_require_role_allows_matching_role():
    user = TokenPayload(sub="u1", iss="iss", exp=9999999999, roles=["Admin"])
    app = _make_app(user)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_require_role_returns_403_for_wrong_role():
    user = TokenPayload(sub="u1", iss="iss", exp=9999999999, roles=["Learner"])
    app = _make_app(user)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin")
    assert resp.status_code == 403
    assert "Insufficient permissions" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_require_role_allows_learner_or_admin():
    user = TokenPayload(sub="u1", iss="iss", exp=9999999999, roles=["Learner"])
    app = _make_app(user)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/learner")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_require_role_returns_401_without_user():
    app = _make_app(None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin")
    assert resp.status_code == 401

