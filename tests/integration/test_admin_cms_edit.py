# Owner: Amer
"""Streamlit AppTest for admin/cms_page.py Delete confirm flow (T046).

Covers:
  - Delete is gated by a two-step confirm; clicking the initial Delete button
    must NOT fire DELETE /cms/pages/{id}.
  - Clicking the second-step "Confirm delete" button fires exactly one DELETE.
  - Cancel after the initial Delete click is a no-op (no DELETE fired).

Note: tasks.md T041/R9 calls out ``st.dialog`` as the confirm pattern; the
current implementation uses the functionally-equivalent session_state confirm
gate (two clicks: Delete → Confirm delete). This test exercises that flow as
implemented.
"""

from __future__ import annotations

from typing import Any, Callable

import httpx
import pytest

pytest.importorskip("admin.cms_page")

from streamlit.testing.v1 import AppTest  # noqa: E402

import admin.cms_page as page  # noqa: E402


_ENTRY = "tests/integration/_admin_cms_page_entry.py"


_LIVE_PAGES = [
    {
        "id": "11111111-2222-3333-4444-555555555555",
        "title": "Pricing",
        "slug": "pricing",
        "body": "Plans and pricing.",
        "source_url": None,
        "status": "published",
        "updated_at": "2026-05-26T10:00:00Z",
    },
]


def _factory(handler: Callable[[httpx.Request], httpx.Response]):
    def factory() -> httpx.Client:
        return httpx.Client(
            transport=httpx.MockTransport(handler), base_url="http://test"
        )

    return factory


def _make_handler(state: dict[str, Any]):
    def handler(req: httpx.Request) -> httpx.Response:
        state["calls"].append({"method": req.method, "path": req.url.path})
        if req.method == "GET" and req.url.path == "/cms/pages":
            return httpx.Response(200, json=state["pages"])
        if req.method == "DELETE" and req.url.path.startswith("/cms/pages/"):
            page_id = req.url.path.rsplit("/", 1)[-1]
            state["pages"] = [p for p in state["pages"] if p["id"] != page_id]
            return httpx.Response(204)
        return httpx.Response(404)

    return handler


def test_delete_requires_two_step_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    """First click on Delete must NOT fire the DELETE request."""
    state: dict[str, Any] = {"pages": list(_LIVE_PAGES), "calls": []}
    monkeypatch.setattr(page, "_http_client", _factory(_make_handler(state)))

    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception

    page_id = _LIVE_PAGES[0]["id"]
    # First click — opens the confirm gate but must NOT delete.
    at.button(key=f"cms_delete_{page_id}").click()
    at.run(timeout=10)
    assert not at.exception

    deletes = [c for c in state["calls"] if c["method"] == "DELETE"]
    assert deletes == [], "Initial Delete click must NOT fire DELETE"
    # The page is still in the dataset.
    assert any(p["id"] == page_id for p in state["pages"])


def test_confirm_delete_fires_exactly_one_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After Delete → Confirm delete, exactly one DELETE request fires."""
    state: dict[str, Any] = {"pages": list(_LIVE_PAGES), "calls": []}
    monkeypatch.setattr(page, "_http_client", _factory(_make_handler(state)))

    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    page_id = _LIVE_PAGES[0]["id"]

    # Step 1: open the confirm gate.
    at.button(key=f"cms_delete_{page_id}").click()
    at.run(timeout=10)
    assert not at.exception

    # Step 2: click Confirm delete.
    at.button(key=f"cms_delete_confirm_yes_{page_id}").click()
    at.run(timeout=10)
    assert not at.exception

    deletes = [c for c in state["calls"] if c["method"] == "DELETE"]
    assert len(deletes) == 1
    assert page_id in deletes[0]["path"]
    # Server state reflects the delete.
    assert all(p["id"] != page_id for p in state["pages"])


def test_cancel_is_a_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete → Cancel must NOT fire DELETE and must reset the confirm state."""
    state: dict[str, Any] = {"pages": list(_LIVE_PAGES), "calls": []}
    monkeypatch.setattr(page, "_http_client", _factory(_make_handler(state)))

    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    page_id = _LIVE_PAGES[0]["id"]

    at.button(key=f"cms_delete_{page_id}").click()
    at.run(timeout=10)
    at.button(key=f"cms_delete_confirm_no_{page_id}").click()
    at.run(timeout=10)
    assert not at.exception

    deletes = [c for c in state["calls"] if c["method"] == "DELETE"]
    assert deletes == [], "Cancel must NOT fire DELETE"
    # The page is still present.
    assert any(p["id"] == page_id for p in state["pages"])
