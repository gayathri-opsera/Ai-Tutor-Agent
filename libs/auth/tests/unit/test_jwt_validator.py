"""Unit tests for JWTValidator."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.config import AuthSettings
from src.jwt_validator import JWTValidationError, JWTValidator
from tests.conftest import ISSUER, make_token


@pytest.fixture
def keypair():
    from tests.conftest import generate_rsa_keypair
    return generate_rsa_keypair()


@pytest.fixture
def validator(keypair):
    _, public_pem = keypair
    settings = AuthSettings(issuer=ISSUER, audience="ai-tutor-api")
    return JWTValidator(auth_settings=settings, public_key_pem=public_pem)


def test_decode_valid_token(validator, keypair):
    private_pem, _ = keypair
    token = make_token(private_pem, roles=["Admin", "Learner"])
    payload = validator.decode(token)
    assert payload.sub == "user-123"
    assert payload.iss == ISSUER
    assert "Admin" in payload.roles
    assert payload.has_role("Admin")


def test_decode_expired_token(validator, keypair):
    private_pem, _ = keypair
    token = make_token(private_pem, exp_offset=-60)
    with pytest.raises(JWTValidationError, match="expired"):
        validator.decode(token)


def test_decode_malformed_token(validator):
    with pytest.raises(JWTValidationError):
        validator.decode("not.a.valid.jwt")


def test_decode_wrong_issuer(validator, keypair):
    private_pem, _ = keypair
    token = make_token(private_pem, iss="http://evil.com/realms/other")
    with pytest.raises(JWTValidationError, match="Invalid issuer"):
        validator.decode(token)


def test_decode_bearer_prefix(validator, keypair):
    private_pem, _ = keypair
    token = make_token(private_pem)
    payload = validator.decode(f"Bearer {token}")
    assert payload.sub == "user-123"


def test_role_extraction(validator, keypair):
    private_pem, _ = keypair
    token = make_token(private_pem, roles=["Creator"])
    payload = validator.decode(token)
    assert payload.roles == ["Creator"]
    assert not payload.has_role("Admin")


def test_decode_empty_token(validator):
    with pytest.raises(JWTValidationError, match="missing"):
        validator.decode("")


def test_has_role_false(validator, keypair):
    private_pem, _ = keypair
    token = make_token(private_pem, roles=["Learner"])
    payload = validator.decode(token)
    assert not payload.has_role("SuperAdmin")
