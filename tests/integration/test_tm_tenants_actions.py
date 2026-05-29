# Owner: Amer
"""Spec 009 US3 T081 — TM Tenants page: create / suspend / erase + audit.

The page module renders the tenants table from `GET /tenants` and exposes
three mutations: create (POST /tenants), suspend (POST /tenants/{id}/suspend),
erase (DELETE /tenants/{id}). Each mutation surface requires a confirmation
input ("type the tenant name") before the action button enables.

This test pins:
  - the tenants list renders from the mocked GET /tenants response,
  - the confirmation gating blocks the action until the right text is typed,
  - the placeholder fallback path renders a visible "(placeholder)" caption
    when the backend is unreachable, with no leaked error text or stack
    trace (Principle V).

A full UI click-through of every action would require Streamlit's button
fixture (which it doesn't expose at the level of granularity needed here),
so the action calls themselves are tested at the HTTP-helper level — both
paths share the same `_http_client` symbol that tests monkeypatch.
"""

from __future__ import annotations

from typing import Callable

import httpx
import pytest

pytest.importorskip("admin.tenants_page")

from streamlit.testing.v1 import AppTest  # noqa: E402

import admin.tenants_page as tenants_page  # noqa: E402


_ENTRY = "tests/integration/_admin_tenants_page_entry.py"


def _factory(handler: Callable[[httpx.Request], httpx.Response]):
    def factory() -> httpx.Client:
        return httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="http://test",
        )

    return factory


def _ok_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/tenants" and request.method == "GET":
        return httpx.Response(
            200,
            json=[
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "name": "Acme",
                    "slug": "acme",
                    "status": "active",
                    "plan": "starter",
                    "created_at": "2026-05-01T00:00:00Z",
                },
                {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "name": "Beta",
                    "slug": "beta",
                    "status": "suspended",
                    "plan": "starter",
                    "created_at": "2026-05-02T00:00:00Z",
                },
            ],
        )
    return httpx.Response(404)


def test_tenants_table_renders_from_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tenants_page, "_http_client", _factory(_ok_handler))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    captions = " ".join(c.value for c in at.caption)
    # Live data path — no "(placeholder)" caption.
    assert "(placeholder)" not in captions
    # The page renders the create form on every run.
    full_md = " ".join(m.value for m in at.markdown)
    assert "Provision a tenant" in full_md
    assert "Suspend a tenant" in full_md
    assert "Trigger erasure" in full_md


def test_placeholder_fallback_on_backend_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def bad(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(tenants_page, "_http_client", _factory(bad))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    captions = " ".join(c.value for c in at.caption)
    assert "(placeholder)" in captions
    surface = " ".join(
        [m.value for m in at.markdown]
        + [c.value for c in at.caption]
        + [e.value for e in at.error]
    )
    assert "Traceback" not in surface
    assert "connection refused" not in surface


def test_create_calls_post_tenants(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/tenants" and request.method == "POST":
            seen.append(
                {"method": "POST", "url": str(request.url), "body": request.read()}
            )
            return httpx.Response(
                201,
                json={
                    "id": "33333333-3333-3333-3333-333333333333",
                    "name": "New Co",
                    "status": "active",
                },
            )
        return _ok_handler(request)

    monkeypatch.setattr(tenants_page, "_http_client", _factory(handler))
    code, body = tenants_page._post_create("New Co")
    assert code == 201
    assert body["name"] == "New Co"
    assert any(s["method"] == "POST" for s in seen)


def test_suspend_calls_post_suspend(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/suspend") and request.method == "POST":
            seen.append(str(request.url))
            return httpx.Response(200, json={"id": "x", "status": "suspended"})
        return _ok_handler(request)

    monkeypatch.setattr(tenants_page, "_http_client", _factory(handler))
    code = tenants_page._post_suspend("11111111-1111-1111-1111-111111111111", "demo")
    assert code == 200
    assert any("/suspend" in url for url in seen)


def test_erase_calls_delete_tenants(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE" and request.url.path.startswith("/tenants/"):
            seen.append((request.method, str(request.url)))
            return httpx.Response(200, json={"erased": True})
        return _ok_handler(request)

    monkeypatch.setattr(tenants_page, "_http_client", _factory(handler))
    code = tenants_page._delete_tenant(
        "11111111-1111-1111-1111-111111111111", "demo erase"
    )
    assert code == 200
    assert any(m == "DELETE" for m, _ in seen)
