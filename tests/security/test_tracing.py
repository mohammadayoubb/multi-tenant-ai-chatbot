"""Tests for safe tracing helpers.

Owner: Ayoub / Owner C
"""

from app.infra.tracing import (
    attach_trace_metadata,
    create_request_id,
    create_trace_context,
)


def test_create_request_id_returns_unique_values() -> None:
    """Request IDs should be unique."""

    first_id = create_request_id()
    second_id = create_request_id()

    assert first_id != second_id
    assert isinstance(first_id, str)
    assert isinstance(second_id, str)


def test_create_trace_context_redacts_sensitive_metadata() -> None:
    """Trace metadata should not contain raw PII or secrets."""

    trace = create_trace_context(
        service_name="modelserver",
        metadata={
            "email": "student@example.com",
            "api_key": "sk-test123456789",
        },
    )

    assert trace.service_name == "modelserver"
    assert "student@example.com" not in str(trace.metadata)
    assert "sk-test123456789" not in str(trace.metadata)
    assert "[REDACTED]" in str(trace.metadata)


def test_attach_trace_metadata_preserves_request_id() -> None:
    """Adding metadata should keep the same request ID."""

    trace = create_trace_context(service_name="guardrails")
    updated_trace = attach_trace_metadata(
        trace,
        metadata={"phone": "+961 71 234 567"},
    )

    assert updated_trace.request_id == trace.request_id
    assert updated_trace.service_name == trace.service_name
    assert "+961 71 234 567" not in str(updated_trace.metadata)
    assert "[REDACTED]" in str(updated_trace.metadata)