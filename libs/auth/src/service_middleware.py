"""Service-to-service authentication middleware.

Extends ``AuthMiddleware`` to support both user JWT tokens and internal
service-account tokens (``X-Service-Token`` header).  This creates an
explicit, machine-verifiable inter-service trust contract so downstream
services never rely on implicit network trust alone.

Calling convention
------------------
User-facing requests:
    ``Authorization: Bearer <user-jwt>``

Internal service-to-service requests:
    ``X-Service-Token: <service-account-token>``
    ``X-Service-Name: <calling-service-name>``

The middleware also enforces a maximum request body size and validates
``Content-Type`` on mutation requests, closing the input validation
perimeter at every ingress point.

Usage::

    from libs.auth.src.service_middleware import ServiceAuthMiddleware

    app.add_middleware(
        ServiceAuthMiddleware,
        exclude_paths=["/health", "/docs"],
        max_body_bytes=10 * 1024 * 1024,   # 10 MB
    )
"""
from __future__ import annotations

import os
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.jwt_validator import JWTValidationError, JWTValidator, TokenPayload

_SERVICE_TOKEN = os.getenv("SERVICE_INTERNAL_TOKEN", "")
_DEFAULT_MAX_BODY = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(10 * 1024 * 1024)))  # 10 MB
_MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class ServiceIdentity:
    """Attached to ``request.state.service`` for authenticated service calls."""

    __slots__ = ("name", "token_type")

    def __init__(self, name: str, token_type: str = "service") -> None:
        self.name = name
        self.token_type = token_type

    def __repr__(self) -> str:
        return f"ServiceIdentity(name={self.name!r})"


class ServiceAuthMiddleware(BaseHTTPMiddleware):
    """Validates caller identity on every ingress and enforces input constraints.

    Accepts:
    - User JWTs via ``Authorization: Bearer <token>``
    - Service-account tokens via ``X-Service-Token: <token>`` +
      ``X-Service-Name: <name>``

    Enforces:
    - Request body size ≤ ``max_body_bytes``
    - ``Content-Type: application/json`` required on POST/PUT/PATCH
    """

    _DEFAULT_EXCLUDE = ["/health", "/ready", "/metrics", "/docs", "/openapi.json"]

    def __init__(
        self,
        app,
        validator: JWTValidator | None = None,
        exclude_paths: list[str] | None = None,
        max_body_bytes: int = _DEFAULT_MAX_BODY,
        require_content_type: bool = True,
    ) -> None:
        super().__init__(app)
        self.validator = validator or JWTValidator()
        self.exclude_paths = exclude_paths or self._DEFAULT_EXCLUDE
        self.max_body_bytes = max_body_bytes
        self.require_content_type = require_content_type

    async def dispatch(self, request: Request, call_next: Callable[..., Awaitable[Response]]) -> Response:
        # Exempt health/docs endpoints from all checks.
        if any(request.url.path.startswith(p) for p in self.exclude_paths):
            return await call_next(request)

        # ── Input validation: Content-Type ──────────────────────────────────
        if self.require_content_type and request.method in _MUTATION_METHODS:
            ct = request.headers.get("content-type", "")
            if ct and not ct.startswith("application/json") and not ct.startswith("multipart/"):
                return JSONResponse(
                    status_code=415,
                    content={"detail": f"Unsupported Media Type: {ct!r}. Use application/json."},
                )

        # ── Input validation: Body size ─────────────────────────────────────
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_body_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": f"Request body exceeds {self.max_body_bytes} bytes limit."},
            )

        # ── Auth: service-to-service token ──────────────────────────────────
        service_token = request.headers.get("x-service-token", "")
        if service_token:
            if _SERVICE_TOKEN and service_token != _SERVICE_TOKEN:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid service token."},
                )
            service_name = request.headers.get("x-service-name", "unknown-service")
            request.state.service = ServiceIdentity(name=service_name)
            request.state.user = None  # service calls have no user context
            return await call_next(request)

        # ── Auth: user JWT ───────────────────────────────────────────────────
        auth_header = request.headers.get("Authorization", "")
        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing Authorization header (Bearer token or X-Service-Token required)."},
            )

        try:
            user: TokenPayload = self.validator.decode(auth_header)
            request.state.user = user
            request.state.service = None
        except JWTValidationError as exc:
            return JSONResponse(status_code=401, content={"detail": str(exc)})

        return await call_next(request)
