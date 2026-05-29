# Owner: Amer
"""Tenant-admin Overview dashboard (Spec 009 US2, T068).

Headline KPIs for a single signed-in tenant admin:
  - Tenant name
  - Widget enabled
  - Leads in the last 30 days
  - Open escalations
  - Conversations in the last 30 days
  - Tokens (month-to-date)
  - Cost USD (month-to-date)

Any endpoint that is unreachable or returns a non-2xx degrades to a placeholder
KPI value with a visible "(placeholder)" caption, per FR-013 / Principle V.
No raw exception or transport-error text is surfaced to the operator.

Tests monkeypatch the module-level `_http_client` symbol; everything that
talks to the backend goes through it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import streamlit as st

from admin._admin_http import (
    PLACEHOLDER as _PLACEHOLDER,
    http_client as _http_client,
    render_placeholder_caption,
    signed_in_tenant_id,
)
from admin._kpi import render_kpi_row
from admin.auth_state import get_tenant_id


def _get_json(path: str) -> tuple[Any, bool]:
    """Return ``(body, ok)``. ``ok`` is False on any transport or non-2xx error."""
    try:
        with _http_client() as client:
            resp = client.get(path)
    except httpx.HTTPError:
        return None, False
    if resp.status_code < 200 or resp.status_code >= 300:
        return None, False
    try:
        return resp.json(), True
    except ValueError:
        return None, False


def _count_recent_leads(leads: Any, cutoff: datetime) -> int | None:
    if not isinstance(leads, list):
        return None
    n = 0
    for lead in leads:
        if not isinstance(lead, dict):
            continue
        created = lead.get("created_at")
        if not isinstance(created, str):
            continue
        try:
            ts = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except ValueError:
            continue
        # API timestamps from naive DateTime columns arrive without tz; treat
        # those as UTC so the comparison against the tz-aware cutoff works.
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts >= cutoff:
            n += 1
    return n


def _count_open_escalations(tickets: Any) -> int | None:
    if not isinstance(tickets, list):
        return None
    open_states = {"pending", "in_progress", "open"}
    n = 0
    for ticket in tickets:
        if isinstance(ticket, dict) and ticket.get("status") in open_states:
            n += 1
    return n


def render() -> None:
    st.title("Overview")

    tenant_id = get_tenant_id() or signed_in_tenant_id()
    cutoff_30d = datetime.now(timezone.utc) - timedelta(days=30)

    widget_cfg, widget_ok = _get_json("/widgets/config")
    usage, usage_ok = _get_json(f"/tenants/{tenant_id}/usage")
    leads, leads_ok = _get_json("/leads")
    escalations, escalations_ok = _get_json("/escalations")

    if widget_ok and isinstance(widget_cfg, dict):
        widget_value = "Yes" if widget_cfg.get("enabled") else "No"
    else:
        widget_value = _PLACEHOLDER

    if usage_ok and isinstance(usage, dict):
        tokens_value = f"{int(usage.get('total_tokens', 0)):,}"
        cost_value = f"${float(usage.get('total_cost_usd', 0.0)):.2f}"
    else:
        tokens_value = _PLACEHOLDER
        cost_value = _PLACEHOLDER

    leads_count = _count_recent_leads(leads, cutoff_30d) if leads_ok else None
    leads_value = str(leads_count) if leads_count is not None else _PLACEHOLDER

    open_count = _count_open_escalations(escalations) if escalations_ok else None
    escalations_value = str(open_count) if open_count is not None else _PLACEHOLDER

    conversations, conversations_ok = _get_json(f"/tenants/{tenant_id}/conversations")
    if conversations_ok and isinstance(conversations, list):
        conversations_value = str(len(conversations))
    elif conversations_ok:
        conversations_value = "0"
    else:
        conversations_value = _PLACEHOLDER

    any_placeholder = not all(
        [widget_ok, usage_ok, leads_ok, escalations_ok, conversations_ok]
    )

    render_kpi_row(
        [
            ("Tenant", tenant_id or _PLACEHOLDER),
            ("Widget enabled", widget_value),
            ("Leads (30d)", leads_value),
        ]
    )
    render_kpi_row(
        [
            ("Open escalations", escalations_value),
            ("Conversations (30d)", conversations_value),
            ("Tokens (MTD)", tokens_value),
            ("Cost (MTD)", cost_value),
        ]
    )

    if any_placeholder:
        render_placeholder_caption(
            "one or more backend endpoints were unavailable; "
            f"the affected cards show `{_PLACEHOLDER}` until the service responds."
        )
