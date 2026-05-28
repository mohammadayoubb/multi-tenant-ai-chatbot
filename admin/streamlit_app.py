# Owner: Amer
"""Concierge AI admin app entrypoint.

Dispatch order (re-evaluated on every Streamlit rerun):

  1. If query-param page=accept-invite -> accept_invite_page (public).
  2. Else if not authenticated -> login_page (public).
  3. Else dispatch by JWT role (server-issued; the user never picks it):
       tenant_manager  -> platform_dashboard_page
       tenant_admin    -> tenant dashboard (existing CMS / Leads / Usage /
                          Widget / Tenant pages)
       anything else   -> access_denied_page
  4. The "Sign out" button clears st.session_state and reruns -> step 2.
"""

import streamlit as st

from admin import (
    access_denied_page,
    accept_invite_page,
    auth_state,
    cms_page,
    leads_page,
    login_page,
    platform_dashboard_page,
    tenant_page,
    usage_page,
    widget_page,
)

st.set_page_config(page_title="Concierge AI Admin", layout="wide")


def _render_tenant_dashboard() -> None:
    """The existing tenant-admin pages, wrapped behind the sidebar nav."""
    st.title("Tenant dashboard")

    st.sidebar.header("Signed in")
    st.sidebar.write(auth_state.get_full_name() or auth_state.get_actor_id() or "(unknown)")
    st.sidebar.caption(f"Tenant: {auth_state.get_tenant_id() or '—'}")
    if st.sidebar.button("Sign out", key="tenant_logout_button"):
        auth_state.clear_session()
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
        st.info(
            "Placeholder admin page. Connect this UI to the FastAPI backend."
        )


def _render_platform_dashboard() -> None:
    st.sidebar.header("Signed in")
    st.sidebar.write(auth_state.get_full_name() or auth_state.get_actor_id() or "(unknown)")
    st.sidebar.caption("Role: tenant_manager")
    if st.sidebar.button("Sign out", key="platform_logout_button"):
        auth_state.clear_session()
        st.rerun()
    platform_dashboard_page.render()


# --- dispatch ---------------------------------------------------------------

_page_param = st.query_params.get("page")

if _page_param == "accept-invite":
    accept_invite_page.render()
    st.stop()

if not auth_state.is_authenticated():
    login_page.render()
    st.stop()

_role = auth_state.get_role()
if _role == "tenant_manager":
    _render_platform_dashboard()
elif _role == "tenant_admin":
    _render_tenant_dashboard()
else:
    access_denied_page.render()
