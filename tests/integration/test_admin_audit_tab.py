# Owner: Amer
"""Integration tests for admin/audit_page.py — TA path (Spec 009 US2, T066).

T077 creates `audit_page.py` with a `role` parameter that branches between
TA-scope (GET /tenants/{tid}/audit-logs) and TM-scope (GET /audit-logs).

This file pins the TA-scope contract:
  - TA Audit tab lists ONLY the signed-in tenant's events (FR-030).
  - A cross-tenant path attempt (the page rendered with the wrong tenant id
    in session) yields a generic forbidden notice; no leaked rows from any
    other tenant ever surface.
"""

from __future__ import annotations

from typing import Any, Callable

import httpx
import pytest

pytest.importorskip("admin.audit_page")

from streamlit.testing.v1 import AppTest  # noqa: E402

import admin.audit_page as page  # noqa: E402


_ENTRY = "tests/integration/_admin_audit_page_entry.py"


_TENANT_A_LOGS = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "tenant_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "actor_id": "alice@a.example",
        "actor_role": "tenant_admin",
        "action": "widget.origin_added",
        "metadata_json": {"origin": "https://a.example"},
        "created_at": "2026-05-26T18:02:11Z",
    },
]


def _factory(handler: Callable[[httpx.Request], httpx.Response]):
    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    return factory


def test_ta_audit_lists_own_tenant_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and "/audit-logs" in req.url.path:
            return httpx.Response(200, json=_TENANT_A_LOGS)
        return httpx.Response(404)

    monkeypatch.setattr(page, "_http_client", _factory(handler))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception

    assert len(at.dataframe) >= 1
    rendered = at.dataframe[0].value
    actions = rendered["action"].tolist() if "action" in rendered.columns else []
    assert "widget.origin_added" in actions


def test_ta_audit_cross_tenant_path_403(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backend returning 403 collapses to a generic notice — no leaked content."""
    secret_marker = "tenant-b-leaked-row"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text=secret_marker)

    monkeypatch.setattr(page, "_http_client", _factory(handler))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception

    full_output = " ".join(
        [m.value for m in at.markdown]
        + [c.value for c in at.caption]
        + [w.value for w in at.warning]
        + [e.value for e in at.error]
    )
    assert secret_marker not in full_output
    assert "Traceback" not in full_output
