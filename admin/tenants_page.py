# Owner: Amer
"""TM Tenants admin page (Spec 009 US3, T085).

Lists every tenant on the platform and exposes the four manager actions:

  - Create tenant            (POST /tenants)
  - View metadata            (read-only modal)
  - Suspend tenant           (POST /tenants/{id}/suspend, confirmation required)
  - Trigger erasure          (DELETE /tenants/{id}, double-confirmation required)

The table is sourced from the admin-JWT-gated ``GET /tenants`` route delivered
by Phase 2A T039u. Aggregate counts (CMS pages, leads, conversation totals)
are intentionally NOT exposed — FR-046 forbids the TM from seeing tenant
content under any aggregate that could fingerprint a tenant's data volume.

Status pills are rendered through ``_status_pill.render_status`` so the
"active / suspended / deleted" visual language matches the rest of the admin.
All mutations collapse failures to a generic "(failed)" message — no raw
server text is ever surfaced.
"""

from __future__ import annotations

from typing import Any

import httpx
import streamlit as st

from admin._admin_http import http_client as _http_client, render_placeholder_caption
from admin._empty import render_empty_state
from admin._status_pill import render_status
from admin._table import render_table

_GENERIC_FAILED = "The request failed; please retry."
_GENERIC_FORBIDDEN = "Forbidden — your role cannot perform that action."

_SAMPLE_TENANTS: list[dict[str, Any]] = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "Acme Demo (sample)",
        "slug": "acme",
        "status": "active",
        "plan": "starter",
        "created_at": "2026-05-01T00:00:00Z",
    },
]


def _fetch_tenants() -> tuple[list[dict[str, Any]], bool]:
    try:
        with _http_client() as client:
            resp = client.get("/tenants")
    except httpx.HTTPError:
        return list(_SAMPLE_TENANTS), True
    if resp.status_code < 200 or resp.status_code >= 300:
        return list(_SAMPLE_TENANTS), True
    try:
        body = resp.json()
    except ValueError:
        return list(_SAMPLE_TENANTS), True
    if not isinstance(body, list):
        return list(_SAMPLE_TENANTS), True
    return body, False


def _post_create(name: str) -> tuple[int, Any]:
    try:
        with _http_client() as client:
            resp = client.post("/tenants", json={"name": name})
    except httpx.HTTPError:
        return 0, None
    try:
        body = resp.json()
    except ValueError:
        body = None
    return resp.status_code, body


def _post_suspend(tenant_id: str, reason: str) -> int:
    try:
        with _http_client() as client:
            resp = client.post(
                f"/tenants/{tenant_id}/suspend", json={"reason": reason}
            )
    except httpx.HTTPError:
        return 0
    return resp.status_code


def _delete_tenant(tenant_id: str, reason: str) -> int:
    try:
        with _http_client() as client:
            resp = client.request(
                "DELETE",
                f"/tenants/{tenant_id}",
                json={"reason": reason},
            )
    except httpx.HTTPError:
        return 0
    return resp.status_code


def _surface(status_code: int) -> None:
    if status_code == 403:
        st.error(_GENERIC_FORBIDDEN)
    else:
        st.error(_GENERIC_FAILED)


def _render_table(tenants: list[dict[str, Any]]) -> None:
    if not tenants:
        render_empty_state(
            "No tenants yet",
            "Provision your first tenant with the form below.",
        )
        return
    rows = [
        {
            "name": t.get("name", "—"),
            "slug": t.get("slug") or "—",
            "status": t.get("status", "—"),
            "plan": t.get("plan") or "—",
            "created_at": t.get("created_at", "—"),
            "id": str(t.get("id", "—")),
        }
        for t in tenants
    ]
    render_table(
        rows,
        columns=["name", "slug", "status", "plan", "created_at", "id"],
        empty_state={
            "title": "No tenants yet",
            "message": "Provision your first tenant with the form below.",
        },
        key="tm_tenants_table",
    )

    # Inline status badges below the table so the visual language stays
    # consistent with the rest of the admin. Streamlit's dataframe can't
    # render coloured chips, so we surface them once per row underneath.
    st.markdown("#### Tenant status")
    for t in tenants:
        cols = st.columns([3, 2])
        with cols[0]:
            st.write(t.get("name", "—"))
        with cols[1]:
            render_status(str(t.get("status", "—")), kind="tenant")


def _render_create_form() -> None:
    st.markdown("#### Provision a tenant")
    with st.form("tm_create_tenant_form", clear_on_submit=True):
        name = st.text_input("Tenant name", key="tm_create_name")
        submitted = st.form_submit_button("Create tenant", type="primary")
    if not submitted:
        return
    if not name.strip():
        st.error("Tenant name is required.")
        return
    with st.spinner("Provisioning…"):
        status_code, body = _post_create(name.strip())
    if status_code in (200, 201) and isinstance(body, dict):
        st.success(f"Tenant `{body.get('name', name.strip())}` created.")
        st.rerun()
    else:
        _surface(status_code)


def _render_suspend(tenants: list[dict[str, Any]]) -> None:
    st.markdown("#### Suspend a tenant")
    options = ["—"] + [f"{t.get('name', '?')} ({t.get('id')})" for t in tenants]
    pick = st.selectbox("Tenant", options, key="tm_suspend_pick")
    if pick == "—":
        return
    selected = tenants[options.index(pick) - 1]
    reason = st.text_input("Reason (optional)", key="tm_suspend_reason")
    confirm_label = (
        f'Type tenant name "{selected.get("name")}" to confirm suspension'
    )
    typed = st.text_input(confirm_label, key="tm_suspend_typed")
    matches = typed.strip() == str(selected.get("name", "")).strip() and typed.strip() != ""
    if st.button(
        "Suspend tenant",
        key="tm_suspend_button",
        type="primary",
        disabled=not matches,
    ):
        with st.spinner("Suspending…"):
            code = _post_suspend(str(selected["id"]), reason.strip())
        if code == 200:
            st.success("Tenant suspended.")
            st.rerun()
        else:
            _surface(code)


def _render_erase(tenants: list[dict[str, Any]]) -> None:
    st.markdown("#### Trigger erasure")
    st.warning(
        "Erasure is irreversible — it deletes tenant rows and content "
        "across every table that holds tenant data. Use only on explicit "
        "tenant request or post-contract teardown."
    )
    options = ["—"] + [f"{t.get('name', '?')} ({t.get('id')})" for t in tenants]
    pick = st.selectbox("Tenant", options, key="tm_erase_pick")
    if pick == "—":
        return
    selected = tenants[options.index(pick) - 1]
    reason = st.text_input("Reason for record", key="tm_erase_reason")
    first_ack = st.checkbox(
        "I understand erasure cannot be undone.", key="tm_erase_ack_1"
    )
    typed = st.text_input(
        f'Type tenant name "{selected.get("name")}" to confirm erasure',
        key="tm_erase_typed",
    )
    matches = (
        first_ack
        and typed.strip() == str(selected.get("name", "")).strip()
        and typed.strip() != ""
        and reason.strip() != ""
    )
    if st.button(
        "Erase tenant permanently",
        key="tm_erase_button",
        type="primary",
        disabled=not matches,
    ):
        with st.spinner("Erasing…"):
            code = _delete_tenant(str(selected["id"]), reason.strip())
        if code == 200:
            st.success("Tenant erased.")
            st.rerun()
        else:
            _surface(code)


def _render_view_metadata(tenants: list[dict[str, Any]]) -> None:
    if not tenants:
        return
    st.markdown("#### Tenant metadata")
    options = [f"{t.get('name', '?')} ({t.get('id')})" for t in tenants]
    pick = st.selectbox("Inspect tenant", options, key="tm_metadata_pick")
    selected = tenants[options.index(pick)]
    # Only metadata — never aggregate counts of content (FR-046).
    st.json(
        {
            "id": selected.get("id"),
            "name": selected.get("name"),
            "slug": selected.get("slug"),
            "status": selected.get("status"),
            "plan": selected.get("plan"),
            "created_at": selected.get("created_at"),
        }
    )


def render() -> None:
    tenants, placeholder = _fetch_tenants()
    if placeholder:
        render_placeholder_caption()

    _render_table(tenants)
    _render_view_metadata(tenants)
    _render_create_form()
    _render_suspend(tenants)
    _render_erase(tenants)
