# Owner: Amer
"""Integration tests for admin/widget_page.py using Streamlit's AppTest harness.

Backend is replaced by an httpx MockTransport so these tests don't need a
running FastAPI server. Covers tasks T041-T044 (add-origin round trip,
greeting save, invalid JSON disables Save).
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from streamlit.testing.v1 import AppTest

import admin.widget_page as widget_page


SEED_ROW: dict[str, Any] = {
    "widget_id": "9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d",
    "allowed_origins": ["https://acme.example"],
    "enabled": True,
    "theme_json": None,
    "greeting": None,
}


def _make_fake_client_factory(initial: dict[str, Any]):
    """Return (state_dict, client_factory). The factory returns a fresh httpx
    Client backed by MockTransport on each call (the page uses a `with` block)."""
    state: dict[str, Any] = {"row": dict(initial), "calls": []}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"].append(
            {
                "method": request.method,
                "path": request.url.path,
                "body": request.content.decode() if request.content else "",
            }
        )
        if request.method == "GET" and request.url.path == "/widgets/config":
            return httpx.Response(200, json=state["row"])
        if request.method == "PUT" and request.url.path == "/widgets/config":
            body = json.loads(request.content)
            state["row"] = {
                "widget_id": state["row"]["widget_id"],
                "allowed_origins": body["allowed_origins"],
                "enabled": body["enabled"],
                "theme_json": body.get("theme_json"),
                "greeting": body.get("greeting"),
            }
            return httpx.Response(200, json=state["row"])
        return httpx.Response(404, json={"error": "not found"})

    def factory():
        return httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="http://test",
        )

    return state, factory


@pytest.fixture(autouse=True)
def _patch_http(monkeypatch):
    state, factory = _make_fake_client_factory(SEED_ROW)
    monkeypatch.setattr(widget_page, "_http_client", factory)
    yield state


def test_admin_page_initial_render_shows_saved_state(_patch_http):
    at = AppTest.from_file("tests/integration/_admin_widget_page_entry.py")
    at.run(timeout=10)
    assert not at.exception
    # "✓ All changes saved" is rendered when draft == saved.
    markdown_text = " ".join(m.value for m in at.markdown)
    assert "All changes saved" in markdown_text


def test_admin_page_add_origin_round_trip(_patch_http):
    """T042: add origin via input → click Add → click Save → fake PUT recorded."""
    at = AppTest.from_file("tests/integration/_admin_widget_page_entry.py")
    at.run(timeout=10)

    # Type a new origin into the add-origin input.
    at.text_input(key="add_origin_input").set_value(
        "https://new.acme.example"
    )
    # Click Add.
    at.button(key="add_origin_button").click()
    at.run(timeout=10)
    assert not at.exception

    # Click Save.
    at.button(key="save_widget_config").click()
    at.run(timeout=10)
    assert not at.exception

    # The fake backend should have received a PUT with the new origin.
    puts = [c for c in _patch_http["calls"] if c["method"] == "PUT"]
    assert len(puts) == 1
    put_body = json.loads(puts[0]["body"])
    assert "https://new.acme.example" in put_body["allowed_origins"]


def test_admin_page_greeting_save(_patch_http):
    """T043: change greeting input → save → fake PUT body has new greeting."""
    at = AppTest.from_file("tests/integration/_admin_widget_page_entry.py")
    at.run(timeout=10)

    at.text_input(key="greeting_input").set_value("Hi from Acme")
    at.run(timeout=10)
    assert not at.exception

    at.button(key="save_widget_config").click()
    at.run(timeout=10)
    assert not at.exception

    puts = [c for c in _patch_http["calls"] if c["method"] == "PUT"]
    assert len(puts) == 1
    body = json.loads(puts[0]["body"])
    assert body["greeting"] == "Hi from Acme"


def test_admin_page_theme_invalid_disables_save(_patch_http):
    """T044: typing invalid JSON into theme textarea disables Save."""
    at = AppTest.from_file("tests/integration/_admin_widget_page_entry.py")
    at.run(timeout=10)

    at.text_area(key="widget_config_theme_text").set_value("not json {{{")
    at.run(timeout=10)
    assert not at.exception

    # Save button should be disabled — clicking it issues no PUT.
    save_button = at.button(key="save_widget_config")
    assert save_button.disabled is True

    # Visible inline error.
    error_text = " ".join(e.value for e in at.error)
    assert "Theme JSON is invalid" in error_text

    # No PUT was made.
    puts = [c for c in _patch_http["calls"] if c["method"] == "PUT"]
    assert puts == []
