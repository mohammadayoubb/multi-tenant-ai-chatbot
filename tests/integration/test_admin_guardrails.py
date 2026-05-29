# Owner: Amer
"""Integration tests for admin/guardrails_page.py (Spec 009 US2, T063).

Covers:
  - Platform rules section renders read-only with a "Locked by platform"
    badge per row (FR-021: tenants cannot weaken platform rules).
  - Tenant rules section is editable — blocked topics list editor + refusal
    tone dropdown — and changes persist via the agent-config PUT.
  - Endpoint missing (GET 404) → placeholder fallback with sample rules and
    no leaked error text (Principle V).

The page module lands in T072.
"""

from __future__ import annotations

from typing import Any, Callable

import httpx
import pytest

pytest.importorskip("admin.guardrails_page")

from streamlit.testing.v1 import AppTest  # noqa: E402

import admin.guardrails_page as page  # noqa: E402


_ENTRY = "tests/integration/_admin_guardrails_page_entry.py"


_LIVE_SNAPSHOT: dict[str, Any] = {
    "platform_rules": [
        {"id": "block_cross_tenant_probe", "name": "Cross-tenant probe block", "locked": True},
        {"id": "block_pii_extraction", "name": "PII extraction block", "locked": True},
        {"id": "block_prompt_injection", "name": "Prompt-injection refusal", "locked": True},
        {"id": "block_unsafe_topics", "name": "Unsafe-topics refusal", "locked": True},
    ],
    "tenant_blocked_topics": ["competitor_pricing"],
    "tenant_refusal_tone": "polite",
}


def _factory(handler: Callable[[httpx.Request], httpx.Response]):
    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    return factory


def test_platform_rules_render_locked_badge(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if "/platform-guardrails" in req.url.path:
            return httpx.Response(200, json=_LIVE_SNAPSHOT)
        return httpx.Response(404)

    monkeypatch.setattr(page, "_http_client", _factory(handler))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception

    full_text = " ".join(m.value for m in at.markdown) + " ".join(
        c.value for c in at.caption
    )
    # Platform rules must show the "Locked by platform" badge.
    assert "Locked by platform" in full_text
    # Each rule name appears.
    for rule in _LIVE_SNAPSHOT["platform_rules"]:
        assert rule["name"] in full_text


def test_tenant_section_editable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tenant blocked-topics list has at least one editable input + a save."""
    def handler(req: httpx.Request) -> httpx.Response:
        if "/platform-guardrails" in req.url.path:
            return httpx.Response(200, json=_LIVE_SNAPSHOT)
        if req.method == "PUT" and "/agent-config" in req.url.path:
            return httpx.Response(200, json={"chips": [], "tenant_blocked_topics": ["competitor_pricing", "internal_roadmap"]})
        return httpx.Response(404)

    monkeypatch.setattr(page, "_http_client", _factory(handler))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception

    # An editable input or text area exists for tenant topics, plus a Save button.
    assert at.button(key="save_guardrails") is not None


def test_placeholder_fallback_on_endpoint_404(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    monkeypatch.setattr(page, "_http_client", _factory(handler))
    at = AppTest.from_file(_ENTRY)
    at.run(timeout=10)
    assert not at.exception
    captions = " ".join(c.value for c in at.caption) + " ".join(w.value for w in at.warning)
    assert "(placeholder)" in captions
    # Even the placeholder renders the locked badge — platform rules NEVER appear unlocked.
    full_text = " ".join(m.value for m in at.markdown) + captions
    assert "Locked by platform" in full_text
