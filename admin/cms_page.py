# Owner: Amer
"""CMS list admin page (read-only).

Feature 005 US2 — see specs/005-admin-read-only-pages/.

Lists CMS pages (title, slug, status, updated_at) with a client-side status
filter, plus a read-only detail viewer. Any non-2xx response or transport
error falls back to canned sample data with a visible "(placeholder)" caption.
"""

from __future__ import annotations

from typing import Any

import httpx
import streamlit as st

from admin._admin_http import http_client as _http_client

_STATUS_OPTIONS = ["all", "draft", "published", "archived"]

_SAMPLE_PAGES: list[dict[str, Any]] = [
    {
        "id": "sample-1",
        "title": "Sample published page",
        "slug": "sample-published",
        "body": "## Hello\n\nThis is sample CMS content shown when the backend is unreachable.",
        "source_url": "https://example.com/sample",
        "status": "published",
        "updated_at": "2026-05-20T10:00:00Z",
    },
    {
        "id": "sample-2",
        "title": "Sample draft page",
        "slug": "sample-draft",
        "body": "Draft body.",
        "source_url": None,
        "status": "draft",
        "updated_at": "2026-05-19T10:00:00Z",
    },
    {
        "id": "sample-3",
        "title": "Sample archived page",
        "slug": "sample-archived",
        "body": "Archived body.",
        "source_url": None,
        "status": "archived",
        "updated_at": "2026-04-01T10:00:00Z",
    },
]


def _fetch_pages() -> tuple[list[dict[str, Any]], bool]:
    """Return (pages, is_placeholder)."""
    try:
        with _http_client() as client:
            resp = client.get("/cms/pages")
    except httpx.HTTPError:
        return _SAMPLE_PAGES, True
    if resp.status_code < 200 or resp.status_code >= 300:
        return _SAMPLE_PAGES, True
    try:
        body = resp.json()
    except ValueError:
        return _SAMPLE_PAGES, True
    if not isinstance(body, list):
        return _SAMPLE_PAGES, True
    return body, False


def render() -> None:
    pages, placeholder = _fetch_pages()
    if placeholder:
        st.caption("(placeholder)")

    selected_status = st.selectbox(
        "Filter by status", _STATUS_OPTIONS, key="cms_status_filter"
    )
    if selected_status != "all":
        filtered = [p for p in pages if p.get("status") == selected_status]
    else:
        filtered = list(pages)

    table = [
        {
            "title": p.get("title", "—"),
            "slug": p.get("slug", "—"),
            "status": p.get("status", "—"),
            "updated_at": p.get("updated_at", "—"),
        }
        for p in filtered
    ]
    st.dataframe(table, key="cms_page_table", width="stretch")

    if not filtered:
        st.markdown("_No CMS pages match the selected filter._")
        return

    st.markdown("#### CMS page detail")
    options = [f"{p.get('title', '—')} — {p.get('slug', '—')}" for p in filtered]
    chosen = st.selectbox("Select page", options, key="cms_detail_select")
    detail = filtered[options.index(chosen)] if chosen in options else filtered[0]
    st.markdown(f"**Title:** {detail.get('title', '—')}")
    st.markdown(f"**Slug:** `{detail.get('slug', '—')}`")
    source_url = detail.get("source_url")
    if source_url:
        st.markdown(f"**Source:** [{source_url}]({source_url})")
    st.markdown("---")
    st.markdown(detail.get("body", ""))
