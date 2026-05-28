# Contract — CMS List Page (US2)

**Page**: [admin/cms_page.py](../../../admin/cms_page.py)
**Owner consumed**: Nasser (Hiba review)
**Status**: `GET /cms/pages` route is documented in CONTRACT.md §13.

## Endpoint consumed

### `GET /cms/pages`

- **Authoritative source**: [CONTRACT.md §13](../../../CONTRACT.md) (API Route Naming) + §8.1 (`cms_pages` table).
- **Request**:
  - Method: `GET`
  - Path: `/cms/pages`
  - Query: optional `status` (one of `draft` / `published` / `archived`). The page may pass through the user's selectbox value, or filter client-side. **Initial implementation filters client-side** to keep the page self-contained and the test harness simple.
  - Headers: `X-Concierge-Role: tenant_admin`, `X-Concierge-Tenant-Id: <uuid>`, `X-Concierge-Actor-Id: <admin email>`.
- **Expected 200 response** (projection from `cms_pages` table):
  ```json
  [
    {
      "id": "uuid",
      "title": "Pricing",
      "slug": "pricing",
      "body": "## Plans\n\n…",
      "source_url": "https://example.com/pricing",
      "status": "published",
      "updated_at": "2026-05-22T11:10:00Z",
      "created_at": "2026-04-01T09:00:00Z"
    }
  ]
  ```
  - **Required for list render**: `id`, `title`, `slug`, `status`, `updated_at`.
  - **Required for detail viewer**: `title`, `slug`, `body`.
  - **Optional for detail viewer**: `source_url` — rendered as a link when present.
- **Placeholder fallback** triggers when (research Decision 5):
  - response status is **any non-2xx** (404, other 4xx, or 5xx), OR
  - the request raises a transport error (`httpx.HTTPError`).
  - Note: a 2xx response with an empty list `[]` is **not** a fallback — it is rendered as "no CMS pages yet" with no badge, because the route is clearly wired.
- **Sample data on fallback** (canned in [admin/cms_page.py](../../../admin/cms_page.py)): three rows — one per allowed status (`draft`, `published`, `archived`) — with realistic titles and slugs.

## Read-only enforcement

This page MUST NOT issue any of: `PUT`, `POST`, `DELETE`, `PATCH`. The detail viewer has no editable text field, no Save button, no Delete button (FR-008).

## AppTest selectors

| Element | Streamlit widget / key |
|---------|------------------------|
| Status filter | `st.selectbox` with key `cms_status_filter` |
| List table | `st.dataframe` with key `cms_page_table` |
| Detail viewer trigger | `st.selectbox` with key `cms_detail_select` (selects page by id) |
| Detail body | `st.markdown` block rendered under header `CMS page detail` |
| Placeholder badge | `st.caption` or `st.warning` containing the literal text `(placeholder)` |
