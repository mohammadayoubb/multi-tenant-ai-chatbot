# Owner: Amer
"""Shared HTTP-client helper for the admin Streamlit pages.

Extracted under research Decision 8: identical `_DEV_HEADERS` and
`_http_client()` definitions appeared in admin/tenant_page.py,
admin/cms_page.py, admin/leads_page.py, and admin/usage_page.py — four files,
above the ">2 pages" duplication threshold.

Tests monkeypatch `_http_client` on the calling page module, so each page
still re-imports the helper at module load and exposes a local `_http_client`
attribute the tests target.
"""

from __future__ import annotations

import os

import httpx
import streamlit as st

# TODO(hiba-handoff): once real admin auth lands, drop the dev headers and pull
# tenant_id / actor_id from the authenticated admin session.
DEV_HEADERS = {
    "X-Concierge-Role": "tenant_admin",
    "X-Concierge-Tenant-Id": "11111111-1111-1111-1111-111111111111",
    "X-Concierge-Actor-Id": "admin@example.com",
}

TENANT_ID = DEV_HEADERS["X-Concierge-Tenant-Id"]


def backend_url() -> str:
    return os.getenv("CONCIERGE_BACKEND_URL", "http://localhost:8000")


def auth_headers() -> dict[str, str]:
    """Return bearer auth for the signed admin session when available."""
    token = st.session_state.get("admin_access_token")
    if isinstance(token, str) and token.strip():
        return {"Authorization": f"Bearer {token.strip()}"}
    return DEV_HEADERS


def tenant_id() -> str:
    """Return the current tenant id from the signed admin session when available."""
    current_tenant_id = st.session_state.get("admin_tenant_id")
    if isinstance(current_tenant_id, str) and current_tenant_id.strip():
        return current_tenant_id.strip()
    return TENANT_ID


def http_client() -> httpx.Client:
    """Default admin HTTP client. Tests monkeypatch each page's `_http_client`."""
    return httpx.Client(base_url=backend_url(), headers=auth_headers(), timeout=10.0)
