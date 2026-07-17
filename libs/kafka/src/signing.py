"""Kafka event payload signing and verification (HMAC-SHA256).

Addresses the "Kafka Event Trust — Payload Authenticity Not Verified" finding.
Consumers call ``verify_signature()`` before processing any message to guard
against malformed or malicious payloads that could propagate untrusted data
into business logic.

The signing key is read from ``KAFKA_SIGNING_KEY`` env var.  In local/test
environments a predictable default is used so tests work without secrets.

Usage (producer side)::

    from libs.kafka.src.signing import sign_payload, SignedEnvelope
    envelope = sign_payload({"event_type": "course.approved", "kb_id": "abc"})
    await producer.produce("course-approval-events", envelope.model_dump())

Usage (consumer side)::

    from libs.kafka.src.signing import verify_signature, SignatureError
    try:
        payload = verify_signature(raw_message)
    except SignatureError as e:
        logger.warning("Dropping message with invalid signature: %s", e)
        return
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any

from pydantic import BaseModel, Field

_DEFAULT_KEY = "local-dev-kafka-signing-key-change-in-prod"
_SIGNING_KEY: bytes = os.getenv("KAFKA_SIGNING_KEY", _DEFAULT_KEY).encode()
_MAX_AGE_SECONDS = int(os.getenv("KAFKA_MESSAGE_MAX_AGE_SECONDS", "300"))


class SignatureError(ValueError):
    """Raised when a Kafka message fails signature or freshness checks."""


class SignedEnvelope(BaseModel):
    """Wrapper that adds HMAC-SHA256 signature and timestamp to any Kafka payload."""

    payload: dict[str, Any] = Field(description="The original event payload")
    sig: str = Field(description="HMAC-SHA256 hex digest of canonical payload JSON")
    ts: int = Field(description="Unix timestamp (seconds) at signing time")
    schema_version: str = Field(default="1.0", description="Envelope schema version")

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SignedEnvelope":
        """Create a signed envelope from an event payload dict."""
        ts = int(time.time())
        canonical = _canonical(payload, ts)
        sig = _hmac_sign(canonical)
        return cls(payload=payload, sig=sig, ts=ts)


def _canonical(payload: dict[str, Any], ts: int) -> bytes:
    """Produce a deterministic byte string for signing."""
    return json.dumps({"payload": payload, "ts": ts}, sort_keys=True, separators=(",", ":")).encode()


def _hmac_sign(data: bytes) -> str:
    return hmac.new(_SIGNING_KEY, data, hashlib.sha256).hexdigest()


def sign_payload(payload: dict[str, Any]) -> SignedEnvelope:
    """Return a ``SignedEnvelope`` wrapping *payload* with a fresh HMAC signature."""
    return SignedEnvelope.from_payload(payload)


def verify_signature(
    raw: dict[str, Any],
    *,
    max_age_seconds: int = _MAX_AGE_SECONDS,
) -> dict[str, Any]:
    """Verify the HMAC signature and freshness of a Kafka message envelope.

    Args:
        raw: The raw dict deserialized from the Kafka message value.
        max_age_seconds: Reject messages older than this many seconds.

    Returns:
        The inner payload dict if the signature is valid.

    Raises:
        SignatureError: If the envelope is missing, expired, or has an invalid sig.
    """
    if "sig" not in raw or "ts" not in raw or "payload" not in raw:
        raise SignatureError(
            "Message is not a SignedEnvelope — missing 'sig', 'ts', or 'payload' fields. "
            "Producer must use libs.kafka.src.signing.sign_payload()."
        )

    age = int(time.time()) - int(raw["ts"])
    if age > max_age_seconds:
        raise SignatureError(
            f"Message is {age}s old (max {max_age_seconds}s). "
            "Possible replay attack or clock skew."
        )

    canonical = _canonical(raw["payload"], raw["ts"])
    expected = _hmac_sign(canonical)
    if not hmac.compare_digest(expected, str(raw["sig"])):
        raise SignatureError("HMAC signature mismatch — payload may have been tampered with.")

    return raw["payload"]
