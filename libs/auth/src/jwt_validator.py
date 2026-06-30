"""JWT validation with RS256, exp/iss checks, and role extraction."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import jwt
from jwt import PyJWKClient

from src.config import AuthSettings, settings


class JWTValidationError(Exception):
    """Raised when a token fails validation."""


@dataclass
class TokenPayload:
    sub: str
    iss: str
    exp: int
    roles: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def has_role(self, role: str) -> bool:
        return role in self.roles


class JWTValidator:
    """Validates JWTs against Keycloak JWKS or a static public key."""

    def __init__(
        self,
        auth_settings: AuthSettings | None = None,
        public_key_pem: str | None = None,
    ) -> None:
        self._settings = auth_settings or settings
        self._public_key_pem = public_key_pem
        self._jwks_client: PyJWKClient | None = None

    def decode(self, token: str) -> TokenPayload:
        """Decode and validate a JWT. Raises JWTValidationError on failure."""
        if not token or not isinstance(token, str):
            raise JWTValidationError("Token is missing or malformed")

        token = token.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()

        try:
            key = self._resolve_key(token)
            payload = jwt.decode(
                token,
                key,
                algorithms=self._settings.algorithms,
                audience=self._settings.audience,
                options={"require": ["exp", "iss", "sub"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise JWTValidationError("Token has expired") from exc
        except jwt.InvalidTokenError as exc:
            raise JWTValidationError(f"Invalid token: {exc}") from exc

        if payload.get("iss") != self._settings.issuer:
            raise JWTValidationError(
                f"Invalid issuer: expected {self._settings.issuer}, got {payload.get('iss')}"
            )

        exp = int(payload.get("exp", 0))
        if exp <= int(time.time()):
            raise JWTValidationError("Token has expired")

        roles = self._extract_roles(payload)
        return TokenPayload(
            sub=str(payload["sub"]),
            iss=str(payload["iss"]),
            exp=exp,
            roles=roles,
            raw=payload,
        )

    def _resolve_key(self, token: str):
        if self._public_key_pem:
            return self._public_key_pem
        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(self._settings.jwks_url)
        signing_key = self._jwks_client.get_signing_key_from_jwt(token)
        return signing_key.key

    def _extract_roles(self, payload: dict[str, Any]) -> list[str]:
        claim_path = self._settings.roles_claim.split(".")
        node: Any = payload
        for part in claim_path:
            if not isinstance(node, dict):
                return []
            node = node.get(part, {})
        if isinstance(node, list):
            return [str(r) for r in node]
        return []
