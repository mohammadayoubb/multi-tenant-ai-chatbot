# Owner: Amer
"""Spec 009 US3 T082 — TM Invites page: revoke / resend.

Asserts:
  - the page renders the issue-form, recent-invites table, and the
    revoke/resend control even when no rows are cached yet (placeholder/empty
    state path);
  - the placeholder/endpoint-pending caption is rendered (no platform-wide
    list endpoint exists yet, so the page surfaces a visible note);
  - the helper HTTP calls for revoke / resend invoke the right URLs and
    surface the right error category for each non-2xx status code.
"""

from __future__ import annotations

from typing import Callable

import httpx
import pytest

pytest.importorskip("admin.invites_page")

from streamlit.testing.v1 import AppTest  # noqa: E402

import admin.invites_page as invites_page  # noqa: E402


_ENTRY = "tests/integration/_admin_invites_page_entry.py"


def _factory(handler: Callable[[httpx.Request], httpx.Response]):
    def factory() -> httpx.Client:
        return httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="http://test",
        )

    return factory


def test_invites_page_renders_form_and_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    def noop(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    monkeypatch.setattr(invites_page, "_http_client", _factory(noop))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    captions = " ".join(c.value for c in at.caption)
    # Endpoint-pending caption is part of the contract.
    assert "endpoint pending" in captions
    md = " ".join(m.value for m in at.markdown)
    assert "Issue a new invite" in md
    assert "Revoke or resend an invite" in md


def test_revoke_helper_calls_revoke_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/revoke") and request.method == "POST":
            seen.append((request.method, str(request.url)))
            return httpx.Response(200, json={"ok": True, "revoked_at": "2026-05-29T00:00:00Z"})
        return httpx.Response(404)

    monkeypatch.setattr(invites_page, "_http_client", _factory(handler))
    code, body = invites_page._post_revoke("tok-1")
    assert code == 200
    assert body["ok"] is True
    assert any("/revoke" in url for _, url in seen)


def test_revoke_already_used_is_409(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"error": "invite_conflict"})

    monkeypatch.setattr(invites_page, "_http_client", _factory(handler))
    code, _ = invites_page._post_revoke("tok-used")
    assert code == 409


def test_resend_helper_calls_resend_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/resend") and request.method == "POST":
            seen.append((request.method, str(request.url)))
            return httpx.Response(
                200,
                json={
                    "token": "rotated-token",
                    "email": "x@y.example",
                    "role": "tenant_admin",
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "expires_at": "2026-06-05T00:00:00Z",
                },
            )
        return httpx.Response(404)

    monkeypatch.setattr(invites_page, "_http_client", _factory(handler))
    code, body = invites_page._post_resend("tok-old")
    assert code == 200
    assert body["token"] == "rotated-token"
    assert any("/resend" in url for _, url in seen)


def test_create_invite_helper_calls_post(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/admin/invites" and request.method == "POST":
            seen.append((request.method, str(request.url)))
            return httpx.Response(
                200,
                json={
                    "token": "fresh-token",
                    "email": "x@y.example",
                    "role": "tenant_admin",
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "expires_at": "2026-06-05T00:00:00Z",
                },
            )
        return httpx.Response(404)

    monkeypatch.setattr(invites_page, "_http_client", _factory(handler))
    code, body = invites_page._post_create_invite("x@y.example", "tenant_admin", 86400)
    assert code == 200
    assert body["token"] == "fresh-token"
    assert any("/admin/invites" in url for _, url in seen)
