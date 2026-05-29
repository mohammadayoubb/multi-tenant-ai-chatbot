# Owner: Amer
"""Platform Overview dashboard for the `tenant_manager` role.

Spec 009 US3 T084.

Surfaces aggregate KPIs across the whole platform:
  - Total tenants
  - Active tenants
  - Suspended tenants
  - Estimated monthly cost (sum across tenants — placeholder until rollup
    endpoint lands; falls back to the Tenants list count for now)
  - Open audit-flagged actions (count of recent rows whose action falls in
    the suspend/erase/blocked-login set)

KPIs use ``_kpi.render_kpi_row`` so the visual language matches the TA
Overview tab. Every endpoint that is unreachable degrades to a "—" with a
visible ``(placeholder)`` caption — no raw error text is surfaced (Principle V).

The legacy "Invite an admin" form is intentionally NOT rendered here; the
TM Invites tab (admin/invites_page.py, T086) owns that surface end-to-end.
"""

from __future__ import annotations

from typing import Any

import httpx
import streamlit as st

from admin._admin_http import (
    PLACEHOLDER as _PLACEHOLDER,
    http_client as _http_client,
    render_placeholder_caption,
)
from admin._kpi import render_kpi_row
from admin.auth_state import get_actor_id

# Actions that should count toward "open audit-flagged actions" in the headline.
# Suspensions, erasures, and revocations are the platform-operator-visible
# events the TM should keep an eye on. The list is intentionally short — when
# real "flagged" alerting lands it will replace this client-side heuristic.
_FLAGGED_ACTIONS = {
    "tenant.suspended",
    "tenant.erased",
    "admin.invite_revoked",
}


def _get_json(path: str, *, params: dict[str, str] | None = None) -> tuple[Any, bool]:
    """Return ``(body, ok)``. ``ok`` is False on any transport or non-2xx error."""
    try:
        with _http_client() as client:
            resp = client.get(path, params=params or {})
    except httpx.HTTPError:
        return None, False
    if resp.status_code < 200 or resp.status_code >= 300:
        return None, False
    try:
        return resp.json(), True
    except ValueError:
        return None, False


def _count_by_status(tenants: Any, status: str) -> int:
    if not isinstance(tenants, list):
        return 0
    return sum(
        1 for t in tenants if isinstance(t, dict) and t.get("status") == status
    )


def _count_flagged(audit_rows: Any) -> int:
    if not isinstance(audit_rows, list):
        return 0
    return sum(
        1
        for r in audit_rows
        if isinstance(r, dict) and r.get("action") in _FLAGGED_ACTIONS
    )


def render() -> None:
    """Render the TM Platform Overview headline."""
    st.title("Platform overview")
    st.caption(f"Signed in as `{get_actor_id() or '—'}` (tenant_manager).")

    tenants, tenants_ok = _get_json("/tenants")
    audit_rows, audit_ok = _get_json("/audit-logs")

    total_value = str(len(tenants)) if tenants_ok and isinstance(tenants, list) else _PLACEHOLDER
    active_value = str(_count_by_status(tenants, "active")) if tenants_ok else _PLACEHOLDER
    suspended_value = (
        str(_count_by_status(tenants, "suspended")) if tenants_ok else _PLACEHOLDER
    )
    flagged_value = str(_count_flagged(audit_rows)) if audit_ok else _PLACEHOLDER

    # Monthly cost rollup endpoint is not yet defined for the TM scope; the
    # KPI shows a placeholder so the card is visually present without lying.
    cost_value = _PLACEHOLDER

    render_kpi_row(
        [
            ("Total tenants", total_value),
            ("Active", active_value),
            ("Suspended", suspended_value),
        ]
    )
    render_kpi_row(
        [
            ("Monthly cost (est.)", cost_value),
            ("Audit-flagged actions", flagged_value),
        ]
    )

    if not all([tenants_ok, audit_ok]):
        render_placeholder_caption(
            "one or more platform endpoints were unavailable; "
            f"the affected cards show `{_PLACEHOLDER}` until the service responds."
        )
    else:
        st.caption("Use the sidebar to drill into Tenants, Invites, or Audit Logs.")
