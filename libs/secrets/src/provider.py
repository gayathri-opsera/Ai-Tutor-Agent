"""Centralised secret loading with production-safety guards.

All services use this module instead of direct ``os.getenv()`` calls with
hardcoded fallback credentials.  In non-local environments (``APP_ENV`` !=
``local``/``test``/``development``) any unset required secret raises
``EnvironmentError`` immediately at startup rather than silently using a
default that could leak into a production container.

Usage::

    from libs.secrets.src.provider import get_db_dsn, get_s3_access_key

    dsn = get_db_dsn()
"""
from __future__ import annotations

import os

_ENV: str = os.getenv("APP_ENV", "local").lower()
_IS_PROD: bool = _ENV not in ("local", "test", "development", "dev")

# Safe local-dev-only defaults — never used when APP_ENV is production.
_LOCAL_DB_DSN = "postgresql://ai_tutor:ai_tutor_local_password@postgres:5432/ai_tutor"
_LOCAL_S3_KEY = "minioadmin"
_LOCAL_JWT = "local-dev-jwt-secret-change-in-prod"


def _require(key: str, *, local_fallback: str | None = None) -> str:
    """Return the environment-variable value for *key*.

    Raises ``EnvironmentError`` in production when the variable is not set.
    In local/test environments returns *local_fallback* when provided.
    """
    value = os.getenv(key)
    if value:
        return value
    if not _IS_PROD and local_fallback is not None:
        return local_fallback
    raise EnvironmentError(
        f"Required secret '{key}' is not set. "
        "Provide it via an environment variable, SealedSecret, or secret manager "
        f"(APP_ENV={_ENV!r})."
    )


def get_db_dsn() -> str:
    """Return the full PostgreSQL connection DSN."""
    return _require("DATABASE_URL", local_fallback=_LOCAL_DB_DSN)


def get_s3_access_key() -> str:
    """Return the S3/MinIO access key."""
    return _require("S3_ACCESS_KEY", local_fallback=_LOCAL_S3_KEY)


def get_s3_secret_key() -> str:
    """Return the S3/MinIO secret key."""
    return _require("S3_SECRET_KEY", local_fallback=_LOCAL_S3_KEY)


def get_weaviate_url() -> str:
    """Return the Weaviate endpoint URL."""
    return os.getenv("WEAVIATE_URL", "http://weaviate:8080")


def get_weaviate_api_key() -> str | None:
    """Return the Weaviate API key, or None for unauthenticated local access."""
    return os.getenv("WEAVIATE_API_KEY")


def get_jwt_secret() -> str:
    """Return the JWT signing secret."""
    return _require("JWT_SECRET", local_fallback=_LOCAL_JWT)


def get_keycloak_secret() -> str:
    """Return the Keycloak client secret."""
    return _require("KEYCLOAK_CLIENT_SECRET", local_fallback="")


def get_redis_url() -> str:
    """Return the Redis connection URL."""
    return os.getenv("REDIS_URL", "redis://redis:6379")


def get_app_env() -> str:
    """Return the current deployment environment name."""
    return _ENV


def is_production() -> bool:
    """Return True when running in a production environment."""
    return _IS_PROD
