"""Test helpers for JWT generation."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
ISSUER = "http://localhost:8080/realms/ai-tutor"
AUDIENCE = "ai-tutor-api"


def generate_rsa_keypair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def make_token(
    private_pem: str,
    *,
    sub: str = "user-123",
    roles: list[str] | None = None,
    exp_offset: int = 3600,
    iss: str = ISSUER,
    aud: str = AUDIENCE,
) -> str:
    now = int(time.time())
    payload = {
        "sub": sub,
        "iss": iss,
        "aud": aud,
        "exp": now + exp_offset,
        "iat": now,
        "realm_access": {"roles": roles or ["Learner"]},
    }
    return jwt.encode(payload, private_pem, algorithm="RS256")
