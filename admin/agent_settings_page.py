# Owner: Amer
"""Tenant Agent settings admin page (Spec 009 US2, T071).

Edits the per-tenant agent persona, greeting, tone, language, business rules
and visitor quick-action chips. Reads `GET /tenants/{tid}/agent-config`
(T039a) and saves through `PUT /tenants/{tid}/agent-config`. The page mirrors
the server's `chips` validation (0..6 entries, each 1..40 chars) so the Save
button disables before a known-bad payload leaves the browser; the server
remains the source of truth.

If the endpoint isn't yet shipped (GET 404 / transport error), the page
degrades to product-default values with a visible "(placeholder)" caption —
no raw exception text is surfaced (Principle V / FR-013).
"""

from __future__ import annotations

import copy
from typing import Any

import httpx
import streamlit as st

from admin._admin_http import http_client as _http_client, signed_in_tenant_id
from admin.auth_state import get_tenant_id

_TONE_OPTIONS = ["professional", "friendly", "casual", "formal", "concierge"]
_LANGUAGE_OPTIONS = ["en", "es", "fr", "de", "ar", "pt", "ja", "zh"]

_DEFAULT_CONFIG: dict[str, Any] = {
    "persona_name": "",
    "greeting": "Hi! How can I help?",
    "tone": "professional",
    "language": "en",
    "business_rules": "",
    "chips": ["Pricing", "Hours", "Talk to a human", "Get a quote"],
    "tenant_blocked_topics": [],
    "tenant_refusal_tone": "polite",
}

_MAX_CHIPS = 6
_MAX_CHIP_LEN = 40
_GENERIC_FORBIDDEN = "You do not have permission for that action."
_GENERIC_FAILED = "Save failed; please retry."


def _agent_config_url() -> str:
    return f"/tenants/{signed_in_tenant_id()}/agent-config"


def _fetch_config() -> tuple[dict[str, Any], bool]:
    """Return ``(config, is_placeholder)``."""
    try:
        with _http_client() as client:
            resp = client.get(_agent_config_url())
    except httpx.HTTPError:
        return copy.deepcopy(_DEFAULT_CONFIG), True
    if resp.status_code < 200 or resp.status_code >= 300:
        return copy.deepcopy(_DEFAULT_CONFIG), True
    try:
        body = resp.json()
    except ValueError:
        return copy.deepcopy(_DEFAULT_CONFIG), True
    if not isinstance(body, dict):
        return copy.deepcopy(_DEFAULT_CONFIG), True
    merged = copy.deepcopy(_DEFAULT_CONFIG)
    for key, value in body.items():
        if key in merged:
            merged[key] = value
    return merged, False


def _put_config(payload: dict[str, Any]) -> tuple[int, Any]:
    try:
        with _http_client() as client:
            resp = client.put(_agent_config_url(), json=payload)
    except httpx.HTTPError:
        return 0, None
    try:
        body = resp.json()
    except ValueError:
        body = None
    return resp.status_code, body


def _parse_chips(raw: str) -> list[str]:
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _chips_locally_valid(chips: list[str]) -> bool:
    if len(chips) > _MAX_CHIPS:
        return False
    for chip in chips:
        if not (1 <= len(chip) <= _MAX_CHIP_LEN):
            return False
    return True


def render() -> None:
    config, placeholder = _fetch_config()
    if placeholder:
        st.caption("(placeholder)")

    persona = st.text_input(
        "Persona name", value=config.get("persona_name", ""), key="persona_input"
    )
    greeting = st.text_input(
        "Greeting", value=config.get("greeting", ""), key="greeting_input"
    )
    tone_options = list(_TONE_OPTIONS)
    current_tone = config.get("tone") or _TONE_OPTIONS[0]
    if current_tone not in tone_options:
        tone_options = [current_tone, *tone_options]
    tone = st.selectbox(
        "Tone",
        tone_options,
        index=tone_options.index(current_tone),
        key="tone_input",
    )
    lang_options = list(_LANGUAGE_OPTIONS)
    current_lang = config.get("language") or _LANGUAGE_OPTIONS[0]
    if current_lang not in lang_options:
        lang_options = [current_lang, *lang_options]
    language = st.selectbox(
        "Language",
        lang_options,
        index=lang_options.index(current_lang),
        key="language_input",
    )
    business_rules = st.text_area(
        "Business rules",
        value=config.get("business_rules", ""),
        key="business_rules_input",
        height=150,
    )

    st.markdown("##### Quick-action chips")
    st.caption(
        f"One chip per line — up to {_MAX_CHIPS} chips, each 1..{_MAX_CHIP_LEN} characters."
    )
    chips_default = "\n".join(config.get("chips") or [])
    chips_raw = st.text_area(
        "Chips",
        value=chips_default,
        key="chips_input",
        height=160,
    )
    chips = _parse_chips(chips_raw)
    chips_ok = _chips_locally_valid(chips)
    if not chips_ok:
        if len(chips) > _MAX_CHIPS:
            st.error(
                f"chips: too many entries (got {len(chips)}, max {_MAX_CHIPS})."
            )
        else:
            st.error(
                f"chips: each entry must be 1..{_MAX_CHIP_LEN} characters."
            )

    save_disabled = placeholder or not chips_ok
    save_clicked = st.button(
        "Save", type="primary", disabled=save_disabled, key="save_agent_config"
    )

    if save_clicked:
        payload = {
            "persona_name": persona.strip(),
            "greeting": greeting,
            "tone": tone,
            "language": language,
            "business_rules": business_rules,
            "chips": chips,
            "tenant_blocked_topics": list(config.get("tenant_blocked_topics") or []),
            "tenant_refusal_tone": config.get("tenant_refusal_tone")
            or _DEFAULT_CONFIG["tenant_refusal_tone"],
        }
        status_code, body = _put_config(payload)
        if status_code in (200, 204):
            st.success("Saved.")
            st.rerun()
        elif status_code == 422:
            detail = body.get("detail") if isinstance(body, dict) else None
            if isinstance(detail, str):
                st.error(f"Save rejected: {detail}")
            elif isinstance(detail, list):
                st.error("Save rejected (validation failed):")
                for err in detail:
                    if isinstance(err, dict):
                        loc = ".".join(str(p) for p in err.get("loc", []) if p)
                        msg = err.get("msg", "")
                        st.write(f"- `{loc}`: {msg}")
            else:
                st.error("Save rejected: chips validation failed.")
        elif status_code == 403:
            st.error(_GENERIC_FORBIDDEN)
        else:
            st.error(_GENERIC_FAILED)


__all__ = ["render"]


# Surface tenant id reads (kept here so monkeypatchers can shim if needed).
_ = get_tenant_id
