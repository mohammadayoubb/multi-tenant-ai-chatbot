# Owner: Amer
"""Tenant Escalations admin page (Spec 009 US2, T075 — refreshed feature 010).

Lists pending / in-progress / resolved tickets for the signed-in tenant and
lets a tenant admin change status or assign a ticket — both controls live
inline on each table row alongside a status pill. The assignee dropdown is
populated from `GET /tenants/{tid}/admin-users` so foreign-tenant assignees
are impossible by construction.

Reads:
- `GET /escalations` — list of tickets scoped to the JWT tenant.
- `GET /tenants/{tid}/admin-users` — assignee pool.

Writes:
- `PATCH /escalations/{id}` — status + assignee_id update.

If either GET fails, the page falls back to placeholder rows / a disabled
assignee dropdown. Mutation failures collapse to a generic "forbidden /
failed" message — no raw server text is ever surfaced (Principle V).
"""

from __future__ import annotations

from typing import Any

import httpx
import streamlit as st

from admin._admin_http import (
    http_client as _http_client,
    render_placeholder_caption,
    signed_in_tenant_id,
)
from admin._status_pill import render_status

# Mirrors the DB CHECK constraint `ck_escalation_tickets_status` exactly —
# any other value will hit a 500 at the repository INSERT/UPDATE. `erased`
# is reserved for GDPR erasure and is not user-selectable.
_STATUS_OPTIONS = ["open", "in_progress", "resolved"]
_PAGE_SIZE = 10

_SAMPLE_TICKETS: list[dict[str, Any]] = [
    {
        "ticket_id": "sample-ticket-1",
        "opened_at": "2026-05-25T10:00:00Z",
        "last_message_excerpt": "Sample ticket — backend unavailable.",
        "status": "pending",
        "assignee_id": None,
        "assignee_name": None,
    },
]

_GENERIC_FORBIDDEN = "Forbidden — you do not have permission for that action."
_GENERIC_FAILED = "The request failed; please retry."

_COL_WEIGHTS = [2, 2, 4, 2, 2, 2, 1]
_COL_HEADERS = (
    "Opened",
    "Ticket",
    "Excerpt",
    "Status",
    "Change",
    "Assignee",
    "",
)


def _admin_users_url() -> str:
    return f"/tenants/{signed_in_tenant_id()}/admin-users"


def _fetch_tickets() -> tuple[list[dict[str, Any]], bool]:
    try:
        with _http_client() as client:
            resp = client.get("/escalations")
    except httpx.HTTPError:
        return list(_SAMPLE_TICKETS), True
    if resp.status_code < 200 or resp.status_code >= 300:
        return list(_SAMPLE_TICKETS), True
    try:
        body = resp.json()
    except ValueError:
        return list(_SAMPLE_TICKETS), True
    if not isinstance(body, list):
        return list(_SAMPLE_TICKETS), True
    return body, False


def _fetch_admins() -> tuple[list[dict[str, Any]], bool]:
    """Return ``(admins, endpoint_pending)``."""
    try:
        with _http_client() as client:
            resp = client.get(_admin_users_url())
    except httpx.HTTPError:
        return [], True
    if resp.status_code == 404:
        return [], True
    if resp.status_code < 200 or resp.status_code >= 300:
        return [], True
    try:
        body = resp.json()
    except ValueError:
        return [], True
    if not isinstance(body, list):
        return [], True
    return body, False


def _patch_ticket(ticket_id: str, payload: dict[str, Any]) -> tuple[int, Any]:
    try:
        with _http_client() as client:
            resp = client.patch(f"/escalations/{ticket_id}", json=payload)
    except httpx.HTTPError:
        return 0, None
    try:
        body = resp.json()
    except ValueError:
        body = None
    return resp.status_code, body


def _surface_error(status_code: int) -> None:
    if status_code == 403:
        st.error(_GENERIC_FORBIDDEN)
    else:
        st.error(_GENERIC_FAILED)


def _format_assignee_label(admin: dict[str, Any]) -> str:
    name = admin.get("full_name") or admin.get("email") or admin.get("actor_id") or "—"
    return str(name)


def _format_opened_at(value: Any) -> str:
    text = str(value or "")
    if "T" in text:
        date_part, time_part = text.split("T", 1)
        return f"{date_part} {time_part[:5]}"
    return text or "—"


def _short_ticket(ticket_id: str) -> str:
    """Display a short prefix for long UUID ticket ids."""
    cleaned = ticket_id.strip()
    if len(cleaned) <= 10:
        return cleaned or "—"
    return f"{cleaned[:8]}…"


def _truncate(text: str, limit: int = 90) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned or "—"
    return cleaned[: limit - 1].rstrip() + "…"


def _escalations_page_prev() -> None:
    current = int(st.session_state.get("escalations_page_idx", 0))
    st.session_state["escalations_page_idx"] = max(0, current - 1)


def _escalations_page_next(*, max_index: int) -> None:
    current = int(st.session_state.get("escalations_page_idx", 0))
    st.session_state["escalations_page_idx"] = min(max_index, current + 1)


def _render_row(
    ticket: dict[str, Any],
    admins: list[dict[str, Any]],
    admin_endpoint_pending: bool,
    placeholder: bool,
) -> None:
    ticket_id = str(ticket.get("ticket_id") or "")
    current_status = str(ticket.get("status") or _STATUS_OPTIONS[0])
    status_options = list(_STATUS_OPTIONS)
    if current_status not in status_options:
        status_options = [current_status, *status_options]

    cols = st.columns(_COL_WEIGHTS)
    cols[0].write(_format_opened_at(ticket.get("opened_at")))
    cols[1].markdown(f"`{_short_ticket(ticket_id)}`")
    cols[2].write(_truncate(ticket.get("last_message_excerpt", ""), 100))
    with cols[3]:
        render_status(current_status, kind="ticket")

    if placeholder or not ticket_id:
        cols[4].write("—")
        cols[5].write("—")
        cols[6].write("")
        return

    with cols[4]:
        new_status = st.selectbox(
            "Status",
            status_options,
            index=status_options.index(current_status),
            key=f"status_select_{ticket_id}",
            label_visibility="collapsed",
        )

    with cols[5]:
        if admin_endpoint_pending or not admins:
            st.selectbox(
                "Assignee",
                ["(pending)"],
                key=f"assignee_select_{ticket_id}",
                disabled=True,
                label_visibility="collapsed",
            )
            new_assignee_id: str | None = ticket.get("assignee_id")
        else:
            options: list[tuple[str | None, str]] = [(None, "Unassigned")]
            for admin in admins:
                options.append(
                    (
                        str(admin.get("actor_id")),
                        _format_assignee_label(admin),
                    )
                )
            current_assignee = ticket.get("assignee_id")
            current_idx = 0
            for idx, (actor_id, _label) in enumerate(options):
                if (actor_id or None) == (current_assignee or None):
                    current_idx = idx
                    break
            selected = st.selectbox(
                "Assignee",
                options=list(range(len(options))),
                format_func=lambda i, _opts=options: _opts[i][1],
                index=current_idx,
                key=f"assignee_select_{ticket_id}",
                label_visibility="collapsed",
            )
            new_assignee_id = options[selected][0]

    with cols[6]:
        if st.button("Save", key=f"save_ticket_{ticket_id}", type="primary"):
            payload: dict[str, Any] = {"status": new_status}
            if not admin_endpoint_pending:
                payload["assignee_id"] = new_assignee_id
            status_code, _body = _patch_ticket(ticket_id, payload)
            if status_code in (200, 204):
                st.success("Ticket updated.")
                st.rerun()
            else:
                _surface_error(status_code)


def render() -> None:
    tickets, placeholder = _fetch_tickets()
    admins, admin_endpoint_pending = _fetch_admins()

    if placeholder:
        render_placeholder_caption()
    if admin_endpoint_pending:
        st.caption(
            "Assignee endpoint pending — the assignee dropdown is disabled "
            "until `/tenants/{tid}/admin-users` is shipped."
        )

    if not tickets:
        st.info(
            "No escalations yet. Tickets created by the agent's escalate tool "
            "will appear here."
        )
        return

    total = len(tickets)
    total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    current_page = int(st.session_state.get("escalations_page_idx", 0))
    current_page = max(0, min(current_page, total_pages - 1))
    start = current_page * _PAGE_SIZE
    end = start + _PAGE_SIZE
    page_rows = tickets[start:end]

    # Column header row inside a bordered container so the layout reads as
    # a real table; each ticket row gets its own bordered container below.
    with st.container(border=True):
        header_cols = st.columns(_COL_WEIGHTS)
        for col, label in zip(header_cols, _COL_HEADERS):
            col.markdown(f"**{label}**")

    for ticket in page_rows:
        with st.container(border=True):
            _render_row(ticket, admins, admin_endpoint_pending, placeholder)

    if total_pages > 1:
        nav_cols = st.columns([1, 1, 4])
        with nav_cols[0]:
            st.button(
                "← Previous",
                key="escalations_prev_page",
                disabled=current_page == 0,
                on_click=_escalations_page_prev,
            )
        with nav_cols[1]:
            st.button(
                "Next →",
                key="escalations_next_page",
                disabled=current_page >= total_pages - 1,
                on_click=_escalations_page_next,
                kwargs={"max_index": total_pages - 1},
            )
        with nav_cols[2]:
            st.caption(
                f"Page {current_page + 1} of {total_pages} — "
                f"showing {start + 1}–{min(end, total)} of {total}"
            )
