# Owner: Amer
"""Shared Streamlit status-pill helper.

A status badge is a tiny inline colored capsule. Streamlit has no first-class
badge component, so we render an inline HTML span styled from the brand
palette. Kinds map a value to a color family.
"""

from __future__ import annotations

import html

import streamlit as st

from admin.brand import COLORS, RADIUS

# Kind -> { value (lowercased) -> (bg, fg) }
_KIND_PALETTE: dict[str, dict[str, tuple[str, str]]] = {
    "tenant": {
        "active": (COLORS["success_bg"], COLORS["success"]),
        "suspended": (COLORS["warn_bg"], COLORS["warn"]),
        "deleted": (COLORS["danger_bg"], COLORS["danger"]),
    },
    "lead": {
        "new": (COLORS["info_bg"], COLORS["info"]),
        "contacted": (COLORS["neutral_bg"], COLORS["neutral"]),
        "qualified": (COLORS["success_bg"], COLORS["success"]),
        "closed": (COLORS["neutral_bg"], COLORS["neutral"]),
    },
    "ticket": {
        "open": (COLORS["warn_bg"], COLORS["warn"]),
        "in_progress": (COLORS["info_bg"], COLORS["info"]),
        "resolved": (COLORS["success_bg"], COLORS["success"]),
        "closed": (COLORS["neutral_bg"], COLORS["neutral"]),
    },
    "invite": {
        "pending": (COLORS["warn_bg"], COLORS["warn"]),
        "used": (COLORS["success_bg"], COLORS["success"]),
        "expired": (COLORS["neutral_bg"], COLORS["neutral"]),
        "revoked": (COLORS["danger_bg"], COLORS["danger"]),
    },
}

_FALLBACK: tuple[str, str] = (COLORS["neutral_bg"], COLORS["neutral"])


def render_status(value: str, *, kind: str) -> None:
    """Render an inline colored status badge.

    Args:
        value: the status string (case-insensitive lookup).
        kind: one of ``tenant`` | ``lead`` | ``ticket`` | ``invite``. Unknown
            kinds and unknown values both fall back to a neutral slate badge.
    """
    palette = _KIND_PALETTE.get(kind, {})
    bg, fg = palette.get(value.lower(), _FALLBACK)
    safe_value = html.escape(str(value))
    st.markdown(
        f'<span style="display:inline-block;'
        f"padding:2px 10px;"
        f"border-radius:{RADIUS['pill']};"
        f"background:{bg};color:{fg};"
        f'font-size:0.78rem;font-weight:600;letter-spacing:0.02em;">'
        f"{safe_value}"
        f"</span>",
        unsafe_allow_html=True,
    )
