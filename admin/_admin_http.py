# Owner: Amer
"""Shared HTTP-client helper for the admin Streamlit pages.

The client attaches `Authorization: Bearer <jwt>` from
`st.session_state["admin_token"]`. The streamlit_app gate guarantees we never
reach this code without a token; the helpers still tolerate a missing token
(request goes out unauthenticated; backend returns 403 and pages fall back
to their placeholder render — FR-013).

`TENANT_ID` is retained as a string constant ONLY because the per-page
`_SAMPLE_*` placeholder dicts reference it as display data. The real tenant
identification flows through the JWT in the Authorization header, and URL
building should use `signed_in_tenant_id()` to read the live session value.
"""

from __future__ import annotations

import os

import httpx
import streamlit as st

from admin.auth_state import get_actor_id, get_role, get_tenant_id, get_token

# Display placeholder for a missing scalar value when the backend is
# unreachable. Lives here (T100) so the 10 admin pages share one source of
# truth instead of redeclaring `_PLACEHOLDER = "—"` per file.
PLACEHOLDER = "—"

# Demo tenant id matching the InMemoryWidgetRepository fixture; used only in
# `_SAMPLE_*` placeholder dicts when the backend is unreachable.
TENANT_ID = "11111111-1111-1111-1111-111111111111"


def backend_url() -> str:
    return os.getenv("CONCIERGE_BACKEND_URL", "http://localhost:8000")


def http_client() -> httpx.Client:
    """Default admin HTTP client. Tests monkeypatch each page's `_http_client`.

    Attaches the admin JWT (Bearer) for routes that use `require_admin_session`,
    and also forwards the session identity as `X-Actor-Role` / `X-Actor-Id`
    headers so the legacy platform-actor routes (POST /tenants,
    POST /tenants/{id}/suspend, DELETE /tenants/{id}) used by the Tenant
    Manager dashboard work without a separate client. Routes that don't read
    those headers ignore them.
    """
    headers: dict[str, str] = {}
    token = get_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    role = get_role()
    if role:
        headers["X-Actor-Role"] = role
    actor_id = get_actor_id()
    if actor_id:
        headers["X-Actor-ID"] = actor_id
    return httpx.Client(base_url=backend_url(), headers=headers, timeout=10.0)


def render_placeholder_caption(detail: str | None = None) -> None:
    """Render the canonical "(placeholder)" caption.

    Per FR-013: when a fetch fails the page degrades to canned content with a
    visible "(placeholder)" caption — never a raw error. `detail` adds a hint
    for the operator (e.g. "one or more backend endpoints were unavailable").
    """
    text = "(placeholder)"
    if detail:
        text = f"(placeholder) — {detail}"
    st.caption(text)


def signed_in_tenant_id() -> str:
    """Return the signed-in admin's tenant id for URL building.

    Falls back to the placeholder `TENANT_ID` constant when there is no
    session — keeps backwards-compatible behavior for tests that hit the page
    rendering paths without going through login.
    """
    return get_tenant_id() or TENANT_ID
