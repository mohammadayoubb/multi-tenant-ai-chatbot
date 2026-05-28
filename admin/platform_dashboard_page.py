# Owner: Amer
"""Platform dashboard for `tenant_manager` role.

Minimal placeholder: the platform-wide tenant list, suspend / erase controls,
and cross-tenant audit log roll-up are out of scope for the auth feature and
will land with the platform-level CRUD endpoints (Hiba). This screen exists so
the role-based redirect from login has a real destination.

It also exposes the "Invite an admin" form, which IS in scope: it lets a
tenant_manager mint an invite token for a new tenant_admin or another
tenant_manager. The form deliberately does not let the user choose a
tenant_id — the inviter's tenant context flows through the JWT.
"""

from __future__ import annotations

import streamlit as st

from admin._admin_http import http_client
from admin.auth_state import get_actor_id, get_tenant_id

_ROLE_OPTIONS = ["tenant_admin", "tenant_manager"]
_TTL_OPTIONS = {
    "24 hours": 24 * 3600,
    "7 days": 7 * 24 * 3600,
    "30 days": 30 * 24 * 3600,
}


def _invite_link(token: str) -> str:
    """Build a click-to-copy acceptance URL.

    The host is intentionally left relative — Streamlit doesn't know its own
    public URL. In production you'd template this against the admin app's
    domain; for now we surface the path the inviter can paste.
    """
    return f"/?page=accept-invite&token={token}"


def _create_invite(email: str, role: str, ttl_seconds: int) -> tuple[bool, dict | str]:
    try:
        with http_client() as client:
            resp = client.post(
                "/admin/invites",
                json={
                    "email": email,
                    "role": role,
                    "ttl_seconds": ttl_seconds,
                },
            )
    except Exception:
        return False, "Could not reach the server. Try again."
    if resp.status_code == 200:
        try:
            return True, resp.json()
        except ValueError:
            return False, "Server returned an unexpected response."
    if resp.status_code == 403:
        return False, "You do not have permission to invite users."
    if resp.status_code == 400:
        return False, "Please enter a valid email."
    return False, "Failed to create invite. Try again."


def render() -> None:
    st.title("Platform overview")
    st.write(
        f"Signed in as **{get_actor_id() or '—'}** (tenant_manager). "
        "Tenant scope: "
        f"`{get_tenant_id() or '—'}`."
    )
    st.info(
        "Platform-wide tenant listings, suspend / erase controls, and "
        "cross-tenant audit will land alongside the platform CRUD endpoints. "
        "Invite management is available below."
    )

    st.markdown("### Invite an admin")
    with st.form("invite_admin_form", clear_on_submit=True):
        email = st.text_input("Invitee email", key="invite_email_input")
        role = st.selectbox("Role", _ROLE_OPTIONS, key="invite_role_input")
        ttl_label = st.selectbox(
            "Invite valid for", list(_TTL_OPTIONS.keys()), key="invite_ttl_input"
        )
        submitted = st.form_submit_button("Create invite", type="primary")

    if submitted:
        if not email.strip():
            st.error("Please enter an invitee email.")
            return
        with st.spinner("Creating invite…"):
            ok, payload = _create_invite(
                email.strip().lower(), role, _TTL_OPTIONS[ttl_label]
            )
        if not ok:
            st.error(payload if isinstance(payload, str) else "Failed to create invite.")
            return
        assert isinstance(payload, dict)
        link = _invite_link(payload["token"])
        st.success("Invite created. Share this link with the invitee:")
        st.code(link)
        st.caption(f"Expires: {payload['expires_at']}")
