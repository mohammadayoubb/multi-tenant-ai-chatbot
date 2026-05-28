# Owner: Amer
"""Concierge AI admin login screen.

Posts {email, password} to POST /admin/login. On success, persists the JWT
plus the trusted (server-issued) role / tenant_id / actor_id into
st.session_state via auth_state.set_session. Role-based redirect happens in
streamlit_app.py based on the server-issued role — the user never picks one.

Security:
  - Server response body is the ONLY source of role/tenant_id/actor_id.
  - All login failure causes (unknown email, wrong password, suspended user,
    unknown role) collapse to one safe error message.
  - Backend transport errors never expose the underlying exception text.
"""

from __future__ import annotations

import os

import httpx
import streamlit as st

from admin import brand
from admin.auth_state import set_session

_GENERIC_LOGIN_ERROR = "Invalid email or password."


def _backend_url() -> str:
    return os.getenv("CONCIERGE_BACKEND_URL", "http://localhost:8000")


def _post_login(email: str, password: str) -> tuple[bool, str | None]:
    """Return (success, safe_error_message). Never echoes server text."""
    try:
        with httpx.Client(base_url=_backend_url(), timeout=10.0) as client:
            resp = client.post(
                "/admin/login", json={"email": email, "password": password}
            )
    except httpx.HTTPError:
        return False, "We can't reach the server right now. Please try again."

    if resp.status_code == 200:
        try:
            body = resp.json()
        except ValueError:
            return False, "Login failed. Please try again."
        set_session(body)
        return True, None

    if resp.status_code in (400, 401):
        return False, _GENERIC_LOGIN_ERROR
    # 5xx / unexpected — fail safe, do NOT leak the body
    return False, "Login failed. Please try again."


def render() -> None:
    brand.render_card_chrome()

    with st.form("admin_login_form", clear_on_submit=False):
        st.markdown("#### Sign in")
        email = st.text_input(
            "Email",
            key="login_email_input",
            autocomplete="email",
        )
        password = st.text_input(
            "Password",
            type="password",
            key="login_password_input",
            autocomplete="current-password",
        )
        submitted = st.form_submit_button("Login", type="primary", width="stretch")

    if submitted:
        if not email or not password:
            st.error("Please enter your email and password.")
            return
        with st.spinner("Signing in…"):
            success, error = _post_login(email.strip().lower(), password)
        if success:
            st.rerun()
        else:
            st.error(error or _GENERIC_LOGIN_ERROR)

    st.markdown(
        '<div class="concierge-footer">'
        'Have an invite? <a href="?page=accept-invite" target="_self">'
        "Accept invite</a>"
        "</div>",
        unsafe_allow_html=True,
    )
