# Owner: Amer
"""Tenant admin Streamlit UI.

Tenant admins manage CMS pages, widget settings, guardrails config, and leads here.
"""

import streamlit as st

st.set_page_config(page_title="Concierge Admin", layout="wide")

st.title("Concierge Admin")
st.write("Manage tenant CMS content, widget settings, guardrails, and leads.")

st.sidebar.header("Navigation")
page = st.sidebar.radio("Go to", ["CMS", "Widget", "Guardrails", "Leads"])

st.subheader(page)
st.info("Placeholder admin page. Connect this UI to the FastAPI backend.")
