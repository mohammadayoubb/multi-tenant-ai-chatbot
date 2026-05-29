# Owner: Amer
"""Integration tests for admin/leads_page.py.

Spec 005 US3 originally locked the leads viewer as read-only (FR-010). That
constraint was lifted in feature 010 — admins now mark leads qualified or
spam inline. These tests now cover the editable-row design and the page-size
pagination. Redaction + placeholder fallback (FR-009 / FR-013 / SC-004) are
unchanged.
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


def _row_selectboxes(at: AppTest) -> list:
    """Per-row status selectboxes (excludes the top filter)."""
    return [s for s in at.selectbox if s.key and s.key.startswith("lead_status_select_")]


def _row_save_buttons(at: AppTest) -> list:
    return [b for b in at.button if b.key and b.key.startswith("lead_status_save_")]


def _all_text(at: AppTest) -> str:
    return " ".join(
        [m.value for m in at.markdown]
        + [c.value for c in at.caption]
        + [w.value for w in at.warning]
    )


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
    # One status selector + Save button per real lead.
    assert len(_row_selectboxes(at)) == 3
    assert len(_row_save_buttons(at)) == 3
    text = _all_text(at)
    # Redacted forms appear; raw forms do not.
    assert "ave***" in text
    assert "+15***" in text
    assert "bot***" in text
    assert "avery@example.com" not in text
    assert "+15551234567" not in text
    assert "bot@spam.test" not in text


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
    assert not at.exception
    assert len(_row_selectboxes(at)) == 1


def test_pagination_shows_one_page_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    big_set = [
        {
            "id": f"lead-{i}",
            "created_at": f"2026-05-{i + 1:02d}T10:00:00Z",
            "name": f"Lead {i}",
            "contact": f"lead{i}@example.com",
            "intent": "demo_request",
            "status": "captured",
            "quality_score": 0.5,
        }
        for i in range(25)
    ]
    monkeypatch.setattr(
        leads_page,
        "_http_client",
        _factory(lambda req: httpx.Response(200, json=big_set)),
    )
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    # Page size is 10 — first page should show exactly 10 rows.
    assert len(_row_selectboxes(at)) == 10
    # Pagination caption mentions the current window.
    caps = " ".join(c.value for c in at.caption)
    assert "Page 1 of 3" in caps
    # Advance to page 2.
    at.button(key="leads_next_page").click()
    at.run(timeout=10)
    assert len(_row_selectboxes(at)) == 10
    caps2 = " ".join(c.value for c in at.caption)
    assert "Page 2 of 3" in caps2
    # Advance to last page — only 5 rows remaining.
    at.button(key="leads_next_page").click()
    at.run(timeout=10)
    assert len(_row_selectboxes(at)) == 5


def test_save_button_calls_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clicking Save after changing the selector triggers a PATCH."""
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=_LIVE_LEADS)
        if request.method == "PATCH":
            import json as _json

            body = _json.loads(request.content.decode())
            calls.append((request.url.path, body.get("status", "")))
            return httpx.Response(200, json={**_LIVE_LEADS[0], "status": body["status"]})
        return httpx.Response(405)

    monkeypatch.setattr(leads_page, "_http_client", _factory(handler))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    at.selectbox(key="lead_status_select_l1").set_value("qualified")
    at.button(key="lead_status_save_l1").click()
    at.run(timeout=10)
    assert not at.exception
    assert calls == [("/leads/l1", "qualified")]


def test_placeholder_fallback_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        leads_page, "_http_client", _factory(lambda req: httpx.Response(404))
    )
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    captions = " ".join(c.value for c in at.caption) + " ".join(w.value for w in at.warning)
    assert "(placeholder)" in captions
    # Placeholder rows still render but without per-row edit affordances.
    assert _row_save_buttons(at) == []


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


def test_placeholder_path_renders_no_edit_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    """The placeholder dataset has no real ids, so the Save / status-change
    controls must stay hidden — we never POST against placeholder ids."""
    monkeypatch.setattr(
        leads_page, "_http_client", _factory(lambda req: httpx.Response(500))
    )
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    assert _row_selectboxes(at) == []
    assert _row_save_buttons(at) == []
