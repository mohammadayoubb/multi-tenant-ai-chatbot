# Contract — Tenant Overview Page (US1)

**Page**: [admin/tenant_page.py](../../../admin/tenant_page.py)
**Owner consumed**: Hiba
**Status**: tenant detail route is documented; audit-log HTTP route is not yet published.

## Endpoints consumed

### 1. `GET /tenants/{tenant_id}`

- **Authoritative source**: [CONTRACT.md §2.6](../../../CONTRACT.md) + §13.
- **Request**:
  - Method: `GET`
  - Path: `/tenants/{tenant_id}` where `{tenant_id}` is the value of the `X-Concierge-Tenant-Id` header (the admin's trusted tenant).
  - Headers: `X-Concierge-Role: tenant_admin`, `X-Concierge-Tenant-Id: <uuid>`, `X-Concierge-Actor-Id: <admin email>`.
  - Body: none.
- **Expected 200 response** (per CONTRACT.md §2.6, extended with optional fields from §8.1):
  ```json
  {
    "id": "uuid",
    "name": "Acme Inc.",
    "slug": "acme",
    "status": "active",
    "plan": "starter",
    "created_at": "2026-01-15T09:30:00Z",
    "updated_at": "2026-05-20T14:00:00Z"
  }
  ```
  - **Required for render**: `id`, `name`, `status`, `created_at`.
  - **Optional**: `slug`, `plan` — render `—` when absent (research Decision 4).
- **Error/edge handling**:
  - Non-200 status → friendly error state (FR-013); no stack trace surfaced.
  - 404 anywhere in the page chain → placeholder fallback for the affected section only.

### 2. `GET /tenants/{tenant_id}/audit-logs`  *(proposed route — Hiba)*

- **Authoritative source**: backing table CONTRACT.md §8.1 `audit_logs`; repository function CONTRACT.md §2.6 `TenantRepository.list_audit_logs`. **No HTTP route is yet published.** This page proposes the path above for Hiba's handoff.
- **Request**:
  - Method: `GET`
  - Path: `/tenants/{tenant_id}/audit-logs`
  - Query: optional `limit=20` (the page slices to 20 client-side regardless).
  - Headers: same dev headers as endpoint 1.
- **Expected 200 response**:
  ```json
  [
    {
      "id": "uuid",
      "created_at": "2026-05-26T13:45:11Z",
      "actor_role": "tenant_admin",
      "action": "cms.page_updated",
      "metadata_json": { "page_slug": "pricing", "field": "body" }
    }
  ]
  ```
  - **Required for render**: `created_at`, `actor_role`, `action`, `metadata_json`.
- **Placeholder fallback** triggers when (research Decision 5):
  - response status is **any non-2xx** (404, other 4xx, or 5xx), OR
  - response status is 2xx but the body is empty / missing required fields, OR
  - the request raises a transport error (`httpx.HTTPError`).
- **Sample data on fallback** (canned in [admin/tenant_page.py](../../../admin/tenant_page.py)): three rows covering `tenant.provisioned`, `widget.origin_added`, and `cms.page_updated` to demonstrate the action vocabulary.

## Read-only enforcement

This page MUST NOT issue any of: `PUT`, `POST`, `DELETE`, `PATCH`. No Save / Suspend / Erase / Edit controls of any kind (FR-006).

## AppTest selectors

| Element | Streamlit widget / key |
|---------|------------------------|
| Header card name | `st.subheader` directly under page title |
| Status chip | First `st.metric` or `st.markdown` chip in the header card |
| Audit log table | `st.dataframe` with key `tenant_audit_log_table` |
| Placeholder badge | `st.caption` or `st.warning` containing the literal text `(placeholder)` |
