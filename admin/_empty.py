# Owner: Amer
"""Shared Streamlit empty-state helper.

`render_empty_state` is the single empty-state surface every admin table
falls back to when its row list is empty. Centralized so the visual
language stays consistent across CMS, Leads, Escalations, Tenants, Invites.
"""

from __future__ import annotations

import html

import streamlit as st

from admin.brand import COLORS, RADIUS


def render_empty_state(
    title: str,
    message: str,
    *,
    primary_cta: tuple[str, str] | None = None,
) -> None:
    """Render an empty-state card with optional primary CTA.

    Args:
        title: short headline (one short sentence).
        message: longer supporting sentence.
        primary_cta: optional ``(label, url)`` tuple. The link opens in the
            same tab (`target=_self`). For action-style CTAs that need a
            callback, render an `st.button` next to this helper instead.
    """
    safe_title = html.escape(title)
    safe_message = html.escape(message)
    cta_html = ""
    if primary_cta is not None:
        label, url = primary_cta
        cta_html = (
            f'<a href="{html.escape(url)}" target="_self" '
            f'style="display:inline-block;margin-top:0.75rem;'
            f"padding:0.4rem 0.9rem;border-radius:{RADIUS['md']};"
            f"background:{COLORS['brand']};color:#fff;font-weight:600;"
            f'text-decoration:none;font-size:0.85rem;">{html.escape(label)}</a>'
        )
    st.markdown(
        f'<div style="padding:1.5rem;text-align:center;'
        f"background:{COLORS['surface_alt']};"
        f"border:1px dashed {COLORS['border']};"
        f"border-radius:{RADIUS['lg']};"
        f'color:{COLORS["text_muted"]};">'
        f'<div style="font-weight:600;color:{COLORS["text"]};font-size:1rem;'
        f'margin-bottom:0.35rem;">{safe_title}</div>'
        f'<div style="font-size:0.88rem;">{safe_message}</div>'
        f"{cta_html}"
        f"</div>",
        unsafe_allow_html=True,
    )
