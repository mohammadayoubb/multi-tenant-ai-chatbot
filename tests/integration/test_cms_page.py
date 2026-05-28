# Owner: Amer
"""Integration tests for admin/cms_page.py.

Spec 005 US2. Covers FR-007 (status filter), FR-008 (read-only detail viewer),
FR-013 (any non-2xx or transport error falls back to placeholder).
"""

from __future__ import annotations

from typing import Callable

import httpx
import pytest
from streamlit.testing.v1 import AppTest

import admin.cms_page as cms_page

_ENTRY = "tests/integration/_admin_cms_page_entry.py"

_LIVE_PAGES = [
    {
        "id": "p1",
        "title": "Pricing",
        "slug": "pricing",
        "body": "## Plans\n\nStarter, Pro, Enterprise.",
        "source_url": "https://example.com/pricing",
        "status": "published",
        "updated_at": "2026-05-22T11:10:00Z",
    },
    {
        "id": "p2",
        "title": "Roadmap (draft)",
        "slug": "roadmap",
        "body": "Coming soon.",
        "source_url": None,
        "status": "draft",
        "updated_at": "2026-05-21T08:00:00Z",
    },
    {
        "id": "p3",
        "title": "Old FAQ",
        "slug": "old-faq",
        "body": "Archived.",
        "source_url": None,
        "status": "archived",
        "updated_at": "2026-04-10T08:00:00Z",
    },
]


def _factory(handler: Callable[[httpx.Request], httpx.Response]) -> Callable[[], httpx.Client]:
    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    return factory


def test_happy_path_renders_all_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cms_page,
        "_http_client",
        _factory(lambda req: httpx.Response(200, json=_LIVE_PAGES)),
    )
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    assert len(at.dataframe) == 1
    rendered = at.dataframe[0].value
    assert len(rendered) == 3
    statuses = set(rendered["status"].tolist())
    assert statuses == {"draft", "published", "archived"}

    captions = " ".join(c.value for c in at.caption)
    assert "(placeholder)" not in captions


def test_status_filter_narrows_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cms_page,
        "_http_client",
        _factory(lambda req: httpx.Response(200, json=_LIVE_PAGES)),
    )
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    at.selectbox(key="cms_status_filter").set_value("published")
    at.run(timeout=10)
    assert not at.exception
    rendered = at.dataframe[0].value
    assert len(rendered) == 1
    assert rendered["status"].tolist() == ["published"]


def test_placeholder_fallback_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cms_page, "_http_client", _factory(lambda req: httpx.Response(404))
    )
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    captions = " ".join(c.value for c in at.caption) + " ".join(w.value for w in at.warning)
    assert "(placeholder)" in captions
    # Should still render the sample table.
    assert len(at.dataframe) == 1


@pytest.mark.parametrize("failure", ["status_500", "transport_error"])
def test_server_error_falls_back_to_placeholder(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    secret_marker = "internal-stack-trace-do-not-leak"

    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "transport_error":
            raise httpx.ConnectError("connection refused")
        return httpx.Response(500, text=secret_marker)

    monkeypatch.setattr(cms_page, "_http_client", _factory(handler))
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
    """FR-008: no create/edit/delete affordances anywhere."""
    monkeypatch.setattr(
        cms_page,
        "_http_client",
        _factory(lambda req: httpx.Response(200, json=_LIVE_PAGES)),
    )
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert at.button == []
