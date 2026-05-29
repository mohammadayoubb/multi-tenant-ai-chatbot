# Owner: Amer
"""Tenant Admin dashboard dispatcher (Spec 009 US2, T069).

The TA workspace exposes one tab per tenant-scoped surface. This module is
the single sidebar router for the tenant_admin role: it owns the navigation
chrome (signed-in identity, tenant id, sign-out) and dispatches into the
per-tab render functions.

Every tab module is independent and stateless across reruns; the dispatcher
keeps no business logic of its own.
"""

from __future__ import annotations

import streamlit as st

from admin import (
    agent_settings_page,
    audit_page,
    auth_state,
    cms_page,
    escalations_page,
    guardrails_page,
    leads_page,
    overview_page,
    usage_page,
    widget_page,
)

_TABS = [
    "Overview",
    "CMS",
    "Agent",
    "Guardrails",
    "Widget",
    "Leads",
    "Escalations",
    "Usage",
    "Audit",
]


def _render_sidebar() -> str:
    st.sidebar.header("Signed in")
    st.sidebar.write(auth_state.get_full_name() or auth_state.get_actor_id() or "(unknown)")
    st.sidebar.caption(f"Tenant: {auth_state.get_tenant_id() or '—'}")
    if st.sidebar.button("Sign out", key="ta_logout_button"):
        auth_state.clear_session()
        st.rerun()

    st.sidebar.header("Navigation")
    return st.sidebar.radio("Go to", _TABS, key="ta_nav_radio")


def render() -> None:
    """Render the tenant_admin dashboard with the selected tab."""
    selection = _render_sidebar()
    st.title(selection)

    if selection == "Overview":
        overview_page.render()
    elif selection == "CMS":
        cms_page.render()
    elif selection == "Agent":
        agent_settings_page.render()
    elif selection == "Guardrails":
        guardrails_page.render()
    elif selection == "Widget":
        widget_page.render()
    elif selection == "Leads":
        leads_page.render()
    elif selection == "Escalations":
        escalations_page.render()
    elif selection == "Usage":
        usage_page.render()
    elif selection == "Audit":
        audit_page.render(role="tenant_admin")
