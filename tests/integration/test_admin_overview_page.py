# Owner: Amer
"""Integration tests for admin/overview_page.py (Spec 009 US2, T060).

Covers the TA Overview dashboard surface:
  - KPI cards render from real backend data when endpoints respond 200.
  - Placeholder fallback path renders a visible "(placeholder)" caption when
    any feeding endpoint is unreachable, with no leaked error text or stack
    trace (Principle V).

The page module itself lands in T068; until then `pytest.importorskip`
defers these cases. When T068 merges they activate automatically.
"""

from __future__ import annotations

from typing import Callable

import httpx
import pytest

pytest.importorskip("admin.overview_page")

from streamlit.testing.v1 import AppTest  # noqa: E402

import admin.overview_page as overview_page  # noqa: E402


_ENTRY = "tests/integration/_admin_overview_page_entry.py"


def _factory(handler: Callable[[httpx.Request], httpx.Response]):
    def factory() -> httpx.Client:
        return httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="http://test",
        )
    return factory


def _ok_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/widgets/config":
        return httpx.Response(200, json={
            "widget_id": "9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d",
            "allowed_origins": ["https://acme.example"],
            "enabled": True,
            "theme_json": None,
            "greeting": None,
        })
    if path.endswith("/usage"):
        return httpx.Response(200, json={
            "total_tokens": 1500,
            "total_cost_usd": 1.25,
            "by_feature": {"chat": {"tokens": 1500, "cost_usd": 1.25}},
            "daily_cost_usd": [{"date": "2026-05-27", "cost_usd": 1.25}],
        })
    if path == "/leads":
        return httpx.Response(200, json=[
            {"id": "l1", "name": "L1", "contact": "x@y", "intent": "demo",
             "status": "captured", "quality_score": 0.5,
             "created_at": "2026-05-25T10:00:00Z"},
        ])
    if path.startswith("/escalations"):
        return httpx.Response(200, json=[
            {"ticket_id": "t1", "opened_at": "2026-05-25T10:00:00Z",
             "last_message_excerpt": "...", "status": "pending",
             "assignee_id": None, "assignee_name": None},
        ])
    return httpx.Response(200, json={})


def test_overview_renders_kpi_cards_from_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(overview_page, "_http_client", _factory(_ok_handler))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    # Real backend path: no placeholder badge anywhere.
    captions = " ".join(c.value for c in at.caption)
    assert "(placeholder)" not in captions
    # At least one st.metric card rendered.
    assert len(at.metric) >= 1


def test_overview_falls_back_to_placeholder_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def bad(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(overview_page, "_http_client", _factory(bad))
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
    assert "Traceback" not in full_output
    assert "connection refused" not in full_output
