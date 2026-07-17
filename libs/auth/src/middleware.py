"""FastAPI middleware for JWT authentication and approval-status enforcement."""
from __future__ import annotations

from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.jwt_validator import JWTValidationError, JWTValidator, TokenPayload


class AuthMiddleware(BaseHTTPMiddleware):
    """Validates Bearer JWT on every request and optionally checks approval_status.

    Constructor parameters
    ----------------------
    validator : JWTValidator | None
        Custom validator (e.g. with a static public key for testing).
        Defaults to a live Keycloak JWKS-backed validator.
    exclude_paths : list[str] | None
        Request path prefixes that bypass ALL authentication (health checks,
        metrics, OpenAPI docs).  Defaults to the standard set.
    approval_checker : Callable[[str], Awaitable[str]] | None
        Optional async callback ``(keycloak_id) -> approval_status``.
        When provided, any user whose status is ``"pending"`` or ``"rejected"``
        receives a 403 before the request reaches the route handler.
        Paths listed in *approval_exclude_paths* are exempt from this check.
    approval_exclude_paths : list[str] | None
        Path prefixes that are exempt from the approval_status check but still
        require a valid JWT.  Defaults to ``["/api/v1/auth/register"]`` so that
        first-time OAuth users can self-register.
    """

    _DEFAULT_EXCLUDE = ["/health", "/ready", "/metrics", "/docs", "/openapi.json"]
    _DEFAULT_APPROVAL_EXCLUDE = ["/api/v1/auth/register"]

    def __init__(
        self,
        app,
        validator: JWTValidator | None = None,
        exclude_paths: list[str] | None = None,
        approval_checker: Callable[[str], Awaitable[str]] | None = None,
        approval_exclude_paths: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.validator = validator or JWTValidator()
        self.exclude_paths = exclude_paths or self._DEFAULT_EXCLUDE
        self.approval_checker = approval_checker
        self.approval_exclude_paths = (
            approval_exclude_paths
            if approval_exclude_paths is not None
            else self._DEFAULT_APPROVAL_EXCLUDE
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        # Paths that bypass all auth (health/metrics/docs)
        if any(request.url.path.startswith(p) for p in self.exclude_paths):
            return await call_next(request)

        # Validate JWT
        auth_header = request.headers.get("Authorization", "")
        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing Authorization header"},
            )

        try:
            user: TokenPayload = self.validator.decode(auth_header)
            request.state.user = user
        except JWTValidationError as exc:
            return JSONResponse(status_code=401, content={"detail": str(exc)})

        # Approval-status gate (skipped for registration endpoint and similar paths)
        if self.approval_checker is not None and not any(
            request.url.path.startswith(p) for p in self.approval_exclude_paths
        ):
            try:
                approval_status: str = await self.approval_checker(user.sub)
            except Exception:
                # Fail secure: treat unknown status as pending
                approval_status = "pending"

            if approval_status == "pending":
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Account pending approval"},
                )
            if approval_status == "rejected":
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Account rejected"},
                )

        return await call_next(request)
