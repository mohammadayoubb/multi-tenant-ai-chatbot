# Owner: Ayoub
"""PII and secret redaction helpers."""

import re

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
]


def redact_text(text: str) -> str:
    """Redact common secret-looking values before logging or tracing."""
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted
