"""Unit tests for PIIScrubber — 10 PII-laden prompt fixtures.

Covers: email, phone, SSN, credit card, custom patterns, and message-list scrubbing.
"""
from __future__ import annotations

import json
import os
import tempfile

import pytest

from src.middleware.pii_scrubber import PIIScrubber


@pytest.fixture
def scrubber() -> PIIScrubber:
    return PIIScrubber()


# ── Email ────────────────────────────────────────────────────────────────────

class TestEmailScrubbing:
    def test_plain_email(self, scrubber):
        result = scrubber.scrub("Contact me at alice@example.com for help.")
        assert "alice@example.com" not in result
        assert "[REDACTED-EMAIL]" in result

    def test_email_with_subdomains(self, scrubber):
        result = scrubber.scrub("Reach us at support@mail.company.org now.")
        assert "@" not in result.replace("[REDACTED-EMAIL]", "")
        assert "[REDACTED-EMAIL]" in result

    def test_multiple_emails_in_one_prompt(self, scrubber):
        text = "From: bob@test.com, To: carol@test.org — re: student records."
        result = scrubber.scrub(text)
        assert "bob@test.com" not in result
        assert "carol@test.org" not in result
        assert result.count("[REDACTED-EMAIL]") == 2


# ── Phone numbers ────────────────────────────────────────────────────────────

class TestPhoneScrubbing:
    def test_us_phone_dashes(self, scrubber):
        result = scrubber.scrub("Call me at 555-867-5309.")
        assert "867-5309" not in result
        assert "[REDACTED-PHONE]" in result

    def test_us_phone_dots(self, scrubber):
        result = scrubber.scrub("My number is 555.123.4567, thanks.")
        assert "123.4567" not in result
        assert "[REDACTED-PHONE]" in result

    def test_us_phone_with_country_code(self, scrubber):
        result = scrubber.scrub("International: +1 (800) 555-1234.")
        assert "555-1234" not in result
        assert "[REDACTED-PHONE]" in result


# ── SSN ──────────────────────────────────────────────────────────────────────

class TestSSNScrubbing:
    def test_ssn_dashes(self, scrubber):
        result = scrubber.scrub("SSN: 123-45-6789 on file.")
        assert "123-45-6789" not in result
        assert "[REDACTED-SSN]" in result

    def test_ssn_compact(self, scrubber):
        result = scrubber.scrub("The patient SSN is 123456789.")
        assert "123456789" not in result
        assert "[REDACTED-SSN]" in result


# ── Credit card ──────────────────────────────────────────────────────────────

class TestCreditCardScrubbing:
    def test_visa_card(self, scrubber):
        result = scrubber.scrub("Payment: 4111111111111111 (Visa)")
        assert "4111111111111111" not in result
        assert "[REDACTED-CREDIT_CARD]" in result

    def test_mastercard(self, scrubber):
        result = scrubber.scrub("MC: 5500005555555559 was declined.")
        assert "5500005555555559" not in result
        assert "[REDACTED-CREDIT_CARD]" in result


# ── Mixed PII in a real prompt ────────────────────────────────────────────────

class TestMixedPII:
    def test_prompt_with_multiple_pii_types(self, scrubber):
        prompt = (
            "Student profile: Jane Doe, email jane.doe@school.edu, "
            "phone 555-321-9876, SSN 321-54-9876, card 4111111111111111."
        )
        result = scrubber.scrub(prompt)
        assert "jane.doe@school.edu" not in result
        assert "321-9876" not in result
        assert "321-54-9876" not in result
        assert "4111111111111111" not in result

    def test_clean_text_unchanged(self, scrubber):
        text = "What is the derivative of x squared?"
        assert scrubber.scrub(text) == text


# ── Custom name list ─────────────────────────────────────────────────────────

class TestNameScrubbing:
    def test_name_from_list_redacted(self):
        s = PIIScrubber(name_list=["Johnathan", "Doe"])
        result = s.scrub("Patient Johnathan Doe was admitted.")
        assert "Johnathan" not in result
        assert "[REDACTED-NAME]" in result

    def test_name_not_in_list_preserved(self):
        s = PIIScrubber(name_list=["Alice"])
        result = s.scrub("Bob is a student.")
        assert "Bob" in result


# ── Extra patterns from file ──────────────────────────────────────────────────

class TestExtraPatterns:
    def test_custom_pattern_from_file(self):
        patterns = [{"label": "PATIENT_ID", "pattern": "PT-\\d{6}"}]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(patterns, f)
            path = f.name
        try:
            s = PIIScrubber(extra_patterns_file=path)
            result = s.scrub("Patient PT-123456 needs follow-up.")
            assert "PT-123456" not in result
            assert "[REDACTED-PATIENT_ID]" in result
        finally:
            os.unlink(path)


# ── Message-list scrubbing ────────────────────────────────────────────────────

class TestScrubMessages:
    def test_scrub_messages_redacts_content(self, scrubber):
        messages = [
            {"role": "user", "content": "My email is test@test.com."},
            {"role": "system", "content": "You are a helpful assistant."},
        ]
        result = scrubber.scrub_messages(messages)
        assert "test@test.com" not in result[0]["content"]
        assert "[REDACTED-EMAIL]" in result[0]["content"]
        assert result[1]["content"] == "You are a helpful assistant."
        assert result[0]["role"] == "user"  # roles preserved
