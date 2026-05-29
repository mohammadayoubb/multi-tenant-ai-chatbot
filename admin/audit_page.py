# Owner: Amer
"""Audit-logs admin page (Spec 009 US2 T077, also reused by US3 T087).

The page accepts a ``role`` parameter that branches the data source:

  - ``role="tenant_admin"`` → `GET /tenants/{tid}/audit-logs` (own-tenant
    only; FR-030).
  - ``role="tenant_manager"`` → `GET /audit-logs` (platform-scoped feed
    backed by `TenantRepository.list_audit_logs_platform_scope`).

The TM render path adds filter controls (actor, tenant_id, action, date
range) that are sent as query-string parameters; the TA path never exposes
those controls.

Any non-2xx response or transport error collapses to a generic "forbidden /
unavailable" message — no raw server text is ever surfaced (Principle V).
"""

from __future__ import annotations

from typing import Any

import httpx
import streamlit as st

from admin._admin_http import http_client as _http_client, signed_in_tenant_id
from admin._table import render_table


_GENERIC_FORBIDDEN = "You do not have permission to view audit logs."
_GENERIC_UNAVAILABLE = "Audit logs are currently unavailable; please retry."


def _ta_url() -> str:
    return f"/tenants/{signed_in_tenant_id()}/audit-logs"


def _tm_url() -> str:
    return "/audit-logs"


def _fetch(path: str, params: dict[str, str] | None = None) -> tuple[int, Any]:
    try:
        with _http_client() as client:
            resp = client.get(path, params=params or {})
    except httpx.HTTPError:
        return 0, None
    try:
        body = resp.json()
    except ValueError:
        body = None
    return resp.status_code, body


def _normalize_rows(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in body:
        if not isinstance(entry, dict):
            continue
        out.append(
            {
                "created_at": entry.get("created_at", "—"),
                "actor_id": entry.get("actor_id") or "—",
                "actor_role": entry.get("actor_role") or "—",
                "tenant_id": entry.get("tenant_id") or "—",
                "action": entry.get("action", "—"),
                "metadata_json": entry.get("metadata_json") or {},
            }
        )
    return out


def _render_table(rows: list[dict[str, Any]]) -> None:
    table = [
        {
            "created_at": r["created_at"],
            "actor_id": r["actor_id"],
            "actor_role": r["actor_role"],
            "tenant_id": r["tenant_id"],
            "action": r["action"],
        }
        for r in rows
    ]
    render_table(
        table,
        columns=["created_at", "actor_id", "actor_role", "tenant_id", "action"],
        empty_state={
            "title": "No audit events yet",
            "message": "Admin actions will appear here as they occur.",
        },
        key="audit_logs_table",
    )


def _render_detail_modal(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    options = [
        f"{r['created_at']} — {r['action']} ({r['actor_id']})" for r in rows
    ]
    chosen = st.selectbox("Inspect event", options, key="audit_detail_select")
    selected = rows[options.index(chosen)] if chosen in options else rows[0]
    st.markdown("#### Event detail")
    st.markdown(f"**Action:** {selected.get('action', '—')}")
    st.markdown(f"**Actor:** {selected.get('actor_id', '—')} "
                f"({selected.get('actor_role', '—')})")
    st.markdown(f"**Tenant:** `{selected.get('tenant_id', '—')}`")
    st.markdown(f"**At:** {selected.get('created_at', '—')}")
    st.markdown("**Metadata:**")
    st.json(selected.get("metadata_json") or {})


def _render_ta(_role: str) -> None:
    status_code, body = _fetch(_ta_url())
    if status_code == 403:
        st.error(_GENERIC_FORBIDDEN)
        return
    if status_code < 200 or status_code >= 300:
        st.error(_GENERIC_UNAVAILABLE)
        return
    rows = _normalize_rows(body)
    _render_table(rows)
    _render_detail_modal(rows)


def _render_tm(_role: str) -> None:
    st.markdown("#### Filter")
    cols = st.columns(4)
    actor = cols[0].text_input("Actor", key="audit_filter_actor")
    tenant_filter = cols[1].text_input("Tenant id", key="audit_filter_tenant")
    action = cols[2].text_input("Action", key="audit_filter_action")
    date_from = cols[3].text_input(
        "Date from (ISO)", key="audit_filter_date_from"
    )
    date_to = st.text_input("Date to (ISO)", key="audit_filter_date_to")

    params: dict[str, str] = {}
    if actor.strip():
        params["actor"] = actor.strip()
    if tenant_filter.strip():
        params["tenant_id"] = tenant_filter.strip()
    if action.strip():
        params["action"] = action.strip()
    if date_from.strip():
        params["date_from"] = date_from.strip()
    if date_to.strip():
        params["date_to"] = date_to.strip()

    status_code, body = _fetch(_tm_url(), params=params)
    if status_code == 403:
        st.error(_GENERIC_FORBIDDEN)
        return
    if status_code < 200 or status_code >= 300:
        st.error(_GENERIC_UNAVAILABLE)
        return
    rows = _normalize_rows(body)
    _render_table(rows)
    _render_detail_modal(rows)


def render(*, role: str) -> None:
    """Render the Audit Logs tab.

    Args:
        role: ``"tenant_admin"`` for the own-tenant feed; ``"tenant_manager"``
            for the platform-wide feed with filter controls.
    """
    if role == "tenant_manager":
        _render_tm(role)
    else:
        _render_ta(role)
