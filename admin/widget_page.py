# Owner: Amer
"""Tenant-admin widget configuration page.

Feature 004 — see specs/004-widget-admin-config/.

Renders the editor for allowed origins, theme JSON, greeting, and enabled flag.
Reads and writes via the FastAPI backend at GET/PUT /widgets/config.
"""

from __future__ import annotations

import copy
import json
import os
from typing import Any
from urllib.parse import urlsplit

import httpx
import streamlit as st

from admin._admin_http import http_client as _http_client

# Allow-listed theme keys (research.md R4). Anything else triggers an inline
# validation error and disables Save — tenants cannot smuggle arbitrary CSS
# through the theme blob.
ALLOWED_THEME_KEYS: frozenset[str] = frozenset(
    {"primary_color", "text_color", "bubble_color", "border_radius"}
)

# WCAG 2.x AA body-text contrast minimum.
_WCAG_AA_RATIO = 4.5
# Panel background the contrast check is computed against (matches the
# widget's default panel surface).
_PANEL_BG_HEX = "#ffffff"


def _fetch_config() -> dict[str, Any] | None:
    try:
        with _http_client() as client:
            resp = client.get("/widgets/config")
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    return resp.json()


# PUT /widgets/config accepts only these fields (WidgetConfigUpdateRequest uses
# extra='forbid'). widget_id comes back on GET but is not settable; sending it
# returns 422.
_PUT_FIELDS = ("allowed_origins", "enabled", "theme_json", "greeting")


def _save_config(draft: dict[str, Any]) -> tuple[int, Any]:
    payload = {k: draft.get(k) for k in _PUT_FIELDS}
    try:
        with _http_client() as client:
            resp = client.put("/widgets/config", json=payload)
    except httpx.HTTPError:
        return 0, "transport error"
    try:
        body = resp.json()
    except ValueError:
        body = resp.text
    return resp.status_code, body


def _validate_theme_keys(parsed: dict[str, Any]) -> list[str]:
    """Return the list of disallowed keys present in a parsed theme object."""
    return sorted(k for k in parsed.keys() if k not in ALLOWED_THEME_KEYS)


def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    s = value.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        return None
    try:
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
    except ValueError:
        return None
    return r, g, b


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(c: int) -> float:
        srgb = c / 255.0
        return srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(fg_hex: str, bg_hex: str) -> float | None:
    fg = _hex_to_rgb(fg_hex)
    bg = _hex_to_rgb(bg_hex)
    if fg is None or bg is None:
        return None
    l_fg = _relative_luminance(fg)
    l_bg = _relative_luminance(bg)
    lighter, darker = (l_fg, l_bg) if l_fg >= l_bg else (l_bg, l_fg)
    return (lighter + 0.05) / (darker + 0.05)


def _theme_contrast_ok(parsed: dict[str, Any]) -> bool:
    """True when ``primary_color`` (if present) meets WCAG AA against panel bg."""
    primary = parsed.get("primary_color")
    if not isinstance(primary, str) or not primary.strip():
        return True
    ratio = _contrast_ratio(primary, _PANEL_BG_HEX)
    if ratio is None:
        return True
    return ratio >= _WCAG_AA_RATIO


def contrast_fallback_warning(parsed: dict[str, Any]) -> str | None:
    """Return a user-facing contrast-fallback warning, or None if the theme passes."""
    if _theme_contrast_ok(parsed):
        return None
    return (
        "Contrast fallback: the chosen primary color does not meet WCAG AA "
        "(4.5:1) against the widget panel background. The widget will fall "
        "back to its built-in accent until a higher-contrast color is chosen."
    )


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
        if _validate_theme_keys(parsed):
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

    # --- Theme (friendly designer + raw-JSON escape hatch) ---
    st.subheader("Theme")
    st.caption(
        "Pick the colors your visitors will see. Changes preview below; saved "
        "themes apply on the next visitor mount."
    )
    st.markdown("_Live preview updates as you change the colors._")

    saved_theme: dict[str, Any] = saved.get("theme_json") or {}

    # Seed each designer control once from the saved theme (or sensible defaults).
    for key, default in (
        ("theme_primary", saved_theme.get("primary_color") or "#0066cc"),
        ("theme_text_color", saved_theme.get("text_color") or "#1a1a1a"),
        ("theme_bubble", saved_theme.get("bubble_color") or "#e8f0fe"),
        ("theme_radius", int(saved_theme.get("border_radius") or 12)),
        ("theme_use_defaults", not bool(saved_theme)),
    ):
        if key not in st.session_state:
            st.session_state[key] = default

    use_defaults = st.checkbox(
        "Use the widget's built-in colors (no custom theme)",
        key="theme_use_defaults",
        help="Tick this if you don't want to override the widget's defaults.",
    )

    if not use_defaults:
        c1, c2, c3 = st.columns(3)
        primary = c1.color_picker("Buttons & launcher", key="theme_primary")
        text_color = c2.color_picker("Message text", key="theme_text_color")
        bubble = c3.color_picker("Assistant bubble", key="theme_bubble")
        radius = st.slider("Corner roundness (px)", 0, 24, key="theme_radius")

        # Live preview — non-technical at-a-glance check.
        st.markdown("**Live preview**")
        st.markdown(
            f'<div style="display:flex; gap:12px; align-items:center;'
            f' margin:12px 0; padding:14px; background:#f6f7f9;'
            f' border-radius:8px; font-family:-apple-system,Segoe UI,Roboto,sans-serif;">'
            f'<div style="background:{primary}; width:96px; height:36px;'
            f' border-radius:{radius}px; color:#fff; display:flex;'
            f' align-items:center; justify-content:center; font-weight:500;">Chat</div>'
            f'<div style="background:{bubble}; color:{text_color};'
            f' padding:10px 14px; border-radius:{radius}px; max-width:300px;">'
            f'Hi! How can I help you today?</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Live contrast check on the primary color — friendly phrasing.
        ratio = _contrast_ratio(primary, _PANEL_BG_HEX)
        if ratio is not None and ratio < _WCAG_AA_RATIO:
            st.warning(
                f"Low contrast (your color is {ratio:.1f}:1 against the panel "
                f"background; WCAG AA needs 4.5:1). To keep the widget readable "
                "for everyone, it'll quietly fall back to its built-in accent "
                "color until you pick something stronger."
            )

        designer_theme: dict[str, Any] | None = {
            "primary_color": primary,
            "text_color": text_color,
            "bubble_color": bubble,
            "border_radius": int(radius),
        }
    else:
        designer_theme = None
        st.caption("→ Saving with this checked clears any custom theme.")

    draft["theme_json"] = designer_theme

    # Advanced escape hatch — kept so power users (and the test suite) can
    # still poke the raw JSON directly. When non-empty, the parsed JSON
    # overrides the designer.
    with st.expander("Advanced — edit raw theme JSON"):
        st.caption(
            "Optional: paste an allow-listed theme JSON object. When set here, "
            "it overrides the designer above."
        )
        theme_text = st.text_area(
            "Raw theme JSON",
            value=theme_text,
            height=140,
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
                    st.error(
                        "Theme must be a JSON object (not a scalar or array)."
                    )
                    parsed_theme = None
                else:
                    disallowed = _validate_theme_keys(parsed_theme)
                    if disallowed:
                        st.error(
                            "Theme JSON contains unknown keys: "
                            + ", ".join(disallowed)
                            + ". Allowed keys: "
                            + ", ".join(sorted(ALLOWED_THEME_KEYS))
                            + "."
                        )
                        parsed_theme = None
                    else:
                        fallback_msg = contrast_fallback_warning(parsed_theme)
                        if fallback_msg is not None:
                            st.warning(fallback_msg)
                        else:
                            st.success("Theme JSON is valid.")
            if parsed_theme is not None:
                draft["theme_json"] = parsed_theme

    # --- Embed snippet (T073) -----------------------------------------------
    st.subheader("Embed snippet")
    widget_id = saved.get("widget_id") or draft.get("widget_id") or "<widget-id>"
    backend_url = os.getenv("CONCIERGE_BACKEND_URL", "http://localhost:8000")
    snippet = (
        f'<script src="{backend_url}/widget.js" '
        f'data-widget-id="{widget_id}" '
        f'data-backend-url="{backend_url}" defer></script>'
    )
    st.code(snippet, language="html")
    st.caption(
        "Paste this on the website pages where you want the concierge to "
        "appear. The widget will load only on the origins you've allow-listed "
        "above."
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
