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


def http_client() -> httpx.Client:
    """Default admin HTTP client. Tests monkeypatch each page's `_http_client`."""
    return httpx.Client(base_url=backend_url(), headers=DEV_HEADERS, timeout=10.0)
