# Owner: Amer
"""Integration tests for admin/leads_page.py.

Spec 005 US3. Covers FR-009 (redacted contact), FR-010 (status filter, no
edit controls), FR-013 (non-2xx / transport error → placeholder), SC-004
(contact ≤ 3 chars clear text).
"""

from __future__ import annotations

from typing import Callable

import httpx
import pytest
from streamlit.testing.v1 import AppTest

import admin.leads_page as leads_page
from admin.leads_page import redact_contact

_ENTRY = "tests/integration/_admin_leads_page_entry.py"

_LIVE_LEADS = [
    {
        "id": "l1",
        "created_at": "2026-05-26T18:02:11Z",
        "name": "Avery T.",
        "contact": "avery@example.com",
        "intent": "demo_request",
        "status": "captured",
        "quality_score": 0.7421,
    },
    {
        "id": "l2",
        "created_at": "2026-05-25T10:00:00Z",
        "name": None,
        "contact": "+15551234567",
        "intent": "pricing_question",
        "status": "qualified",
        "quality_score": None,
    },
    {
        "id": "l3",
        "created_at": "2026-05-24T08:00:00Z",
        "name": "spammy",
        "contact": "bot@spam.test",
        "intent": "unknown",
        "status": "spam",
        "quality_score": 0.01,
    },
]


def _factory(handler: Callable[[httpx.Request], httpx.Response]) -> Callable[[], httpx.Client]:
    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    return factory


@pytest.mark.parametrize(
    "value,expected",
    [
        ("", "***"),
        ("a", "a***"),
        ("ab", "ab***"),
        ("abc", "abc***"),
        ("avery@example.com", "ave***"),
    ],
)
def test_redact_contact_edge_cases(value: str, expected: str) -> None:
    assert redact_contact(value) == expected


def test_happy_path_renders_redacted_contacts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        leads_page,
        "_http_client",
        _factory(lambda req: httpx.Response(200, json=_LIVE_LEADS)),
    )
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    rendered = at.dataframe[0].value
    assert len(rendered) == 3
    contacts = rendered["contact"].tolist()
    assert contacts == ["ave***", "+15***", "bot***"]
    # No raw contact value anywhere on the page.
    full_text = " ".join(
        [m.value for m in at.markdown]
        + [c.value for c in at.caption]
        + [w.value for w in at.warning]
    )
    assert "avery@example.com" not in full_text
    assert "+15551234567" not in full_text
    assert "bot@spam.test" not in full_text


def test_status_filter_narrows_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        leads_page,
        "_http_client",
        _factory(lambda req: httpx.Response(200, json=_LIVE_LEADS)),
    )
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    at.selectbox(key="leads_status_filter").set_value("qualified")
    at.run(timeout=10)
    rendered = at.dataframe[0].value
    assert len(rendered) == 1
    assert rendered["status"].tolist() == ["qualified"]


def test_placeholder_fallback_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        leads_page, "_http_client", _factory(lambda req: httpx.Response(404))
    )
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    captions = " ".join(c.value for c in at.caption) + " ".join(w.value for w in at.warning)
    assert "(placeholder)" in captions
    assert len(at.dataframe) == 1


@pytest.mark.parametrize("failure", ["status_500", "transport_error"])
def test_server_error_falls_back_to_placeholder(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    secret_marker = "leaked-contact-or-stack-trace"

    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "transport_error":
            raise httpx.ConnectError("connection refused")
        return httpx.Response(500, text=secret_marker)

    monkeypatch.setattr(leads_page, "_http_client", _factory(handler))
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
    assert secret_marker not in full_output
    assert "Traceback" not in full_output


def test_no_mutating_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-010: no qualify/spam/export/edit controls."""
    monkeypatch.setattr(
        leads_page,
        "_http_client",
        _factory(lambda req: httpx.Response(200, json=_LIVE_LEADS)),
    )
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert at.button == []
