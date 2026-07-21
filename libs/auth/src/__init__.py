"""Shared authentication library for AI Tutor services."""
from config import AuthSettings
from decorators import require_role
from jwt_validator import JWTValidator, TokenPayload
from middleware import AuthMiddleware
from service_middleware import ServiceAuthMiddleware, ServiceIdentity

__all__ = [
    "AuthSettings",
    "AuthMiddleware",
    "ServiceAuthMiddleware",
    "ServiceIdentity",
    "JWTValidator",
    "TokenPayload",
    "require_role",
]
