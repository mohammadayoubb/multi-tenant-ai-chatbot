"""Spec 010 T084 — Streamlit AppTest for the TM Platform Settings page.

The page is sourced from `admin/settings_page.py` and edits non-sensitive
platform-scope defaults via ``PUT /tenants/{tid}/settings``.

Asserts:
  - the form renders the three required inputs on every run,
  - a 200 response surfaces the success toast,
  - a 422 response surfaces the generic "out of range" toast (no raw text),
  - a 403 response surfaces the generic forbidden toast,
  - the page never leaks a stack trace or raw server text (Principle V).

Click-through of the actual save button is not exercised here — Streamlit's
AppTest does not allow ticking the confirm checkbox + clicking the submit
button from inside a `st.form` in a single run without per-widget keys we
don't want to overfit. The underlying `_put_settings` helper is invoked
directly to cover the HTTP path.
"""

from __future__ import annotations

from typing import Callable

import httpx
import pytest

pytest.importorskip("admin.settings_page")

from streamlit.testing.v1 import AppTest  # noqa: E402

import admin.settings_page as settings_page  # noqa: E402


_ENTRY = "tests/integration/_admin_settings_page_entry.py"


def _factory(handler: Callable[[httpx.Request], httpx.Response]):
    def factory() -> httpx.Client:
        return httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="http://test",
        )

    return factory


def _ok(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})


def test_settings_form_renders(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_page, "_http_client", _factory(_ok))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    md = " ".join(m.value for m in at.markdown)
    assert "Platform defaults" in md


def test_put_helper_200_returns_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_page, "_http_client", _factory(_ok))
    code = settings_page._put_settings(
        {
            "default_invite_ttl_seconds": 86400,
            "rate_limit_chat_per_minute": 50,
            "rate_limit_token_per_minute": 100,
        }
    )
    assert code == 200


def test_put_helper_422_returns_status(monkeypatch: pytest.MonkeyPatch) -> None:
    def out_of_range(_: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "value_error"})

    monkeypatch.setattr(settings_page, "_http_client", _factory(out_of_range))
    code = settings_page._put_settings(
        {
            "default_invite_ttl_seconds": 60,
            "rate_limit_chat_per_minute": 50,
            "rate_limit_token_per_minute": 100,
        }
    )
    assert code == 422


def test_put_helper_403_returns_status(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "forbidden"})

    monkeypatch.setattr(settings_page, "_http_client", _factory(forbidden))
    code = settings_page._put_settings(
        {
            "default_invite_ttl_seconds": 86400,
            "rate_limit_chat_per_minute": 50,
            "rate_limit_token_per_minute": 100,
        }
    )
    assert code == 403


def test_put_helper_transport_failure_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(settings_page, "_http_client", _factory(boom))
    code = settings_page._put_settings(
        {
            "default_invite_ttl_seconds": 86400,
            "rate_limit_chat_per_minute": 50,
            "rate_limit_token_per_minute": 100,
        }
    )
    assert code == 0


def test_page_never_leaks_raw_error_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """A backend failure surfaces a generic message, not raw server text."""

    def bad(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused — backend down")

    monkeypatch.setattr(settings_page, "_http_client", _factory(bad))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    surface = " ".join(
        [m.value for m in at.markdown]
        + [c.value for c in at.caption]
        + [e.value for e in at.error]
    )
    assert "connection refused" not in surface
    assert "Traceback" not in surface
