"""Auth configuration."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_", env_file=".env", extra="ignore")

    issuer: str = "http://localhost:8080/realms/ai-tutor"
    audience: str = "ai-tutor-api"
    jwks_url: str = "http://localhost:8080/realms/ai-tutor/protocol/openid-connect/certs"
    algorithms: list[str] = ["RS256"]
    roles_claim: str = "realm_access.roles"


settings = AuthSettings()
