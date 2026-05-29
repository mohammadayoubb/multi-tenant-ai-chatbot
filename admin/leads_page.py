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

from admin._admin_http import http_client as _http_client, render_placeholder_caption
from admin._status_pill import render_status

_STATUS_OPTIONS = ["all", "captured", "qualified", "spam"]
_EDITABLE_STATUSES = ["captured", "qualified", "spam"]
_GENERIC_FORBIDDEN = "You do not have permission for that action."
_GENERIC_FAILED = "The request failed; please retry."
_PAGE_SIZE = 10

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


def _patch_lead_status(lead_id: str, new_status: str) -> int:
    try:
        with _http_client() as client:
            resp = client.patch(
                f"/leads/{lead_id}", json={"status": new_status}
            )
    except httpx.HTTPError:
        return 0
    return resp.status_code


_COL_WEIGHTS = [2, 2, 2, 3, 2, 2, 1, 1]
_COL_HEADERS = (
    "Created",
    "Name",
    "Contact",
    "Intent",
    "Status",
    "Change",
    "",
    "Score",
)


def _format_created_at(value: Any) -> str:
    text = str(value or "")
    if "T" in text:
        date_part, time_part = text.split("T", 1)
        return f"{date_part} {time_part[:5]}"
    return text or "—"


def render() -> None:
    leads, placeholder = _fetch_leads()
    if placeholder:
        render_placeholder_caption()

    # Reset to page 0 whenever the filter changes — without this, switching
    # from "all" to "qualified" can leave the user stranded on an empty page.
    prev_filter = st.session_state.get("_leads_prev_filter")
    selected_status = st.selectbox(
        "Filter by status", _STATUS_OPTIONS, key="leads_status_filter"
    )
    if prev_filter is not None and prev_filter != selected_status:
        st.session_state["leads_page_idx"] = 0
    st.session_state["_leads_prev_filter"] = selected_status

    if selected_status != "all":
        filtered = [lead for lead in leads if lead.get("status") == selected_status]
    else:
        filtered = list(leads)

    if not filtered:
        st.info(
            "No leads captured yet. They will appear here as visitors share "
            "their contact info with the agent."
        )
        return

    # FR-024: NO download / export control is rendered here — visitor PII
    # never leaves the admin surface.

    total = len(filtered)
    total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    current_page = int(st.session_state.get("leads_page_idx", 0))
    current_page = max(0, min(current_page, total_pages - 1))
    start = current_page * _PAGE_SIZE
    end = start + _PAGE_SIZE
    page_rows = filtered[start:end]

    # Column header row.
    header_cols = st.columns(_COL_WEIGHTS)
    for col, label in zip(header_cols, _COL_HEADERS):
        col.markdown(f"**{label}**")

    for lead in page_rows:
        lead_id = str(lead.get("id") or "")
        current_status = str(lead.get("status") or "captured")
        cols = st.columns(_COL_WEIGHTS)
        cols[0].write(_format_created_at(lead.get("created_at")))
        cols[1].write(lead.get("name") or "—")
        cols[2].write(redact_contact(lead.get("contact")))
        cols[3].write(lead.get("intent") or "—")
        with cols[4]:
            render_status(current_status, kind="lead")
        if placeholder or not lead_id:
            cols[5].write("—")
            cols[6].write("")
        else:
            try:
                default_idx = _EDITABLE_STATUSES.index(current_status)
            except ValueError:
                default_idx = 0
            with cols[5]:
                new_status = st.selectbox(
                    "Status",
                    _EDITABLE_STATUSES,
                    index=default_idx,
                    key=f"lead_status_select_{lead_id}",
                    label_visibility="collapsed",
                )
            with cols[6]:
                if st.button("Save", key=f"lead_status_save_{lead_id}"):
                    if new_status == current_status:
                        st.toast("No change.")
                    else:
                        code = _patch_lead_status(lead_id, new_status)
                        if code in (200, 204):
                            st.success(f"Lead marked {new_status}.")
                            st.rerun()
                        elif code == 403:
                            st.error(_GENERIC_FORBIDDEN)
                        else:
                            st.error(_GENERIC_FAILED)
        cols[7].write(
            f"{lead['quality_score']:.4f}"
            if lead.get("quality_score") is not None
            else "—"
        )

    # Pagination controls — only render when there is more than one page so
    # the UI stays compact for small tenants. Uses on_click callbacks (not
    # `if st.button(...)`) so the page-index state change is applied before
    # the next script run; otherwise the row list would still reflect the
    # previous page index in the same rerun.
    if total_pages > 1:
        nav_cols = st.columns([1, 1, 4])
        with nav_cols[0]:
            st.button(
                "← Previous",
                key="leads_prev_page",
                disabled=current_page == 0,
                on_click=_leads_page_prev,
            )
        with nav_cols[1]:
            st.button(
                "Next →",
                key="leads_next_page",
                disabled=current_page >= total_pages - 1,
                on_click=_leads_page_next,
                kwargs={"max_index": total_pages - 1},
            )
        with nav_cols[2]:
            st.caption(
                f"Page {current_page + 1} of {total_pages} — "
                f"showing {start + 1}–{min(end, total)} of {total}"
            )


def _leads_page_prev() -> None:
    current = int(st.session_state.get("leads_page_idx", 0))
    st.session_state["leads_page_idx"] = max(0, current - 1)


def _leads_page_next(*, max_index: int) -> None:
    current = int(st.session_state.get("leads_page_idx", 0))
    st.session_state["leads_page_idx"] = min(max_index, current + 1)
