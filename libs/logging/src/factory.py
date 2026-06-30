"""PII masking and structured logger factory."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")


def mask_pii(message: str) -> str:
    """Redact email addresses and phone numbers from log messages."""
    masked = _EMAIL_RE.sub("[REDACTED_EMAIL]", message)
    return _PHONE_RE.sub("[REDACTED_PHONE]", masked)


class StructuredLogger(logging.LoggerAdapter):
    """Logger adapter that injects standard fields and masks PII."""

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        extra = kwargs.setdefault("extra", {})
        extra.setdefault("service_name", self.extra.get("service_name"))
        extra.setdefault("request_id", self.extra.get("request_id"))
        extra.setdefault("user_id", self.extra.get("user_id"))
        extra.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        return mask_pii(str(msg)), kwargs


def get_logger(
    service_name: str,
    *,
    request_id: str | None = None,
    user_id: str | None = None,
    level: int = logging.INFO,
) -> StructuredLogger:
    """Create a structured logger with standard context fields."""
    base = logging.getLogger(service_name)
    base.setLevel(level)
    if not base.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        base.addHandler(handler)
    return StructuredLogger(
        base,
        {"service_name": service_name, "request_id": request_id, "user_id": user_id},
    )
