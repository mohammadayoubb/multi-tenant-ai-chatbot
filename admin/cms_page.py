# Owner: Amer
"""CMS admin page — list + CRUD (Spec 009 US2, T070).

Lists CMS pages (title, slug, status, updated_at) via the shared `_table`
helper, with a status filter. Tenant admins can Create / Edit / Publish /
Unpublish / Delete. Each mutating action calls the corresponding backend
endpoint; tenant_id ALWAYS derives from the admin JWT (never from any form
field). Delete requires a two-step confirmation (FR-022).

Any non-2xx response or transport error on the GET falls back to canned
sample data with a visible "(placeholder)" caption (FR-013).
"""

from __future__ import annotations

from typing import Any

import httpx
import streamlit as st

from admin._admin_http import http_client as _http_client, render_placeholder_caption
from admin._table import render_table

_STATUS_OPTIONS = ["all", "draft", "published", "archived"]
_CREATE_STATUS_OPTIONS = ["draft", "published", "archived"]

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

_GENERIC_FORBIDDEN = "You do not have permission for that action."
_GENERIC_FAILED = "The request failed; please retry."


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


def _post_page(payload: dict[str, Any]) -> tuple[int, Any]:
    try:
        with _http_client() as client:
            resp = client.post("/cms/pages", json=payload)
    except httpx.HTTPError:
        return 0, None
    try:
        body = resp.json()
    except ValueError:
        body = None
    return resp.status_code, body


def _put_page(page_id: str, payload: dict[str, Any]) -> tuple[int, Any]:
    try:
        with _http_client() as client:
            resp = client.put(f"/cms/pages/{page_id}", json=payload)
    except httpx.HTTPError:
        return 0, None
    try:
        body = resp.json()
    except ValueError:
        body = None
    return resp.status_code, body


def _patch_status(page_id: str, new_status: str) -> tuple[int, Any]:
    try:
        with _http_client() as client:
            resp = client.patch(
                f"/cms/pages/{page_id}/status", json={"status": new_status}
            )
    except httpx.HTTPError:
        return 0, None
    try:
        body = resp.json()
    except ValueError:
        body = None
    return resp.status_code, body


def _delete_page(page_id: str) -> int:
    try:
        with _http_client() as client:
            resp = client.delete(f"/cms/pages/{page_id}")
    except httpx.HTTPError:
        return 0
    return resp.status_code


def _surface_error(status_code: int, body: Any) -> None:
    """Render a generic error message; never leak raw server bodies."""
    if status_code == 403:
        st.error(_GENERIC_FORBIDDEN)
        return
    if status_code == 422:
        # Surface only the high-level "validation failed" message and the
        # field locations, not arbitrary text from the body.
        st.error("Validation failed.")
        if isinstance(body, dict):
            detail = body.get("detail")
            if isinstance(detail, list):
                for err in detail:
                    if isinstance(err, dict):
                        loc = ".".join(str(p) for p in err.get("loc", []) if p)
                        msg = err.get("msg", "")
                        if loc or msg:
                            st.write(f"- `{loc}`: {msg}")
        return
    st.error(_GENERIC_FAILED)


def _render_create_form() -> None:
    with st.expander("Create a new page", expanded=False):
        with st.form("cms_create_form", clear_on_submit=True):
            title = st.text_input("Title", key="cms_create_title")
            slug = st.text_input("Slug", key="cms_create_slug")
            body = st.text_area("Body (markdown)", key="cms_create_body")
            source_url = st.text_input(
                "Source URL (optional)", key="cms_create_source_url"
            )
            create_status = st.selectbox(
                "Status", _CREATE_STATUS_OPTIONS, key="cms_create_status"
            )
            submitted = st.form_submit_button("Create page", type="primary")
        if submitted:
            payload: dict[str, Any] = {
                "title": title.strip(),
                "slug": slug.strip(),
                "body": body,
                "status": create_status,
            }
            if source_url.strip():
                payload["source_url"] = source_url.strip()
            if not payload["title"] or not payload["slug"] or not payload["body"]:
                st.error("Title, slug, and body are required.")
                return
            code, resp_body = _post_page(payload)
            if code in (200, 201):
                st.success("Page created.")
                st.rerun()
            else:
                _surface_error(code, resp_body)


def _render_edit_form(page: dict[str, Any]) -> None:
    page_id = str(page.get("id"))
    with st.form(f"cms_edit_form_{page_id}", clear_on_submit=False):
        title = st.text_input(
            "Title", value=page.get("title", ""), key=f"cms_edit_title_{page_id}"
        )
        slug = st.text_input(
            "Slug", value=page.get("slug", ""), key=f"cms_edit_slug_{page_id}"
        )
        body = st.text_area(
            "Body (markdown)",
            value=page.get("body", ""),
            key=f"cms_edit_body_{page_id}",
            height=200,
        )
        source_url = st.text_input(
            "Source URL (optional)",
            value=page.get("source_url") or "",
            key=f"cms_edit_source_url_{page_id}",
        )
        saved = st.form_submit_button("Save changes", type="primary")
    if saved:
        payload: dict[str, Any] = {
            "title": title.strip(),
            "slug": slug.strip(),
            "body": body,
        }
        url = source_url.strip()
        payload["source_url"] = url or None
        code, resp_body = _put_page(page_id, payload)
        if code in (200, 204):
            st.success("Changes saved.")
            st.rerun()
        else:
            _surface_error(code, resp_body)


def _render_publish_controls(page: dict[str, Any]) -> None:
    page_id = str(page.get("id"))
    current = page.get("status", "draft")
    cols = st.columns(2)
    if current != "published":
        if cols[0].button("Publish", key=f"cms_publish_{page_id}"):
            code, body = _patch_status(page_id, "published")
            if code in (200, 204):
                st.success("Page published.")
                st.rerun()
            else:
                _surface_error(code, body)
    else:
        if cols[0].button("Unpublish", key=f"cms_unpublish_{page_id}"):
            code, body = _patch_status(page_id, "draft")
            if code in (200, 204):
                st.success("Page unpublished.")
                st.rerun()
            else:
                _surface_error(code, body)
    if current != "archived":
        if cols[1].button("Archive", key=f"cms_archive_{page_id}"):
            code, body = _patch_status(page_id, "archived")
            if code in (200, 204):
                st.success("Page archived.")
                st.rerun()
            else:
                _surface_error(code, body)


def _render_delete_controls(page: dict[str, Any]) -> None:
    page_id = str(page.get("id"))
    confirm_key = f"cms_delete_confirm_{page_id}"
    is_confirming = bool(st.session_state.get(confirm_key))

    if not is_confirming:
        if st.button("Delete page", key=f"cms_delete_{page_id}"):
            st.session_state[confirm_key] = True
            st.rerun()
        return

    st.warning(
        "Delete this page? The page will be removed and its content will no "
        "longer be searchable by the agent."
    )
    cols = st.columns(2)
    if cols[0].button("Confirm delete", key=f"cms_delete_confirm_yes_{page_id}", type="primary"):
        code = _delete_page(page_id)
        st.session_state.pop(confirm_key, None)
        if code in (200, 204):
            st.session_state.pop("cms_detail_select", None)
            st.success("Page archived (removed from RAG).")
            st.rerun()
        else:
            _surface_error(code, None)
    if cols[1].button("Cancel", key=f"cms_delete_confirm_no_{page_id}"):
        st.session_state.pop(confirm_key, None)
        st.rerun()


def render() -> None:
    pages, placeholder = _fetch_pages()
    if placeholder:
        render_placeholder_caption()

    _render_create_form()

    selected_status = st.selectbox(
        "Filter by status",
        _STATUS_OPTIONS,
        index=_STATUS_OPTIONS.index("published"),
        key="cms_status_filter",
    )
    if selected_status != "all":
        filtered = [p for p in pages if p.get("status") == selected_status]
    else:
        filtered = list(pages)

    rows = [
        {
            "title": p.get("title", "—"),
            "slug": p.get("slug", "—"),
            "status": p.get("status", "—"),
            "updated_at": p.get("updated_at", "—"),
        }
        for p in filtered
    ]
    render_table(
        rows,
        columns=["title", "slug", "status", "updated_at"],
        empty_state={
            "title": "No CMS pages yet",
            "message": "Create your first page above so the agent can answer from it.",
        },
        key="cms_page_table",
    )

    if not filtered:
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

    # Mutating controls are skipped on the placeholder dataset (no real ids).
    if placeholder:
        return

    st.markdown("---")
    st.markdown("#### Edit")
    _render_edit_form(detail)
    st.markdown("#### Status")
    _render_publish_controls(detail)
    st.markdown("#### Delete")
    _render_delete_controls(detail)
