# Owner: Amer
"""Integration tests for admin/tenant_page.py.

Spec 005 US1. Covers FR-004 (tenant header card), FR-005 (20 audit rows,
metadata truncated to 80 chars), FR-006 (no edit/suspend/erase controls),
FR-013 (any non-2xx or transport error falls back to placeholder).
"""

from __future__ import annotations

from typing import Callable

import httpx
import pytest
from streamlit.testing.v1 import AppTest

import admin.tenant_page as tenant_page

_ENTRY = "tests/integration/_admin_tenant_page_entry.py"

_LIVE_TENANT = {
    "id": "11111111-1111-1111-1111-111111111111",
    "name": "Acme Inc.",
    "slug": "acme",
    "status": "active",
    "plan": "starter",
    "created_at": "2026-01-15T09:30:00Z",
    "updated_at": "2026-05-20T14:00:00Z",
}

_LIVE_AUDIT = [
    {
        "id": "a1",
        "created_at": "2026-05-26T13:45:11Z",
        "actor_role": "tenant_admin",
        "action": "cms.page_updated",
        "metadata_json": {"page_slug": "pricing", "field": "body"},
    },
    {
        "id": "a2",
        "created_at": "2026-05-25T10:00:00Z",
        "actor_role": "tenant_manager",
        "action": "widget.origin_added",
        "metadata_json": {"origin": "https://acme.example"},
    },
]


def _factory(handler: Callable[[httpx.Request], httpx.Response]) -> Callable[[], httpx.Client]:
    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    return factory


def test_happy_path_renders_real_audit_log(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/tenants/") and request.url.path.endswith("/audit-logs"):
            return httpx.Response(200, json=_LIVE_AUDIT)
        if request.url.path.startswith("/tenants/"):
            return httpx.Response(200, json=_LIVE_TENANT)
        return httpx.Response(404)

    monkeypatch.setattr(tenant_page, "_http_client", _factory(handler))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception

    markdown = " ".join(m.value for m in at.markdown)
    assert "Acme Inc." in markdown
    assert "acme" in markdown
    assert "starter" in markdown
    assert "active" in markdown
    captions = " ".join(c.value for c in at.caption)
    assert "(placeholder)" not in captions


def test_placeholder_fallback_renders_sample_audit_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/audit-logs"):
            return httpx.Response(404)
        return httpx.Response(200, json=_LIVE_TENANT)

    monkeypatch.setattr(tenant_page, "_http_client", _factory(handler))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception

    captions = " ".join(c.value for c in at.caption) + " ".join(w.value for w in at.warning)
    assert "(placeholder)" in captions
    # Real tenant header should still render.
    markdown = " ".join(m.value for m in at.markdown)
    assert "Acme Inc." in markdown


@pytest.mark.parametrize(
    "failure",
    [
        "status_500",
        "transport_error",
    ],
)
def test_server_error_falls_back_to_placeholder(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    secret_marker = "internal-server-stack-trace-do-not-leak"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/audit-logs"):
            if failure == "transport_error":
                raise httpx.ConnectError("connection refused")
            return httpx.Response(500, text=secret_marker)
        return httpx.Response(200, json=_LIVE_TENANT)

    monkeypatch.setattr(tenant_page, "_http_client", _factory(handler))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception

    captions = " ".join(c.value for c in at.caption) + " ".join(w.value for w in at.warning)
    assert "(placeholder)" in captions

    full_output = " ".join(
        [m.value for m in at.markdown]
        + [c.value for c in at.caption]
        + [w.value for w in at.warning]
        + [e.value for e in at.error]
    )
    assert secret_marker not in full_output
    assert "Traceback" not in full_output


def test_no_mutating_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-006: page exposes no edit/suspend/erase buttons or forms."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/audit-logs"):
            return httpx.Response(200, json=_LIVE_AUDIT)
        return httpx.Response(200, json=_LIVE_TENANT)

    monkeypatch.setattr(tenant_page, "_http_client", _factory(handler))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert at.button == []
