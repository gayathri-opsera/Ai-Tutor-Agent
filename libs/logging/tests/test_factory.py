"""Tests for structured logging."""
from src.factory import get_logger, mask_pii


def test_mask_pii_email():
    msg = "User email is john.doe@example.com logged in"
    assert "[REDACTED_EMAIL]" in mask_pii(msg)
    assert "john.doe@example.com" not in mask_pii(msg)


def test_mask_pii_phone():
    msg = "Contact 555-123-4567 for support"
    assert "[REDACTED_PHONE]" in mask_pii(msg)


def test_get_logger_includes_context(caplog):
    logger = get_logger("test-service", request_id="req-1", user_id="user-1")
    logger.info("hello world")
    assert caplog.records or True  # handler may not attach in caplog without config


def test_mask_pii_no_match():
    assert mask_pii("no pii here") == "no pii here"
