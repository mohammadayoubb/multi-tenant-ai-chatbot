"""Redaction utilities for Concierge.

Owner: Ayoub / Owner C

This module removes sensitive values before text is written to logs,
traces, memory, or debug output.

Important:
- Do not log raw visitor messages if they may contain PII or secrets.
- Redaction must happen before storing/logging sensitive text.
"""

from __future__ import annotations

import re


REDACTION_TEXT = "[REDACTED]"


# Common email format.
EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# Basic international/local phone pattern.
PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)"
)

# Common API key / token-looking values.
SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{10,}\b", re.IGNORECASE),
    re.compile(r"\b(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s,;]+", re.IGNORECASE),
]


def redact_text(text: str | None) -> str:
    """Redact sensitive values from text.

    Redacts:
    - email addresses
    - phone numbers
    - OpenAI-style keys such as sk-...
    - Bearer tokens
    - key/value secrets like password=...
    """

    if text is None:
        return ""

    redacted = text

    redacted = EMAIL_PATTERN.sub(REDACTION_TEXT, redacted)
    redacted = PHONE_PATTERN.sub(REDACTION_TEXT, redacted)

    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(REDACTION_TEXT, redacted)

    return redacted


def contains_sensitive_data(text: str | None) -> bool:
    """Return True if text appears to contain sensitive data."""

    if text is None:
        return False

    if EMAIL_PATTERN.search(text):
        return True

    if PHONE_PATTERN.search(text):
        return True

    return any(pattern.search(text) for pattern in SECRET_PATTERNS)