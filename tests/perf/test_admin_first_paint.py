# Owner: Amer
"""Admin first-paint budget (Spec 009 T123a / SC-007).

Asserts wall-clock time from request to first widget render for the three
load-bearing admin entry surfaces:

  - Login (unauthenticated landing)
  - Tenant Admin Overview (post-login landing for role=tenant_admin)
  - Tenant Manager Overview (post-login landing for role=tenant_manager)

Budget: 1.0 s on a local backend. SC-007 explicitly carves out admin
first-paint at one second; visitor widget first-feedback is governed
separately by frontend/widget/src/__tests__/latency.test.tsx.

The TA and TM dashboards talk to backend endpoints during their render path;
we monkeypatch `_http_client` with an in-memory `httpx.MockTransport` so the
budget measures the page-render work rather than network latency.
"""

from __future__ import annotations

import time

import httpx
import pytest
from streamlit.testing.v1 import AppTest

import admin.overview_page as overview_page
import admin.platform_dashboard_page as platform_dashboard_page
from admin import auth_state

FIRST_PAINT_BUDGET_S = 1.0
APPTEST_TIMEOUT_S = 10.0


def _mock_client_factory(handler):
    def factory() -> httpx.Client:
        return httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="http://test",
        )
    return factory


def _ta_ok_handler(request: httpx.Request) -> httpx.Response:
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
        return httpx.Response(200, json=[])
    if path.startswith("/escalations"):
        return httpx.Response(200, json=[])
    return httpx.Response(200, json={})


def _tm_ok_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/tenants":
        return httpx.Response(200, json=[
            {"id": "00000000-0000-0000-0000-000000000001",
             "name": "Tenant A", "status": "active", "created_at": "2026-01-01T00:00:00Z"},
            {"id": "00000000-0000-0000-0000-000000000002",
             "name": "Tenant B", "status": "active", "created_at": "2026-01-01T00:00:00Z"},
        ])
    if path == "/audit-logs":
        return httpx.Response(200, json=[])
    return httpx.Response(200, json={})


def _time_render(entry: str) -> float:
    started = time.perf_counter()
    at = AppTest.from_file(entry)
    at.run(timeout=APPTEST_TIMEOUT_S)
    elapsed = time.perf_counter() - started
    assert not at.exception, f"{entry} raised: {at.exception}"
    return elapsed


def test_login_first_paint_under_budget() -> None:
    elapsed = _time_render("tests/perf/_admin_login_entry.py")
    assert elapsed < FIRST_PAINT_BUDGET_S, (
        f"login first paint {elapsed:.3f}s exceeded budget {FIRST_PAINT_BUDGET_S}s"
    )


def test_ta_overview_first_paint_under_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        overview_page, "_http_client", _mock_client_factory(_ta_ok_handler)
    )
    # Seed a signed-in tenant-admin session so the page renders real KPIs.
    monkeypatch.setattr(
        auth_state, "get_tenant_id",
        lambda: "00000000-0000-0000-0000-000000000001",
    )
    elapsed = _time_render("tests/integration/_admin_overview_page_entry.py")
    assert elapsed < FIRST_PAINT_BUDGET_S, (
        f"TA Overview first paint {elapsed:.3f}s exceeded budget {FIRST_PAINT_BUDGET_S}s"
    )


def test_tm_overview_first_paint_under_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        platform_dashboard_page, "_http_client", _mock_client_factory(_tm_ok_handler)
    )
    elapsed = _time_render("tests/perf/_admin_platform_dashboard_entry.py")
    assert elapsed < FIRST_PAINT_BUDGET_S, (
        f"TM Overview first paint {elapsed:.3f}s exceeded budget {FIRST_PAINT_BUDGET_S}s"
    )
