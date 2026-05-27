# Owner: Amer
"""Tenant admin Streamlit UI.

Tenant admins manage CMS pages, widget settings, guardrails config, and leads here.
"""

import streamlit as st

from admin import cms_page, leads_page, tenant_page, usage_page, widget_page

st.set_page_config(page_title="Concierge Admin", layout="wide")

st.title("Concierge Admin")
st.write("Manage tenant CMS content, widget settings, guardrails, and leads.")

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
    st.info("Placeholder admin page. Connect this UI to the FastAPI backend.")
