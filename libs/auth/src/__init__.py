"""Shared authentication library for AI Tutor services."""
from src.config import AuthSettings
from src.decorators import require_role
from src.jwt_validator import JWTValidator, TokenPayload
from src.middleware import AuthMiddleware
from src.service_middleware import ServiceAuthMiddleware, ServiceIdentity

__all__ = [
    "AuthSettings",
    "AuthMiddleware",
    "ServiceAuthMiddleware",
    "ServiceIdentity",
    "JWTValidator",
    "TokenPayload",
    "require_role",
]
