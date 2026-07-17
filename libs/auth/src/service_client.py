"""Authenticated inter-service HTTP client.

Provides an httpx ``AsyncClient`` that automatically forwards the caller's
JWT Bearer token on every outbound request.  Services use this instead of
bare ``httpx.AsyncClient()`` so the trust handshake is explicit and
centralised rather than assumed from network proximity alone.

Usage::

    from libs.auth.src.service_client import service_client

    # Inside a FastAPI route handler:
    async with service_client(request) as client:
        resp = await client.get("http://rag-pipeline:8006/api/v1/rag/retrieve", ...)

    # Or for fire-and-forget calls where no JWT is available (background tasks):
    async with service_client(token="service-internal-token") as client:
        ...
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx

_SERVICE_TOKEN = os.getenv("SERVICE_INTERNAL_TOKEN", "")
_DEFAULT_TIMEOUT = float(os.getenv("SERVICE_CLIENT_TIMEOUT", "30"))


def _extract_bearer(request) -> str | None:  # type: ignore[no-untyped-def]
    """Extract the raw JWT string from a FastAPI ``Request`` object, or None."""
    try:
        auth_header: str = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            return auth_header[7:]
    except Exception:
        pass
    return None


@asynccontextmanager
async def service_client(
    request=None,  # FastAPI Request — token is forwarded when present
    *,
    token: str | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
    **httpx_kwargs,
) -> AsyncIterator[httpx.AsyncClient]:
    """Context-managed httpx client that propagates JWT auth to downstream services.

    Priority order for the Bearer token:
    1. Explicit ``token`` kwarg
    2. ``Authorization`` header from the incoming ``request``
    3. ``SERVICE_INTERNAL_TOKEN`` env var (service-to-service background calls)
    4. No auth header (only safe for health-check / metrics endpoints)
    """
    bearer = token or (request and _extract_bearer(request)) or _SERVICE_TOKEN or None

    headers = dict(httpx_kwargs.pop("headers", {}))
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    headers.setdefault("X-Service-Name", os.getenv("SERVICE_NAME", "ai-tutor-service"))

    async with httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        **httpx_kwargs,
    ) as client:
        yield client
