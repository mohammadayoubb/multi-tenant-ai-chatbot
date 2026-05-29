# Owner: Amer
"""Test-only Streamlit entrypoint for admin/audit_page.render() in TA mode."""
from admin.audit_page import render

render(role="tenant_admin")
