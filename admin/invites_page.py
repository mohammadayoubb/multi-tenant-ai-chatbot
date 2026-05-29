# Owner: Amer
"""TM Invites admin page (Spec 009 US3, T086).

Three sub-surfaces on one page:

  1. Issue a new invite (was historically rendered on the platform dashboard;
     moved here so the platform dashboard can focus on KPIs).
  2. A table of recently-issued invites cached in ``st.session_state`` so the
     operator can see what they just minted. A real ``GET /admin/invites``
     platform-wide list endpoint is not yet on the contract; until it ships,
     this page surfaces a "(endpoint pending)" caption and works with the
     session-cached rows alone.
  3. Revoke / resend by token — calls ``POST /admin/invites/{token}/revoke``
     (T037) and ``POST /admin/invites/{token}/resend`` (T037). The placeholder
     fallback case is consistent with the rest of the admin: any failure
     collapses to a generic "(failed)" message; no raw server text is shown.
"""

from __future__ import annotations

from typing import Any

import httpx
import streamlit as st

from admin._admin_http import http_client as _http_client
from admin._empty import render_empty_state
from admin._status_pill import render_status
from admin._table import render_table

_ROLE_OPTIONS = ["tenant_admin", "tenant_manager"]
_TTL_OPTIONS = {
    "24 hours": 24 * 3600,
    "7 days": 7 * 24 * 3600,
    "30 days": 30 * 24 * 3600,
}

_SESSION_KEY = "tm_recent_invites"

_GENERIC_FAILED = "The request failed; please retry."
_GENERIC_FORBIDDEN = "Forbidden — your role cannot perform that action."
_GENERIC_CONFLICT = "Invite is already used or already revoked."
_GENERIC_NOT_FOUND = "No invite found for that token."


def _recent() -> list[dict[str, Any]]:
    return st.session_state.get(_SESSION_KEY, [])


def _remember(invite: dict[str, Any]) -> None:
    rows = list(_recent())
    rows.insert(0, invite)
    st.session_state[_SESSION_KEY] = rows[:25]


def _mark(token: str, *, status: str) -> None:
    rows = list(_recent())
    for row in rows:
        if str(row.get("token")) == token:
            row["status"] = status
    st.session_state[_SESSION_KEY] = rows


def _replace_token(old_token: str, new_row: dict[str, Any]) -> None:
    rows = [r for r in _recent() if str(r.get("token")) != old_token]
    rows.insert(0, new_row)
    st.session_state[_SESSION_KEY] = rows[:25]


def _post_create_invite(email: str, role: str, ttl_seconds: int) -> tuple[int, Any]:
    try:
        with _http_client() as client:
            resp = client.post(
                "/admin/invites",
                json={"email": email, "role": role, "ttl_seconds": ttl_seconds},
            )
    except httpx.HTTPError:
        return 0, None
    try:
        body = resp.json()
    except ValueError:
        body = None
    return resp.status_code, body


def _post_revoke(token: str) -> tuple[int, Any]:
    try:
        with _http_client() as client:
            resp = client.post(f"/admin/invites/{token}/revoke")
    except httpx.HTTPError:
        return 0, None
    try:
        body = resp.json()
    except ValueError:
        body = None
    return resp.status_code, body


def _post_resend(token: str) -> tuple[int, Any]:
    try:
        with _http_client() as client:
            resp = client.post(f"/admin/invites/{token}/resend")
    except httpx.HTTPError:
        return 0, None
    try:
        body = resp.json()
    except ValueError:
        body = None
    return resp.status_code, body


def _surface(status_code: int) -> None:
    if status_code == 403:
        st.error(_GENERIC_FORBIDDEN)
    elif status_code == 404:
        st.error(_GENERIC_NOT_FOUND)
    elif status_code == 409:
        st.error(_GENERIC_CONFLICT)
    else:
        st.error(_GENERIC_FAILED)


def _render_recent() -> None:
    st.markdown("#### Recently issued invites")
    st.caption(
        "(endpoint pending) — a platform-wide list endpoint is not yet on the "
        "contract. The rows below are the invites issued from THIS session."
    )
    rows = _recent()
    if not rows:
        render_empty_state(
            "No invites issued in this session yet",
            "Use the form below to mint a new invite.",
        )
        return
    table = [
        {
            "email": r.get("email", "—"),
            "role": r.get("role", "—"),
            "tenant_id": r.get("tenant_id", "—"),
            "expires_at": r.get("expires_at", "—"),
            "status": r.get("status", "pending"),
            "token": r.get("token", "—"),
        }
        for r in rows
    ]
    render_table(
        table,
        columns=["email", "role", "tenant_id", "expires_at", "status", "token"],
        empty_state={
            "title": "No invites yet",
            "message": "Use the form below to mint a new invite.",
        },
        key="tm_invites_table",
    )
    for row in rows:
        cols = st.columns([3, 2])
        with cols[0]:
            st.write(f"{row.get('email')} → {row.get('role')}")
        with cols[1]:
            render_status(str(row.get("status", "pending")), kind="invite")


def _render_issue_form() -> None:
    st.markdown("#### Issue a new invite")
    with st.form("tm_invite_form", clear_on_submit=True):
        email = st.text_input("Invitee email", key="tm_invite_email")
        role = st.selectbox("Role", _ROLE_OPTIONS, key="tm_invite_role")
        ttl_label = st.selectbox(
            "Invite valid for", list(_TTL_OPTIONS.keys()), key="tm_invite_ttl"
        )
        submitted = st.form_submit_button("Create invite", type="primary")
    if not submitted:
        return
    email_clean = email.strip().lower()
    if not email_clean:
        st.error("Invitee email is required.")
        return
    with st.spinner("Creating invite…"):
        status_code, body = _post_create_invite(
            email_clean, role, _TTL_OPTIONS[ttl_label]
        )
    if status_code == 200 and isinstance(body, dict):
        _remember(
            {
                "token": str(body.get("token")),
                "email": body.get("email", email_clean),
                "role": body.get("role", role),
                "tenant_id": str(body.get("tenant_id", "—")),
                "expires_at": body.get("expires_at", "—"),
                "status": "pending",
            }
        )
        link = f"/?page=accept-invite&token={body.get('token')}"
        st.success("Invite created. Share this link with the invitee:")
        st.code(link)
    else:
        _surface(status_code)


def _render_revoke_resend() -> None:
    st.markdown("#### Revoke or resend an invite")
    token = st.text_input("Invite token", key="tm_invite_action_token")
    cols = st.columns(2)
    with cols[0]:
        if st.button(
            "Revoke",
            key="tm_invite_revoke_button",
            disabled=not token.strip(),
        ):
            with st.spinner("Revoking…"):
                status_code, _ = _post_revoke(token.strip())
            if status_code == 200:
                _mark(token.strip(), status="revoked")
                st.success("Invite revoked.")
                st.rerun()
            else:
                _surface(status_code)
    with cols[1]:
        if st.button(
            "Resend",
            key="tm_invite_resend_button",
            disabled=not token.strip(),
        ):
            with st.spinner("Resending…"):
                status_code, body = _post_resend(token.strip())
            if status_code == 200 and isinstance(body, dict):
                _replace_token(
                    token.strip(),
                    {
                        "token": str(body.get("token")),
                        "email": body.get("email", "—"),
                        "role": body.get("role", "—"),
                        "tenant_id": str(body.get("tenant_id", "—")),
                        "expires_at": body.get("expires_at", "—"),
                        "status": "pending",
                    },
                )
                st.success("Invite resent — new token issued.")
                st.rerun()
            else:
                _surface(status_code)


def render() -> None:
    _render_recent()
    _render_issue_form()
    _render_revoke_resend()
