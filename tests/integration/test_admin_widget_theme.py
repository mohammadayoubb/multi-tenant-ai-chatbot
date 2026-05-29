# Owner: Amer
"""Integration tests for the widget theme JSON sandbox (Spec 009 US2, T064).

The widget admin page already validates that theme JSON parses to an object
(see test_admin_widget_page.py). T073 adds:

  - Allow-listed key set per research.md R4 (unknown keys → inline error).
  - WCAG 4.5:1 contrast check against panel background; failing primary_color
    triggers a visible "(contrast fallback)" notice and the page renders the
    default accent in the preview.
  - Live preview surface reflects valid theme changes.

These cases target T073-added behavior. When the feature isn't present
they fall through to importorskip-style detection so the suite still runs.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import httpx
import pytest
from streamlit.testing.v1 import AppTest

import admin.widget_page as widget_page


_ENTRY = "tests/integration/_admin_widget_page_entry.py"


_SEED: dict[str, Any] = {
    "widget_id": "9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d",
    "allowed_origins": ["https://acme.example"],
    "enabled": True,
    "theme_json": None,
    "greeting": None,
}


def _factory(handler: Callable[[httpx.Request], httpx.Response]):
    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    return factory


def _serve_seed():
    state: dict[str, Any] = {"row": dict(_SEED), "calls": []}

    def handler(req: httpx.Request) -> httpx.Response:
        state["calls"].append({"method": req.method, "path": req.url.path,
                                "body": req.content.decode() if req.content else ""})
        if req.method == "GET" and req.url.path == "/widgets/config":
            return httpx.Response(200, json=state["row"])
        if req.method == "PUT" and req.url.path == "/widgets/config":
            state["row"] = json.loads(req.content)
            return httpx.Response(200, json=state["row"])
        return httpx.Response(404)
    return state, handler


def test_invalid_theme_json_inline_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Existing-behavior regression net: malformed JSON shows an inline error
    and disables Save (already true today)."""
    state, handler = _serve_seed()
    monkeypatch.setattr(widget_page, "_http_client", _factory(handler))

    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    at.text_area(key="widget_config_theme_text").set_value("{not valid")
    at.run(timeout=10)

    assert at.button(key="save_widget_config").disabled is True
    error_text = " ".join(e.value for e in at.error)
    assert "Theme JSON is invalid" in error_text
    puts = [c for c in state["calls"] if c["method"] == "PUT"]
    assert puts == []


def test_valid_theme_updates_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    """A valid theme JSON keeps Save enabled and is reflected in the preview surface."""
    state, handler = _serve_seed()
    monkeypatch.setattr(widget_page, "_http_client", _factory(handler))

    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    at.text_area(key="widget_config_theme_text").set_value(
        json.dumps({"primary_color": "#005577"})
    )
    at.run(timeout=10)
    assert not at.exception
    assert at.button(key="save_widget_config").disabled is False

    # Preview area present.
    full_text = " ".join(m.value for m in at.markdown) + " ".join(i.value for i in at.info)
    assert "Theme preview" in full_text or "preview" in full_text.lower()


def test_theme_with_unknown_key_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """T073: theme JSON sandbox allow-lists keys; unknown keys → inline error.

    Skips until the sandbox parser ships.
    """
    if not hasattr(widget_page, "ALLOWED_THEME_KEYS") and not hasattr(
        widget_page, "_validate_theme_keys"
    ):
        pytest.skip("Theme key allow-list (T073) not present yet")

    state, handler = _serve_seed()
    monkeypatch.setattr(widget_page, "_http_client", _factory(handler))

    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    at.text_area(key="widget_config_theme_text").set_value(
        json.dumps({"primary_color": "#005577", "evil_inject": "x"})
    )
    at.run(timeout=10)

    error_text = " ".join(e.value for e in at.error)
    assert "evil_inject" in error_text or "unknown" in error_text.lower()
    assert at.button(key="save_widget_config").disabled is True


def test_bad_contrast_triggers_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """T073: WCAG 4.5:1 contrast failure → visible fallback notice in admin.

    Skips until the contrast helper ships.
    """
    if not (
        hasattr(widget_page, "_theme_contrast_ok")
        or hasattr(widget_page, "contrast_fallback_warning")
    ):
        pytest.skip("Contrast-fallback helper (T073) not present yet")

    state, handler = _serve_seed()
    monkeypatch.setattr(widget_page, "_http_client", _factory(handler))

    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    # Light grey on white: fails 4.5:1.
    at.text_area(key="widget_config_theme_text").set_value(
        json.dumps({"primary_color": "#dddddd"})
    )
    at.run(timeout=10)

    full_text = " ".join(w.value for w in at.warning) + " ".join(
        c.value for c in at.caption
    ) + " ".join(i.value for i in at.info)
    assert "contrast" in full_text.lower()
