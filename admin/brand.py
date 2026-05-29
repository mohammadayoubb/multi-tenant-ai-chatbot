# Owner: Amer
"""Shared Concierge AI branding for the admin auth screens.

The login and accept-invite pages share a centered-card SaaS layout. Putting
the CSS + brand header in one helper keeps the two pages visually identical
and avoids per-page drift when product wants the wordmark or accent color
changed in one place.
"""

from __future__ import annotations

import streamlit as st

PRODUCT_NAME = "Concierge AI"
PRODUCT_TAGLINE = (
    "Manage your AI concierge, widget, leads, and customer "
    "conversations in one place."
)

# Shared design tokens consumed by the admin helpers (`_table`, `_kpi`,
# `_status_pill`, `_empty`). Streamlit doesn't have CSS variables we can rely
# on, so we keep the palette + spacing scale in one Python dict per family.
COLORS = {
    "bg": "#ffffff",
    "surface": "#ffffff",
    "surface_alt": "#f8fafc",
    "border": "#e6e8eb",
    "text": "#0f172a",
    "text_muted": "#475569",
    "text_soft": "#64748b",
    "brand": "#2563eb",
    "brand_hover": "#1d4ed8",
    "success": "#16a34a",
    "success_bg": "#dcfce7",
    "warn": "#d97706",
    "warn_bg": "#fef3c7",
    "danger": "#dc2626",
    "danger_bg": "#fee2e2",
    "info": "#0ea5e9",
    "info_bg": "#e0f2fe",
    "neutral": "#64748b",
    "neutral_bg": "#f1f5f9",
}

SPACING = {
    "1": "0.25rem",
    "2": "0.5rem",
    "3": "0.75rem",
    "4": "1rem",
    "5": "1.25rem",
    "6": "1.5rem",
}

RADIUS = {
    "sm": "6px",
    "md": "10px",
    "lg": "14px",
    "pill": "999px",
}

_CARD_CSS = """
<style>
section.main > div.block-container {
    max-width: 480px;
    padding-top: 4rem;
}
div[data-testid="stForm"] {
    background: #ffffff;
    border: 1px solid #e6e8eb;
    border-radius: 12px;
    padding: 1.5rem 1.75rem;
    box-shadow: 0 4px 14px rgba(15, 23, 42, 0.06);
}
.concierge-brand {
    text-align: center;
    margin-bottom: 1.5rem;
}
.concierge-brand h1 {
    margin: 0 0 0.25rem 0;
    font-size: 1.85rem;
    letter-spacing: -0.01em;
}
.concierge-brand p {
    margin: 0;
    color: #475569;
    font-size: 0.95rem;
    line-height: 1.4;
}
.concierge-footer {
    text-align: center;
    margin-top: 1rem;
    color: #64748b;
    font-size: 0.85rem;
}
.concierge-footer a {
    color: #2563eb;
    text-decoration: none;
}
</style>
"""


def render_card_chrome() -> None:
    """Inject the card CSS + centered Concierge AI header.

    Call this at the top of every auth screen so login + accept-invite share
    the same visual chrome.
    """
    st.markdown(_CARD_CSS, unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="concierge-brand">
          <h1>{PRODUCT_NAME}</h1>
          <p>{PRODUCT_TAGLINE}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
