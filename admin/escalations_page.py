# Owner: Amer
"""Tenant Escalations admin page (Spec 009 US2, T075).

Lists open / in-progress / resolved tickets for the signed-in tenant and lets
a tenant admin change status or assign a ticket. The assignee dropdown is
populated from `GET /tenants/{tid}/admin-users` so foreign-tenant assignees
are impossible by construction — the dropdown only ever lists same-tenant
users.

Reads:
- `GET /escalations` (T039e) — list of tickets scoped to the JWT tenant.
- `GET /tenants/{tid}/admin-users` (T039g) — assignee pool.

Writes:
- `PATCH /escalations/{id}` (T039e) — status + assignee_id update.

If either GET fails, the page falls back to placeholder rows / a disabled
assignee dropdown. Mutation failures collapse to a generic "forbidden /
failed" message — no raw server text is ever surfaced (Principle V).
"""

from __future__ import annotations

from typing import Any

import httpx
import streamlit as st

from admin._admin_http import http_client as _http_client, signed_in_tenant_id
from admin._status_pill import render_status
from admin._table import render_table

_STATUS_OPTIONS = ["pending", "in_progress", "resolved", "closed"]

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


def _render_table(tickets: list[dict[str, Any]]) -> None:
    rows = [
        {
            "ticket_id": str(t.get("ticket_id", "—")),
            "opened_at": t.get("opened_at", "—"),
            "status": t.get("status", "—"),
            "assignee": t.get("assignee_name") or "—",
            "excerpt": t.get("last_message_excerpt", "—"),
        }
        for t in tickets
    ]
    render_table(
        rows,
        columns=["ticket_id", "opened_at", "status", "assignee", "excerpt"],
        empty_state={
            "title": "No escalations yet",
            "message": "Tickets created by the agent's escalate tool will appear here.",
        },
        key="escalations_table",
    )

    # US4 / T115: render ticket-status pills below the table so the visual
    # language matches tenants/invites/leads. Streamlit's dataframe cannot
    # render colored chips inline.
    if tickets:
        st.markdown("#### Ticket status")
        for t in tickets:
            cols = st.columns([3, 2])
            with cols[0]:
                st.write(f"`{t.get('ticket_id', '—')}`")
            with cols[1]:
                render_status(str(t.get("status", "—")), kind="ticket")


def _render_ticket_controls(
    ticket: dict[str, Any],
    admins: list[dict[str, Any]],
    admin_endpoint_pending: bool,
) -> None:
    ticket_id = str(ticket.get("ticket_id"))
    current_status = ticket.get("status") or _STATUS_OPTIONS[0]
    status_options = list(_STATUS_OPTIONS)
    if current_status not in status_options:
        status_options = [current_status, *status_options]

    st.markdown(f"#### Ticket `{ticket_id}`")
    cols = st.columns(2)
    with cols[0]:
        new_status = st.selectbox(
            "Status",
            status_options,
            index=status_options.index(current_status),
            key=f"status_select_{ticket_id}",
        )
    with cols[1]:
        if admin_endpoint_pending or not admins:
            st.selectbox(
                "Assignee",
                ["(endpoint pending — assignee dropdown disabled)"],
                key=f"assignee_select_{ticket_id}",
                disabled=True,
            )
            st.caption("Assignee endpoint pending — selection disabled.")
            new_assignee_id = ticket.get("assignee_id")
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
                format_func=lambda i: options[i][1],
                index=current_idx,
                key=f"assignee_select_{ticket_id}",
            )
            new_assignee_id = options[selected][0]

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
        st.caption("(placeholder)")
    if admin_endpoint_pending:
        st.caption(
            "Assignee endpoint pending — the assignee dropdown is disabled "
            "until `/tenants/{tid}/admin-users` is shipped."
        )

    _render_table(tickets)

    if not tickets:
        return

    for ticket in tickets:
        _render_ticket_controls(ticket, admins, admin_endpoint_pending)
