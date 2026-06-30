"""FastAPI middleware for JWT authentication."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.jwt_validator import JWTValidationError, JWTValidator, TokenPayload


class AuthMiddleware(BaseHTTPMiddleware):
    """Validates Bearer JWT on every request except excluded paths."""

    def __init__(
        self,
        app,
        validator: JWTValidator | None = None,
        exclude_paths: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.validator = validator or JWTValidator()
        self.exclude_paths = exclude_paths or ["/health", "/ready", "/metrics", "/docs", "/openapi.json"]

    async def dispatch(self, request: Request, call_next) -> Response:
        if any(request.url.path.startswith(p) for p in self.exclude_paths):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header:
            return JSONResponse(status_code=401, content={"detail": "Missing Authorization header"})

        try:
            user: TokenPayload = self.validator.decode(auth_header)
            request.state.user = user
        except JWTValidationError as exc:
            return JSONResponse(status_code=401, content={"detail": str(exc)})

        return await call_next(request)
