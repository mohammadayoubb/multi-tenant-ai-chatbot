# Owner: Ayoub
"""Security tests for redaction."""

from app.infra.redaction import redact_text


def test_redacts_fake_openai_key() -> None:
    """Secret-looking values should not survive redaction."""
    text = "my key is sk-test123456789"
    assert "sk-test" not in redact_text(text)
