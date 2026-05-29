# Owner: Amer
"""Spec 009 US3 T083 — TM Audit Logs filtering.

The TM render path in admin/audit_page.py (T077 + T087) calls
``GET /audit-logs`` and forwards filter form values (actor, tenant_id,
action, date_from, date_to) as query-string parameters. This test mocks the
endpoint and asserts:

  - the page renders the filter form on every run,
  - the placeholder/forbidden message renders cleanly on 403,
  - the helper request mechanics forward all five filter knobs as query
    parameters when present.

The form inputs themselves are populated by Streamlit text-inputs whose
state we can't drive easily from AppTest without per-element keys; we
exercise the underlying ``_fetch`` helper that the form ultimately calls.
"""

from __future__ import annotations

from typing import Callable

import httpx
import pytest

from streamlit.testing.v1 import AppTest

import admin.audit_page as audit_page


_ENTRY = "tests/integration/_admin_audit_tm_entry.py"


def _factory(handler: Callable[[httpx.Request], httpx.Response]):
    def factory() -> httpx.Client:
        return httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="http://test",
        )

    return factory


def _ok_handler(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json=[
            {
                "id": "row-1",
                "tenant_id": "11111111-1111-1111-1111-111111111111",
                "actor_id": "someone@acme.example",
                "actor_role": "tenant_admin",
                "action": "cms.page_updated",
                "metadata_json": {"page_id": "abc"},
                "created_at": "2026-05-25T10:00:00Z",
            },
            {
                "id": "row-2",
                "tenant_id": "22222222-2222-2222-2222-222222222222",
                "actor_id": "tm@platform.example",
                "actor_role": "tenant_manager",
                "action": "tenant.provisioned",
                "metadata_json": {"tenant_name": "Beta"},
                "created_at": "2026-05-26T10:00:00Z",
            },
        ],
    )


def test_tm_audit_renders_filter_form(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit_page, "_http_client", _factory(_ok_handler))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    md = " ".join(m.value for m in at.markdown)
    assert "Filter" in md


def test_tm_audit_403_renders_generic_message(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "forbidden"})

    monkeypatch.setattr(audit_page, "_http_client", _factory(forbidden))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    errors = " ".join(e.value for e in at.error)
    assert "permission" in errors.lower()
    assert "forbidden" not in errors.lower() or "permission" in errors.lower()


def test_fetch_forwards_filter_query_params(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=[])

    monkeypatch.setattr(audit_page, "_http_client", _factory(handler))
    audit_page._fetch(
        "/audit-logs",
        params={
            "actor": "boss@platform.example",
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "action": "tenant.provisioned",
            "date_from": "2026-05-01T00:00:00Z",
            "date_to": "2026-05-30T23:59:59Z",
        },
    )
    assert len(seen) == 1
    params = seen[0]
    assert params["actor"] == "boss@platform.example"
    assert params["tenant_id"].startswith("11111111")
    assert params["action"] == "tenant.provisioned"
    assert "2026-05-01" in params["date_from"]
    assert "2026-05-30" in params["date_to"]


def test_fetch_no_params_when_filters_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=[])

    monkeypatch.setattr(audit_page, "_http_client", _factory(handler))
    audit_page._fetch("/audit-logs")
    assert seen == [{}]
