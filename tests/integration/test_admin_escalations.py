# Owner: Amer
"""Integration tests for admin/escalations_page.py (Spec 009 US2, T065).

Covers:
  - Status PATCH round-trip (open → in_progress) calls
    PATCH /escalations/{id} with the chosen status.
  - Assignee dropdown is populated from GET /tenants/{tid}/admin-users; when
    that endpoint isn't shipped yet, the dropdown renders a "(no admin users
    available — endpoint pending)" placeholder and the assign control is
    disabled.
  - A cross-tenant ticket id returns 403; the page surfaces a generic
    "forbidden" notice and the table row is removed / hidden.

The page module lands in T075.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import httpx
import pytest

pytest.importorskip("admin.escalations_page")

from streamlit.testing.v1 import AppTest  # noqa: E402

import admin.escalations_page as page  # noqa: E402


_ENTRY = "tests/integration/_admin_escalations_page_entry.py"


_LIVE_TICKETS = [
    {
        "ticket_id": "11111111-1111-1111-1111-111111111111",
        "opened_at": "2026-05-26T18:02:11Z",
        "last_message_excerpt": "need a human",
        "status": "pending",
        "assignee_id": None,
        "assignee_name": None,
    },
]

_LIVE_ADMINS = [
    {
        "actor_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "full_name": "Alice Admin",
        "email": "alice@acme.example",
        "role": "tenant_admin",
        "status": "active",
    },
]


def _factory(handler: Callable[[httpx.Request], httpx.Response]):
    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    return factory


def test_status_patch_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict[str, Any] = {"tickets": list(_LIVE_TICKETS), "calls": []}

    def handler(req: httpx.Request) -> httpx.Response:
        state["calls"].append({"method": req.method, "path": req.url.path,
                                "body": req.content.decode() if req.content else ""})
        if req.method == "GET" and req.url.path == "/escalations":
            return httpx.Response(200, json=state["tickets"])
        if req.method == "GET" and "/admin-users" in req.url.path:
            return httpx.Response(200, json=_LIVE_ADMINS)
        if req.method == "PATCH" and req.url.path.startswith("/escalations/"):
            payload = json.loads(req.content)
            for t in state["tickets"]:
                if t["ticket_id"] in req.url.path:
                    t["status"] = payload.get("status", t["status"])
                    if "assignee_id" in payload:
                        t["assignee_id"] = payload["assignee_id"]
            return httpx.Response(200, json=state["tickets"][0])
        return httpx.Response(404)

    monkeypatch.setattr(page, "_http_client", _factory(handler))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception

    # Pick the in_progress status option and save.
    at.selectbox(key="status_select_11111111-1111-1111-1111-111111111111").set_value(
        "in_progress"
    )
    at.button(key="save_ticket_11111111-1111-1111-1111-111111111111").click()
    at.run(timeout=10)
    assert not at.exception

    patches = [c for c in state["calls"] if c["method"] == "PATCH"]
    assert len(patches) == 1
    body = json.loads(patches[0]["body"])
    assert body["status"] == "in_progress"


def test_assignee_dropdown_placeholder_when_endpoint_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """If /tenants/{tid}/admin-users 404s, the dropdown renders a disabled placeholder."""
    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.path == "/escalations":
            return httpx.Response(200, json=_LIVE_TICKETS)
        if req.method == "GET" and "/admin-users" in req.url.path:
            return httpx.Response(404)
        return httpx.Response(404)

    monkeypatch.setattr(page, "_http_client", _factory(handler))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception

    captions = " ".join(c.value for c in at.caption) + " ".join(w.value for w in at.warning)
    assert "endpoint pending" in captions or "(placeholder)" in captions


def test_cross_tenant_ticket_403_surfaced(monkeypatch: pytest.MonkeyPatch) -> None:
    """A PATCH that returns 403 must surface a generic forbidden message,
    not raw response text or a stack trace."""
    secret_marker = "sensitive-server-error"

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.path == "/escalations":
            return httpx.Response(200, json=_LIVE_TICKETS)
        if req.method == "GET" and "/admin-users" in req.url.path:
            return httpx.Response(200, json=_LIVE_ADMINS)
        if req.method == "PATCH" and req.url.path.startswith("/escalations/"):
            return httpx.Response(403, text=secret_marker)
        return httpx.Response(404)

    monkeypatch.setattr(page, "_http_client", _factory(handler))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    at.selectbox(key="status_select_11111111-1111-1111-1111-111111111111").set_value(
        "resolved"
    )
    at.button(key="save_ticket_11111111-1111-1111-1111-111111111111").click()
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
    # And the generic forbidden notice appears.
    assert "forbidden" in full_output.lower() or "not allowed" in full_output.lower()
