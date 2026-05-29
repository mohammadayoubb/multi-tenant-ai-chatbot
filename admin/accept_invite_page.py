# Owner: Amer
"""Concierge AI invite acceptance screen.

URL: /?page=accept-invite&token=<uuid>

Flow:
  1. Read token from query params.
  2. GET /admin/invites/{token} -> safe metadata (email, role, tenant_name,
     status). The visitor cannot type the email, tenant, or role themselves.
  3. If status is pending, render the registration form (full name + password
     + confirm password). Otherwise render an "expired" / "used" / "invalid"
     screen with a Back-to-Login button.
  4. POST /admin/invites/{token}/accept with {full_name, password,
     confirm_password}. On success, immediately POST /admin/login with the
     invite email + new password to mint a JWT, persist session, and rerun so
     the streamlit_app gate redirects to the role-correct dashboard.

Security:
  - Email, role, tenant are display-only and come from the server.
  - No raw backend error bodies are surfaced.
  - Empty / invalid / expired / used tokens land on a clean explainer screen.
"""

from __future__ import annotations

import os

import httpx
import streamlit as st

from admin import brand
from admin.auth_state import set_session

_GENERIC_INVITE_ERROR = (
    "This invite link is no longer valid. Please ask for a fresh invite."
)


def _backend_url() -> str:
    return os.getenv("CONCIERGE_BACKEND_URL", "http://localhost:8000")


def _fetch_invite(token: str) -> tuple[dict | None, str | None]:
    try:
        with httpx.Client(base_url=_backend_url(), timeout=10.0) as client:
            resp = client.get(f"/admin/invites/{token}")
    except httpx.HTTPError:
        return None, "We can't reach the server right now. Please try again."
    if resp.status_code == 200:
        try:
            return resp.json(), None
        except ValueError:
            return None, _GENERIC_INVITE_ERROR
    if resp.status_code == 404:
        return None, _GENERIC_INVITE_ERROR
    return None, _GENERIC_INVITE_ERROR


def _post_accept(
    token: str, full_name: str, password: str, confirm: str
) -> tuple[bool, str | None]:
    try:
        with httpx.Client(base_url=_backend_url(), timeout=10.0) as client:
            resp = client.post(
                f"/admin/invites/{token}/accept",
                json={
                    "full_name": full_name,
                    "password": password,
                    "confirm_password": confirm,
                },
            )
    except httpx.HTTPError:
        return False, "We can't reach the server right now. Please try again."
    if resp.status_code == 200:
        return True, None
    if resp.status_code == 422:
        try:
            body = resp.json()
        except ValueError:
            return False, "Please choose a stronger password."
        message = body.get("message") if isinstance(body, dict) else None
        return False, message or "Please choose a stronger password."
    if resp.status_code == 400:
        return False, _GENERIC_INVITE_ERROR
    return False, "Something went wrong. Please try again."


def _post_login(email: str, password: str) -> bool:
    """After acceptance, sign the user in immediately and store the JWT."""
    try:
        with httpx.Client(base_url=_backend_url(), timeout=10.0) as client:
            resp = client.post(
                "/admin/login", json={"email": email, "password": password}
            )
    except httpx.HTTPError:
        return False
    if resp.status_code != 200:
        return False
    try:
        body = resp.json()
    except ValueError:
        return False
    set_session(body)
    return True


def _back_to_login_link() -> None:
    st.markdown(
        '<div class="concierge-footer">'
        '<a href="?" target="_self">Back to login</a>'
        "</div>",
        unsafe_allow_html=True,
    )


def _render_status_screen(status: str) -> None:
    if status == "used":
        st.warning("This invite has already been used.")
    elif status == "expired":
        st.warning("This invite has expired.")
    elif status == "revoked":
        st.warning("This invite has been revoked. Please ask your admin for a new one.")
    else:
        # Unknown / null status — collapse to the generic copy so the
        # backend can't enumerate which states exist via UI text.
        st.error(_GENERIC_INVITE_ERROR)
    _back_to_login_link()


def render() -> None:
    brand.render_card_chrome()
    token = st.query_params.get("token", "").strip()

    if not token:
        st.error(_GENERIC_INVITE_ERROR)
        _back_to_login_link()
        return

    with st.spinner("Loading invite…"):
        invite, error = _fetch_invite(token)

    if invite is None:
        st.error(error or _GENERIC_INVITE_ERROR)
        _back_to_login_link()
        return

    status = invite.get("status")
    if status != "pending":
        _render_status_screen(status or "invalid")
        return

    st.markdown("#### Accept your invite")
    st.write(
        f"You've been invited to **{invite['tenant_name']}** as "
        f"`{invite['role']}`."
    )
    st.caption(f"Invite email: {invite['email']}")

    with st.form("accept_invite_form", clear_on_submit=False):
        full_name = st.text_input("Full name", key="accept_full_name_input")
        password = st.text_input(
            "Password",
            type="password",
            key="accept_password_input",
            autocomplete="new-password",
            help="At least 8 characters; include a letter and a digit.",
        )
        confirm = st.text_input(
            "Confirm password",
            type="password",
            key="accept_confirm_input",
            autocomplete="new-password",
        )
        submitted = st.form_submit_button(
            "Accept invite", type="primary", width="stretch"
        )

    if submitted:
        if not full_name.strip():
            st.error("Please enter your full name.")
            return
        if len(password) < 8:
            st.error("Password must be at least 8 characters.")
            return
        if password != confirm:
            st.error("Passwords do not match.")
            return

        with st.spinner("Creating your account…"):
            success, error = _post_accept(token, full_name.strip(), password, confirm)
        if not success:
            st.error(error or "Something went wrong. Please try again.")
            return

        with st.spinner("Signing you in…"):
            signed_in = _post_login(invite["email"], password)
        if not signed_in:
            st.success(
                "Account created. Please sign in with your new credentials."
            )
            _back_to_login_link()
            return

        # Drop the page+token query params so the next render hits the
        # role-based dashboard cleanly.
        st.query_params.clear()
        st.rerun()

    _back_to_login_link()
