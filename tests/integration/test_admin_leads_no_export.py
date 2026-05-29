# Owner: Amer
"""Integration test for the leads page export-controls discipline (Spec 009 US2, T067).

FR-024: the TA Leads page MUST NOT expose any download / export control —
visitor PII never leaves the admin surface. This file makes that explicit
as a separate, named regression rather than relying on a side-effect of
test_leads_page.py::test_no_mutating_controls.
"""

from __future__ import annotations

from typing import Any, Callable

import httpx
import pytest
from streamlit.testing.v1 import AppTest

import admin.leads_page as leads_page


_ENTRY = "tests/integration/_admin_leads_page_entry.py"


_LIVE_LEADS: list[dict[str, Any]] = [
    {
        "id": "l1",
        "created_at": "2026-05-26T18:02:11Z",
        "name": "Lead One",
        "contact": "one@example.com",
        "intent": "demo_request",
        "status": "captured",
        "quality_score": 0.81,
    },
]


def _factory(handler: Callable[[httpx.Request], httpx.Response]):
    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    return factory


def test_leads_page_renders_no_export_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    """No button anywhere on the page is wired to export / download."""
    monkeypatch.setattr(
        leads_page,
        "_http_client",
        _factory(lambda req: httpx.Response(200, json=_LIVE_LEADS)),
    )
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception

    # Hard rule: zero buttons on the read-only Leads page (matches existing
    # admin/leads_page.py invariant).
    assert at.button == []

    # And no copy reading "download" / "export" / "csv" anywhere visible.
    full_text = " ".join(
        [m.value for m in at.markdown]
        + [c.value for c in at.caption]
        + [w.value for w in at.warning]
    ).lower()
    for forbidden in ("download", "export", "csv", "xlsx", "json dump"):
        assert forbidden not in full_text, (
            f"Leads page must not surface a {forbidden!r} control (FR-024). "
            f"Found in: {full_text!r}"
        )


def test_leads_page_placeholder_path_still_has_no_export(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even on the placeholder/error path, no export control is added."""
    monkeypatch.setattr(
        leads_page,
        "_http_client",
        _factory(lambda req: httpx.Response(500)),
    )
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    assert at.button == []
