# Owner: Amer
"""Tenant admin Streamlit UI."""

from __future__ import annotations

import httpx
import streamlit as st

from admin import cms_page, leads_page, tenant_page, usage_page, widget_page
from admin._admin_http import backend_url

st.set_page_config(page_title="Concierge Admin", layout="wide")


def _auth_request(path: str, payload: dict[str, str]) -> tuple[bool, str | dict[str, str]]:
    try:
        with httpx.Client(base_url=backend_url(), timeout=10.0) as client:
            response = client.post(path, json=payload)
    except httpx.HTTPError:
        return False, "The backend could not be reached."

    try:
        body = response.json()
    except ValueError:
        body = {}

    if response.status_code >= 400:
        detail = body.get("detail") if isinstance(body, dict) else None
        return False, detail or "Authentication request failed."

    if not isinstance(body, dict):
        return False, "Authentication response was malformed."
    return True, body


def _store_session(body: dict[str, str]) -> None:
    st.session_state["admin_access_token"] = body["access_token"]
    st.session_state["admin_actor_id"] = body["actor_id"]
    st.session_state["admin_tenant_id"] = body["tenant_id"]
    st.session_state["admin_tenant_name"] = body["tenant_name"]
    st.session_state["admin_widget_id"] = body["widget_id"]


def _clear_session() -> None:
    for key in (
        "admin_access_token",
        "admin_actor_id",
        "admin_tenant_id",
        "admin_tenant_name",
        "admin_widget_id",
    ):
        st.session_state.pop(key, None)


def _authenticated() -> bool:
    token = st.session_state.get("admin_access_token")
    return isinstance(token, str) and len(token.strip()) > 0


def _render_auth_gate() -> None:
    st.title("Concierge Admin")
    st.write("Create your tenant workspace or log back into an existing one.")

    signup_tab, login_tab = st.tabs(["Sign up", "Log in"])

    with signup_tab:
        with st.form("signup_form"):
            business_name = st.text_input("Business name", key="signup_business_name")
            email = st.text_input("Work email", key="signup_email")
            password = st.text_input(
                "Password",
                type="password",
                key="signup_password",
                help="Use at least 8 characters.",
            )
            confirm_password = st.text_input(
                "Confirm password",
                type="password",
                key="signup_password_confirm",
            )
            submitted = st.form_submit_button("Create workspace", type="primary")

        if submitted:
            if password != confirm_password:
                st.error("Passwords do not match.")
                return

            ok, result = _auth_request(
                "/auth/signup",
                {
                    "business_name": business_name,
                    "email": email,
                    "password": password,
                },
            )
            if not ok:
                st.error(str(result))
                return

            assert isinstance(result, dict)
            _store_session(result)
            st.success("Workspace created.")
            st.rerun()

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Log in", type="primary")

        if submitted:
            ok, result = _auth_request(
                "/auth/login",
                {
                    "email": email,
                    "password": password,
                },
            )
            if not ok:
                st.error(str(result))
                return

            assert isinstance(result, dict)
            _store_session(result)
            st.success("Logged in.")
            st.rerun()


if not _authenticated():
    _render_auth_gate()
    st.stop()

st.title("Concierge Admin")
st.write("Manage tenant CMS content, widget settings, guardrails, and leads.")

st.sidebar.header("Account")
st.sidebar.write(st.session_state.get("admin_tenant_name", "Unknown tenant"))
st.sidebar.caption(st.session_state.get("admin_actor_id", ""))
st.sidebar.text(f"Widget ID: {st.session_state.get('admin_widget_id', '')}")
if st.sidebar.button("Log out"):
    _clear_session()
    st.rerun()

st.sidebar.header("Navigation")
page = st.sidebar.radio(
    "Go to",
    ["Tenant", "CMS", "Leads", "Usage", "Widget", "Guardrails"],
)

st.subheader(page)
if page == "Tenant":
    tenant_page.render()
elif page == "CMS":
    cms_page.render()
elif page == "Leads":
    leads_page.render()
elif page == "Usage":
    usage_page.render()
elif page == "Widget":
    widget_page.render()
else:
    st.info("Guardrails UI is not wired yet. The platform guardrails service is running in the backend.")
