# Owner: Amer
"""Leads viewer admin page (read-only, redacted contact).

Feature 005 US3 — see specs/005-admin-read-only-pages/.

Renders captured leads with the contact column always redacted to the first
three characters plus a fixed "***" suffix (Principle V, FR-009). The
unredacted contact value is never written to logs, st.write, or any error
message. Any non-2xx response or transport error falls back to canned sample
data with a visible "(placeholder)" caption (FR-013).
"""

from __future__ import annotations

from typing import Any

import httpx
import streamlit as st

from admin._admin_http import http_client as _http_client

_STATUS_OPTIONS = ["all", "captured", "qualified", "spam"]

_SAMPLE_LEADS: list[dict[str, Any]] = [
    {
        "id": "sample-1",
        "created_at": "2026-05-20T10:00:00Z",
        "name": "Sample Captured",
        "contact": "sample-captured@example.com",
        "intent": "demo_request",
        "status": "captured",
        "quality_score": 0.5,
    },
    {
        "id": "sample-2",
        "created_at": "2026-05-19T10:00:00Z",
        "name": None,
        "contact": "+15550000001",
        "intent": "pricing_question",
        "status": "qualified",
        "quality_score": None,
    },
    {
        "id": "sample-3",
        "created_at": "2026-05-18T10:00:00Z",
        "name": "Sample Spam",
        "contact": "spam@spam.test",
        "intent": "unknown",
        "status": "spam",
        "quality_score": 0.05,
    },
]


def redact_contact(value: str | None) -> str:
    """Always render first 3 chars + literal '***' (research Decision 6)."""
    head = (value or "")[:3]
    return f"{head}***"


def _fetch_leads() -> tuple[list[dict[str, Any]], bool]:
    try:
        with _http_client() as client:
            resp = client.get("/leads")
    except httpx.HTTPError:
        return _SAMPLE_LEADS, True
    if resp.status_code < 200 or resp.status_code >= 300:
        return _SAMPLE_LEADS, True
    try:
        body = resp.json()
    except ValueError:
        return _SAMPLE_LEADS, True
    if not isinstance(body, list):
        return _SAMPLE_LEADS, True
    return body, False


def render() -> None:
    leads, placeholder = _fetch_leads()
    if placeholder:
        st.caption("(placeholder)")

    selected_status = st.selectbox(
        "Filter by status", _STATUS_OPTIONS, key="leads_status_filter"
    )
    if selected_status != "all":
        filtered = [lead for lead in leads if lead.get("status") == selected_status]
    else:
        filtered = list(leads)

    table = [
        {
            "created_at": lead.get("created_at", "—"),
            "name": lead.get("name") or "—",
            "contact": redact_contact(lead.get("contact")),
            "intent": lead.get("intent", "—"),
            "status": lead.get("status", "—"),
            "quality_score": (
                f"{lead['quality_score']:.4f}"
                if lead.get("quality_score") is not None
                else "—"
            ),
        }
        for lead in filtered
    ]
    st.dataframe(table, key="leads_table", width="stretch")
