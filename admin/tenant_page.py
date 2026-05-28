# Owner: Amer
"""Tenant overview admin page (read-only).

Feature 005 US1 — see specs/005-admin-read-only-pages/.

Renders a header card for the current tenant (name, slug, status, plan,
created_at) plus the 20 most recent audit log rows. Read-only: no edit,
suspend, or erase controls. Any non-2xx response, missing-required-field
body, or transport error collapses to a single placeholder fallback with a
visible "(placeholder)" caption (FR-013, research Decision 5).
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import streamlit as st

from admin._admin_http import (
    TENANT_ID,
    http_client as _http_client,
    signed_in_tenant_id,
)

_SAMPLE_TENANT: dict[str, Any] = {
    "id": TENANT_ID,
    "name": "Sample Tenant",
    "slug": "sample-tenant",
    "status": "active",
    "plan": "starter",
    "created_at": "2026-01-01T00:00:00Z",
}

_SAMPLE_AUDIT: list[dict[str, Any]] = [
    {
        "created_at": "2026-05-26T12:00:00Z",
        "actor_role": "tenant_manager",
        "action": "tenant.provisioned",
        "metadata_json": {"plan": "starter"},
    },
    {
        "created_at": "2026-05-25T09:30:00Z",
        "actor_role": "tenant_admin",
        "action": "widget.origin_added",
        "metadata_json": {"origin": "https://sample.example"},
    },
    {
        "created_at": "2026-05-24T15:45:00Z",
        "actor_role": "tenant_admin",
        "action": "cms.page_updated",
        "metadata_json": {"page_slug": "pricing", "field": "body"},
    },
]


def _fetch_json(path: str, required: tuple[str, ...]) -> Any | None:
    """Return parsed JSON when 2xx + required keys present; else None."""
    try:
        with _http_client() as client:
            resp = client.get(path)
    except httpx.HTTPError:
        return None
    if resp.status_code < 200 or resp.status_code >= 300:
        return None
    try:
        body = resp.json()
    except ValueError:
        return None
    if isinstance(body, dict) and not all(k in body for k in required):
        return None
    return body


def _render_header(tenant: dict[str, Any], placeholder: bool) -> None:
    name = tenant.get("name", "—")
    slug = tenant.get("slug") or "—"
    status = tenant.get("status", "—")
    plan = tenant.get("plan") or "—"
    created_at = tenant.get("created_at", "—")
    st.markdown(f"### {name}")
    if placeholder:
        st.caption("(placeholder)")
    cols = st.columns(4)
    cols[0].markdown(f"**Slug**\n\n{slug}")
    cols[1].markdown(f"**Status**\n\n{status}")
    cols[2].markdown(f"**Plan**\n\n{plan}")
    cols[3].markdown(f"**Created**\n\n{created_at}")


def _render_audit_log(rows: list[dict[str, Any]], placeholder: bool) -> None:
    st.markdown("#### Recent audit log")
    if placeholder:
        st.caption("(placeholder)")
    table = [
        {
            "created_at": r.get("created_at", "—"),
            "actor_role": r.get("actor_role", "—"),
            "action": r.get("action", "—"),
            "metadata_json": json.dumps(r.get("metadata_json", {}))[:80],
        }
        for r in rows[:20]
    ]
    st.dataframe(table, key="tenant_audit_log_table", width="stretch")


def render() -> None:
    tenant_id = signed_in_tenant_id()
    tenant_body = _fetch_json(
        f"/tenants/{tenant_id}", required=("name", "status", "created_at")
    )
    tenant_placeholder = tenant_body is None
    tenant = tenant_body if isinstance(tenant_body, dict) else _SAMPLE_TENANT

    audit_body = _fetch_json(f"/tenants/{tenant_id}/audit-logs", required=())
    audit_placeholder = not isinstance(audit_body, list) or not audit_body
    audit_rows = audit_body if isinstance(audit_body, list) and audit_body else _SAMPLE_AUDIT

    _render_header(tenant, placeholder=tenant_placeholder)
    _render_audit_log(audit_rows, placeholder=audit_placeholder)
