"""Safe tracing helpers for Concierge.

Owner: Ayoub / Owner C

This module creates request IDs and safe trace metadata.

Important:
- Do not store raw visitor messages in traces.
- Do not store secrets, tokens, passwords, or PII in traces.
- Use redaction before putting user-provided text into trace metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from app.infra.redaction import redact_text


@dataclass(frozen=True)
class TraceContext:
    """Small immutable trace context for one request or service call."""

    request_id: str
    service_name: str
    created_at: str
    metadata: dict[str, str] = field(default_factory=dict)


def create_request_id() -> str:
    """Create a unique request ID for tracing one request across services."""

    return str(uuid4())


def create_trace_context(
    service_name: str,
    request_id: str | None = None,
    metadata: dict[str, str] | None = None,
) -> TraceContext:
    """Create a trace context with redacted metadata."""

    safe_metadata = {}

    if metadata:
        for key, value in metadata.items():
            safe_metadata[key] = redact_text(str(value))

    return TraceContext(
        request_id=request_id or create_request_id(),
        service_name=service_name,
        created_at=datetime.now(UTC).isoformat(),
        metadata=safe_metadata,
    )


def attach_trace_metadata(
    trace_context: TraceContext,
    metadata: dict[str, str],
) -> TraceContext:
    """Return a new trace context with extra redacted metadata."""

    safe_metadata = dict(trace_context.metadata)

    for key, value in metadata.items():
        safe_metadata[key] = redact_text(str(value))

    return TraceContext(
        request_id=trace_context.request_id,
        service_name=trace_context.service_name,
        created_at=trace_context.created_at,
        metadata=safe_metadata,
    )