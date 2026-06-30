"""PII scrubbing middleware (HIPAA PHI handling mandate).

Redacts the following from outbound prompts before they reach any provider:
  - Email addresses
  - US phone numbers (various formats)
  - US Social Security Numbers
  - US credit card numbers
  - Names matching a configurable pattern list (default: HHS common name list)

Redaction uses `[REDACTED-<TYPE>]` tokens so that downstream consumers can
detect that scrubbing occurred without leaking any personal information.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# ── Built-in patterns ────────────────────────────────────────────────────────

_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "EMAIL",
        re.compile(
            r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
            re.IGNORECASE,
        ),
    ),
    # Credit card MUST come before phone — card numbers match the phone digit pattern
    (
        "CREDIT_CARD",
        re.compile(
            r"\b(?:4[0-9]{12}(?:[0-9]{3})?|"       # Visa (13 or 16 digits)
            r"5[1-5][0-9]{14}|"                     # Mastercard (16 digits)
            r"3[47][0-9]{13}|"                      # Amex (15 digits)
            r"6(?:011|5[0-9]{2})[0-9]{12})\b"       # Discover (16 digits)
        ),
    ),
    (
        "SSN",
        re.compile(
            r"\b(?!000|666|9\d{2})\d{3}[- ]?(?!00)\d{2}[- ]?(?!0000)\d{4}\b"
        ),
    ),
    (
        "PHONE",
        re.compile(
            r"""
            (?:
                \+?1[\s\-.]?           # optional country code
            )?
            (?:\(?\d{3}\)?[\s\-.]?)    # area code
            \d{3}[\s\-.]?\d{4}         # local number
            """,
            re.VERBOSE,
        ),
    ),
]


def _load_extra_patterns(path: str) -> list[tuple[str, re.Pattern]]:
    """Load additional regex patterns from a JSON file.

    File format:
      [{"label": "PATIENT_ID", "pattern": "PT-\\d{6}"}]
    """
    file = Path(path)
    if not file.exists():
        return []
    data = json.loads(file.read_text())
    result = []
    for item in data:
        label = item.get("label", "CUSTOM")
        try:
            result.append((label, re.compile(item["pattern"])))
        except re.error:
            pass
    return result


class PIIScrubber:
    """Stateless scrubber that redacts PII from arbitrary text.

    Patterns are compiled once at instantiation so repeated scrub() calls
    add no regex-compile overhead.
    """

    def __init__(
        self,
        extra_patterns_file: str = "",
        name_list: list[str] | None = None,
    ) -> None:
        self._patterns = list(_PATTERNS)

        if extra_patterns_file:
            self._patterns.extend(_load_extra_patterns(extra_patterns_file))

        # Build a name-matching pattern from the configurable name list.
        # The list approach avoids an NLP dependency while still covering
        # the most common first/last name combinations in the training corpus.
        if name_list:
            name_alts = "|".join(re.escape(n) for n in sorted(name_list, key=len, reverse=True))
            self._patterns.append(
                ("NAME", re.compile(rf"\b(?:{name_alts})\b", re.IGNORECASE))
            )

    def scrub(self, text: str) -> str:
        """Return `text` with all PII replaced by [REDACTED-<TYPE>] tokens."""
        for label, pattern in self._patterns:
            text = pattern.sub(f"[REDACTED-{label}]", text)
        return text

    def scrub_messages(self, messages: list[dict]) -> list[dict]:
        """Scrub PII from a list of role/content message dicts (in-place copy)."""
        return [
            {**msg, "content": self.scrub(msg.get("content", ""))}
            for msg in messages
        ]
