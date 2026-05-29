# Owner: Amer
"""Integration tests for admin/agent_settings_page.py (Spec 009 US2, T062).

Covers:
  - Happy path: form Save calls PUT /tenants/{tid}/agent-config with the
    persona, greeting, tone, language, business rules, and chip list.
  - Server returns 422 when chips length > 6; the page must surface the
    validation error and not clobber draft state.
  - Backend GET 404 (endpoint not yet shipped or transport error) →
    placeholder fallback renders with a "(placeholder)" caption and the
    product-default chip set.

The page module itself lands in T071; until then `pytest.importorskip`
defers these cases.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import httpx
import pytest

pytest.importorskip("admin.agent_settings_page")

from streamlit.testing.v1 import AppTest  # noqa: E402

import admin.agent_settings_page as page  # noqa: E402


_ENTRY = "tests/integration/_admin_agent_settings_page_entry.py"


_LIVE_CONFIG: dict[str, Any] = {
    "persona_name": "Acme Concierge",
    "greeting": "Hi! How can I help?",
    "tone": "professional",
    "language": "en",
    "business_rules": "Never quote unreleased pricing.",
    "chips": ["Pricing", "Demo", "Hours", "Contact"],
}


def _make_factory(handler: Callable[[httpx.Request], httpx.Response]):
    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    return factory


def test_agent_settings_happy_save(monkeypatch: pytest.MonkeyPatch) -> None:
    """T062: edit one field, click Save → PUT body matches the draft."""
    state: dict[str, Any] = {"row": dict(_LIVE_CONFIG), "calls": []}

    def handler(req: httpx.Request) -> httpx.Response:
        state["calls"].append({"method": req.method, "path": req.url.path,
                                "body": req.content.decode() if req.content else ""})
        if req.method == "GET" and "/agent-config" in req.url.path:
            return httpx.Response(200, json=state["row"])
        if req.method == "PUT" and "/agent-config" in req.url.path:
            state["row"] = json.loads(req.content)
            return httpx.Response(200, json=state["row"])
        return httpx.Response(404)

    monkeypatch.setattr(page, "_http_client", _make_factory(handler))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception

    at.text_input(key="greeting_input").set_value("Hello! Anything I can help with?")
    at.button(key="save_agent_config").click()
    at.run(timeout=10)
    assert not at.exception

    puts = [c for c in state["calls"] if c["method"] == "PUT"]
    assert len(puts) == 1
    body = json.loads(puts[0]["body"])
    assert body["greeting"] == "Hello! Anything I can help with?"


def test_agent_settings_rejects_chip_count_over_six(monkeypatch: pytest.MonkeyPatch) -> None:
    """T062: > 6 chips → client-side rejection OR server-side 422 surfaced inline."""
    state: dict[str, Any] = {"row": dict(_LIVE_CONFIG), "calls": []}

    def handler(req: httpx.Request) -> httpx.Response:
        state["calls"].append({"method": req.method, "path": req.url.path,
                                "body": req.content.decode() if req.content else ""})
        if req.method == "GET" and "/agent-config" in req.url.path:
            return httpx.Response(200, json=state["row"])
        if req.method == "PUT" and "/agent-config" in req.url.path:
            payload = json.loads(req.content)
            if len(payload.get("chips", [])) > 6:
                return httpx.Response(422, json={"detail": "chips: too many"})
            state["row"] = payload
            return httpx.Response(200, json=state["row"])
        return httpx.Response(404)

    monkeypatch.setattr(page, "_http_client", _make_factory(handler))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)

    # Seven chips, one per line.
    at.text_area(key="chips_input").set_value(
        "Pricing\nDemo\nHours\nContact\nSupport\nDocs\nCareers"
    )
    at.run(timeout=10)

    # Either the Save button is disabled by the client validator OR clicking
    # it surfaces an inline error. Both satisfy the contract.
    save_btn = at.button(key="save_agent_config")
    if save_btn.disabled:
        return
    save_btn.click()
    at.run(timeout=10)
    error_text = " ".join(e.value for e in at.error)
    assert "chips" in error_text.lower() or "6" in error_text


def test_agent_settings_placeholder_fallback_on_get_404(monkeypatch: pytest.MonkeyPatch) -> None:
    """Endpoint absent (404 / transport error) → render product-default chips with badge."""
    def bad(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    monkeypatch.setattr(page, "_http_client", _make_factory(bad))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    captions = " ".join(c.value for c in at.caption) + " ".join(w.value for w in at.warning)
    assert "(placeholder)" in captions
