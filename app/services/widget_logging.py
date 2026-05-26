# Owner: Amer
"""Structured logging and tracing for the widget token endpoint.

Per Constitution Principle V (Lean Serving & Mandatory Redaction):
- Widget IDs and source IPs are HMAC-hashed with WIDGET_LOG_SALT before logging.
- Raw JWT signing secrets, raw tokens, and raw PII never appear in logs.

Field schema: data-model.md §3. Requirements: spec.md FR-020 through FR-023.
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import hmac
import time
from typing import Iterator
from uuid import UUID, uuid4

import structlog

from app.domain.widget import WidgetTokenRefusalReason
from app.services.widget_settings import widget_settings

_log = structlog.get_logger("widget.token")

_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "widget_trace_id", default=None
)


def _hash(value: str) -> str:
    salt = widget_settings().widget_log_salt.encode("utf-8")
    return hmac.new(salt, value.encode("utf-8"), hashlib.sha256).hexdigest()


def emit_refusal(
    *,
    reason: WidgetTokenRefusalReason,
    widget_id: UUID,
    source_ip: str,
    origin: str,
    latency_ms: int,
    tenant_id: UUID | None = None,
) -> None:
    """Emit widget.token.refused.

    `tenant_id` is included only when the widget was resolved (every reason
    except `unknown_widget`). Internal logs are not visible to attackers, so
    FR-007's external indistinguishability is unaffected. See data-model.md §3.
    """
    payload: dict[str, object] = {
        "widget_id_hash": _hash(str(widget_id)),
        "ip_hash": _hash(source_ip),
        "origin": origin,
        "reason": reason.value,
        "latency_ms": latency_ms,
    }
    if tenant_id is not None:
        payload["tenant_id"] = str(tenant_id)
    if (trace_id := _trace_id_var.get()) is not None:
        payload["trace_id"] = trace_id
    _log.info("widget.token.refused", **payload)


def emit_issuance(
    *,
    tenant_id: UUID,
    widget_id: UUID,
    source_ip: str,
    origin: str,
    latency_ms: int,
) -> None:
    """Emit widget.token.issued for a successful token exchange."""
    payload: dict[str, object] = {
        "tenant_id": str(tenant_id),
        "widget_id_hash": _hash(str(widget_id)),
        "ip_hash": _hash(source_ip),
        "origin": origin,
        "latency_ms": latency_ms,
    }
    if (trace_id := _trace_id_var.get()) is not None:
        payload["trace_id"] = trace_id
    _log.info("widget.token.issued", **payload)


@contextlib.contextmanager
def widget_trace_span(origin: str) -> Iterator[dict[str, object]]:
    """Open a distributed trace span for one POST /widgets/token request (FR-022).

    Yields a mutable attributes dict the caller can populate with outcome details.
    On exit, emits a `widget.token.span` structured log carrying every attribute
    that was set during the request, plus measured latency.
    """
    trace_id = str(uuid4())
    token = _trace_id_var.set(trace_id)
    attrs: dict[str, object] = {
        "trace_id": trace_id,
        "span.name": "widget.token.exchange",
        "request.origin": origin,
        "started_at": time.time(),
    }
    started_perf = time.perf_counter()
    try:
        yield attrs
    finally:
        attrs["latency_ms"] = int((time.perf_counter() - started_perf) * 1000)
        _log.info("widget.token.span", **attrs)
        _trace_id_var.reset(token)
