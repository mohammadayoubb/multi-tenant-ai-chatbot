"""Tests for redaction utilities.

Owner: Ayoub / Owner C

These tests prove that obvious PII and fake secrets are removed before
text can be stored in logs, traces, or memory.
"""

from app.infra.redaction import contains_sensitive_data, redact_text


def test_redacts_email_address() -> None:
    """Email addresses should not remain visible after redaction."""

    text = "Please contact me at student@example.com"

    redacted = redact_text(text)

    assert "student@example.com" not in redacted
    assert "[REDACTED]" in redacted


def test_redacts_phone_number() -> None:
    """Phone numbers should not remain visible after redaction."""

    text = "My phone number is +961 71 234 567"

    redacted = redact_text(text)

    assert "+961 71 234 567" not in redacted
    assert "[REDACTED]" in redacted


def test_redacts_fake_openai_key() -> None:
    """Fake OpenAI-style API keys should not remain visible."""

    text = "Here is my key: sk-fake1234567890abcdef"

    redacted = redact_text(text)

    assert "sk-fake1234567890abcdef" not in redacted
    assert "[REDACTED]" in redacted


def test_redacts_bearer_token() -> None:
    """Bearer tokens should not remain visible."""

    text = "Authorization: Bearer abcdef1234567890"

    redacted = redact_text(text)

    assert "Bearer abcdef1234567890" not in redacted
    assert "[REDACTED]" in redacted


def test_detects_sensitive_data() -> None:
    """Sensitive text should be detected before logging or tracing."""

    assert contains_sensitive_data("email me at person@example.com") is True
    assert contains_sensitive_data("normal public message") is False