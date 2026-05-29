# Owner: Amer
"""Concierge AI admin app entrypoint.

Dispatch order (re-evaluated on every Streamlit rerun):

  1. If query-param page=accept-invite -> accept_invite_page (public).
  2. Else if not authenticated -> login_page (public).
  3. Else dispatch by JWT role (server-issued; the user never picks it):
       tenant_manager  -> TM tabs (Overview, Tenants, Invites, Usage & Cost,
                          Audit Logs, Settings) — Spec 009 US3 T090.
       tenant_admin    -> tenant_dashboard.render() (Spec 009 US2 tabs)
       anything else   -> access_denied_page
  4. The "Sign out" button clears st.session_state and reruns -> step 2.
"""

import streamlit as st

from admin import (
    access_denied_page,
    accept_invite_page,
    audit_page,
    auth_state,
    invites_page,
    login_page,
    platform_dashboard_page,
    settings_page,
    tenant_dashboard,
    tenants_page,
    usage_page,
)

st.set_page_config(page_title="Concierge AI Admin", layout="wide")


_TM_TABS = [
    "Overview",
    "Tenants",
    "Invites",
    "Usage & Cost",
    "Audit Logs",
    "Settings",
]


def _render_tm_sidebar() -> str:
    st.sidebar.header("Signed in")
    st.sidebar.write(auth_state.get_full_name() or auth_state.get_actor_id() or "(unknown)")
    st.sidebar.caption("Role: tenant_manager")
    if st.sidebar.button("Sign out", key="platform_logout_button"):
        auth_state.clear_session()
        st.rerun()

    st.sidebar.header("Navigation")
    return st.sidebar.radio("Go to", _TM_TABS, key="tm_nav_radio")


def _render_platform_dashboard() -> None:
    selection = _render_tm_sidebar()
    st.title(selection)

    if selection == "Overview":
        platform_dashboard_page.render()
    elif selection == "Tenants":
        tenants_page.render()
    elif selection == "Invites":
        invites_page.render()
    elif selection == "Usage & Cost":
        usage_page.render(role="tenant_manager")
    elif selection == "Audit Logs":
        audit_page.render(role="tenant_manager")
    elif selection == "Settings":
        settings_page.render()


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
    tenant_dashboard.render()
else:
    access_denied_page.render()
