# Owner: Amer
"""TM Platform Settings admin page (Spec 009 US3, T088).

Edits the non-sensitive platform-scope defaults that live in
``tenant_settings`` (Phase 2A migration 0006):

  - default invite TTL (seconds, 3600 .. 30·24·3600)
  - rate-limit chat per minute (1 .. 1000)
  - rate-limit token per minute (1 .. 1000)

Persists through ``PUT /tenants/{tid}/settings`` (T039n) which gates writes
to the ``tenant_manager`` role and emits a ``tenant_settings_updated`` audit
event with redacted metadata.

The page targets the signed-in TM's own tenant — the path tenant id is
derived from session state, never from a form field (Principle I). A
confirmation modal is required before any save commits.
"""

from __future__ import annotations

from typing import Any

import httpx
import streamlit as st

from admin._admin_http import http_client as _http_client, signed_in_tenant_id

_GENERIC_FAILED = "Failed to update settings; please retry."
_GENERIC_FORBIDDEN = "Forbidden — your role cannot perform that action."
_GENERIC_INVALID = "Some values are out of range; check the form and retry."

_DEFAULTS = {
    "default_invite_ttl_seconds": 7 * 24 * 3600,
    "rate_limit_chat_per_minute": 30,
    "rate_limit_token_per_minute": 60,
}

_TTL_MIN = 3600
_TTL_MAX = 30 * 24 * 3600
_RATE_MIN = 1
_RATE_MAX = 1000


def _put_settings(payload: dict[str, Any]) -> int:
    try:
        with _http_client() as client:
            resp = client.put(
                f"/tenants/{signed_in_tenant_id()}/settings", json=payload
            )
    except httpx.HTTPError:
        return 0
    return resp.status_code


def _surface(status_code: int) -> None:
    if status_code == 403:
        st.error(_GENERIC_FORBIDDEN)
    elif status_code == 422:
        st.error(_GENERIC_INVALID)
    else:
        st.error(_GENERIC_FAILED)


def render() -> None:
    st.markdown("#### Platform defaults")
    st.caption(
        "Edits apply to your tenant scope. Out-of-range values are rejected "
        "server-side; the canonical bounds are shown next to each input."
    )

    ttl_default = int(
        st.session_state.get(
            "settings_default_invite_ttl_seconds",
            _DEFAULTS["default_invite_ttl_seconds"],
        )
    )
    chat_default = int(
        st.session_state.get(
            "settings_rate_limit_chat_per_minute",
            _DEFAULTS["rate_limit_chat_per_minute"],
        )
    )
    token_default = int(
        st.session_state.get(
            "settings_rate_limit_token_per_minute",
            _DEFAULTS["rate_limit_token_per_minute"],
        )
    )

    # Confirmation lives OUTSIDE the form on purpose. Streamlit batches form
    # widget interactions until submit, so a checkbox inside the form would
    # never re-trigger a rerun to flip `disabled=not confirm` on the submit
    # button — the user would be permanently locked out.
    confirm = st.checkbox(
        "I confirm these settings apply across the tenant immediately.",
        key="tm_settings_confirm",
    )

    with st.form("tm_settings_form"):
        ttl = st.number_input(
            f"Default invite TTL (seconds) — between {_TTL_MIN} and {_TTL_MAX}",
            min_value=_TTL_MIN,
            max_value=_TTL_MAX,
            value=ttl_default,
            step=3600,
            key="tm_settings_ttl",
        )
        chat = st.number_input(
            f"Chat rate limit (per minute) — between {_RATE_MIN} and {_RATE_MAX}",
            min_value=_RATE_MIN,
            max_value=_RATE_MAX,
            value=chat_default,
            step=1,
            key="tm_settings_chat",
        )
        token = st.number_input(
            f"Token rate limit (per minute) — between {_RATE_MIN} and {_RATE_MAX}",
            min_value=_RATE_MIN,
            max_value=_RATE_MAX,
            value=token_default,
            step=1,
            key="tm_settings_token",
        )
        if not confirm:
            st.caption("Tick the confirmation checkbox above to enable Save.")
        submitted = st.form_submit_button(
            "Save settings", type="primary", disabled=not confirm
        )

    if not submitted:
        return
    if not confirm:
        st.warning("Confirmation required before saving.")
        return
    payload = {
        "default_invite_ttl_seconds": int(ttl),
        "rate_limit_chat_per_minute": int(chat),
        "rate_limit_token_per_minute": int(token),
    }
    with st.spinner("Saving…"):
        status_code = _put_settings(payload)
    if status_code == 200:
        st.session_state["settings_default_invite_ttl_seconds"] = int(ttl)
        st.session_state["settings_rate_limit_chat_per_minute"] = int(chat)
        st.session_state["settings_rate_limit_token_per_minute"] = int(token)
        st.success("Settings saved.")
    else:
        _surface(status_code)
