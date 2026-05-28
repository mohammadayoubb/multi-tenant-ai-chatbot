# Owner: Amer
"""Tenant-admin widget configuration page.

Feature 004 — see specs/004-widget-admin-config/.

Renders the editor for allowed origins, theme JSON, greeting, and enabled flag.
Reads and writes via the FastAPI backend at GET/PUT /widgets/config.
"""

from __future__ import annotations

import copy
import json
from typing import Any
from urllib.parse import urlsplit

import httpx
import streamlit as st

from admin._admin_http import backend_url as _backend_url
from admin._admin_http import http_client as _http_client


def _fetch_config() -> dict[str, Any] | None:
    try:
        with _http_client() as client:
            resp = client.get("/widgets/config")
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    return resp.json()


def _save_config(draft: dict[str, Any]) -> tuple[int, Any]:
    try:
        with _http_client() as client:
            resp = client.put("/widgets/config", json=draft)
    except httpx.HTTPError:
        return 0, "transport error"
    try:
        body = resp.json()
    except ValueError:
        body = resp.text
    return resp.status_code, body


def _origin_locally_valid(raw: str) -> bool:
    """Client-side pre-validation only (server is the source of truth)."""
    try:
        parts = urlsplit(raw.strip())
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.hostname)


def _draft_is_valid(draft: dict[str, Any], theme_text: str) -> bool:
    """All-fields validity check used to enable/disable the Save button (FR-017)."""
    # Origins: each must look like a valid URL locally.
    for origin in draft.get("allowed_origins", []):
        if not _origin_locally_valid(origin):
            return False
    # Greeting length.
    greeting = draft.get("greeting") or ""
    if len(greeting) > 280:
        return False
    # Theme JSON parseable (and an object) or empty.
    if theme_text.strip():
        try:
            parsed = json.loads(theme_text)
        except json.JSONDecodeError:
            return False
        if not isinstance(parsed, dict):
            return False
    # Enabled + empty origins.
    if draft.get("enabled") and not draft.get("allowed_origins"):
        return False
    return True


def _seed_theme_text_from_saved() -> None:
    saved_theme = st.session_state["widget_config_saved"].get("theme_json")
    st.session_state["widget_config_theme_text"] = (
        json.dumps(saved_theme, indent=2) if saved_theme else ""
    )


def render() -> None:
    """Render the admin Widget page."""
    # Three independent init guards so refresh / discard / save flows can clear
    # individual keys and let the next rerun re-seed them.
    if "widget_config_saved" not in st.session_state:
        fetched = _fetch_config()
        if fetched is None:
            st.error(
                "Could not load widget configuration. Confirm the backend is "
                "running at the configured CONCIERGE_BACKEND_URL and that your "
                "admin role is set up."
            )
            return
        st.session_state["widget_config_saved"] = fetched

    if "widget_config_draft" not in st.session_state:
        st.session_state["widget_config_draft"] = copy.deepcopy(
            st.session_state["widget_config_saved"]
        )

    # Seed the theme textarea's session_state key BEFORE the widget runs.
    if "widget_config_theme_text" not in st.session_state:
        _seed_theme_text_from_saved()

    draft: dict[str, Any] = st.session_state["widget_config_draft"]
    saved: dict[str, Any] = st.session_state["widget_config_saved"]
    theme_text: str = st.session_state["widget_config_theme_text"]

    # --- Unsaved-changes indicator (FR-016) ---
    is_dirty = (
        draft != saved
        or theme_text.strip() != (
            json.dumps(saved.get("theme_json") or {}, indent=2)
            if saved.get("theme_json") is not None
            else ""
        )
    )
    if is_dirty:
        st.markdown("● **Unsaved changes**")
        if st.button("Discard changes"):
            # Clear; the init guards above will re-seed from saved on rerun.
            del st.session_state["widget_config_draft"]
            del st.session_state["widget_config_theme_text"]
            st.rerun()
    else:
        st.markdown("✓ All changes saved")

    # --- Allowed origins editor (US1) ---
    st.subheader("Allowed origins")
    new_origins: list[str] = []
    for idx, origin in enumerate(draft["allowed_origins"]):
        cols = st.columns([6, 1])
        cols[0].text(origin)
        if cols[1].button("Remove", key=f"remove_origin_{idx}"):
            keep = [o for j, o in enumerate(draft["allowed_origins"]) if j != idx]
            draft["allowed_origins"] = keep
            st.rerun()
        new_origins.append(origin)

    add_input = st.text_input(
        "Add origin (https://example.com)", key="add_origin_input"
    )
    if st.button("Add origin", key="add_origin_button"):
        candidate = add_input.strip()
        if not _origin_locally_valid(candidate):
            st.error(
                "Origin must be a valid http(s) URL with a host (e.g., "
                "https://example.com)."
            )
        elif candidate in draft["allowed_origins"]:
            st.warning("That origin is already in the list.")
        else:
            draft["allowed_origins"] = draft["allowed_origins"] + [candidate]
            st.rerun()

    # --- Greeting + enabled (US2) ---
    st.subheader("Greeting")
    draft["greeting"] = st.text_input(
        "Greeting (max 280 chars)",
        value=draft.get("greeting") or "",
        max_chars=280,
        key="greeting_input",
    )
    st.caption(f"{len(draft.get('greeting') or '')} / 280 characters")

    st.subheader("Enabled")
    draft["enabled"] = st.toggle(
        "Widget enabled",
        value=bool(draft.get("enabled")),
        key="enabled_toggle",
    )
    if draft["enabled"] and not draft["allowed_origins"]:
        st.warning(
            "Enabled widgets must have at least one allowed origin. Add an "
            "origin or toggle Enabled off before saving."
        )

    # --- Theme (US3) ---
    st.subheader("Theme (free-form JSON object)")
    theme_text = st.text_area(
        "Theme JSON",
        value=theme_text,
        height=180,
        key="widget_config_theme_text",
    )
    if theme_text.strip():
        try:
            parsed_theme = json.loads(theme_text)
        except json.JSONDecodeError as exc:
            st.error(f"Theme JSON is invalid: {exc.msg} (line {exc.lineno}).")
            parsed_theme = None
        else:
            if not isinstance(parsed_theme, dict):
                st.error("Theme must be a JSON object (not a scalar or array).")
                parsed_theme = None
            else:
                st.success("Theme JSON is valid.")
    else:
        parsed_theme = None
    draft["theme_json"] = parsed_theme

    # --- Theme preview (US3 stretch goal) ---
    st.subheader("Theme preview")
    st.info(
        "Theme preview: the saved theme will apply on next visitor mount. "
        "Live preview lands together with the widget runtime's theme support "
        "in a later phase."
    )

    # --- Save controls (FR-016/017/018) ---
    is_valid = _draft_is_valid(draft, theme_text)
    save_clicked = st.button(
        "Save", type="primary", disabled=not is_valid, key="save_widget_config"
    )
    if save_clicked:
        status, body = _save_config(draft)
        if status == 200:
            # Replace the saved snapshot; clear draft + theme key so the init
            # guards reseed from the server response on the next rerun.
            st.session_state["widget_config_saved"] = body
            for k in ("widget_config_draft", "widget_config_theme_text"):
                if k in st.session_state:
                    del st.session_state[k]
            st.success("Saved.")
            st.rerun()
        elif status == 422:
            st.error("Save rejected (validation failed):")
            errors = body.get("detail") if isinstance(body, dict) else body
            if isinstance(errors, list):
                for err in errors:
                    loc = ".".join(str(p) for p in err.get("loc", []))
                    msg = err.get("msg", "")
                    st.write(f"- `{loc}`: {msg}")
            else:
                st.write(errors)
        elif status == 403:
            st.error("Save rejected: forbidden.")
        else:
            st.error("Save failed; please retry.")
