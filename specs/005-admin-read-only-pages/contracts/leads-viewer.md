# Contract — Leads Viewer Page (US3)

**Page**: [admin/leads_page.py](../../../admin/leads_page.py)
**Owner consumed**: Nasser (Hiba review)
**Status**: HTTP route is not yet published. This page proposes `GET /leads` for Nasser's handoff.

## Endpoint consumed

### `GET /leads`  *(proposed route — Nasser)*

- **Authoritative source**: backing table [CONTRACT.md §8.1](../../../CONTRACT.md) `leads`. No HTTP route is yet documented; this page proposes `GET /leads` as the natural pair to `GET /cms/pages`.
- **Request**:
  - Method: `GET`
  - Path: `/leads`
  - Query: optional `status` (one of `captured` / `qualified` / `spam`). Initial implementation filters client-side, same rationale as the CMS list (self-contained + simpler tests).
  - Headers: `X-Concierge-Role: tenant_admin`, `X-Concierge-Tenant-Id: <uuid>`, `X-Concierge-Actor-Id: <admin email>`.
- **Expected 200 response** (projection from `leads` table):
  ```json
  [
    {
      "id": "uuid",
      "created_at": "2026-05-26T18:02:11Z",
      "name": "Avery T.",
      "contact": "avery@example.com",
      "intent": "demo_request",
      "status": "captured",
      "quality_score": 0.7421
    }
  ]
  ```
  - **Required for render**: `created_at`, `intent`, `status`.
  - **Conditionally rendered as "—"**: `name`, `quality_score` (both nullable in schema).
  - **Rendered redacted**: `contact` — see redaction rule below.
- **Placeholder fallback** triggers when (research Decision 5):
  - response status is **any non-2xx** (404, other 4xx, or 5xx), OR
  - response status is 2xx but the body is missing required fields (route present in placeholder mode), OR
  - the request raises a transport error (`httpx.HTTPError`).
- **Sample data on fallback** (canned in [admin/leads_page.py](../../../admin/leads_page.py)): three rows covering each filterable status (`captured`, `qualified`, `spam`), including one row with a `null` name and one row with a `null` quality_score to exercise nullable rendering.

## Redaction rule (Principle V, FR-009)

The `contact` column is **always** redacted before display:

```python
def redact_contact(value: str) -> str:
    return f"{value[:3]}***"
```

- Empty string → `"***"`
- 1 char `"a"` → `"a***"`
- 3 chars `"abc"` → `"abc***"`
- Long contact `"avery@example.com"` → `"ave***"`

The unredacted contact value is **never** written to logs, console output, or any st.write call elsewhere on the page.

## Read-only enforcement

This page MUST NOT issue any of: `PUT`, `POST`, `DELETE`, `PATCH`. No qualify / mark-as-spam / export / edit controls (FR-010).

## AppTest selectors

| Element | Streamlit widget / key |
|---------|------------------------|
| Status filter | `st.selectbox` with key `leads_status_filter` |
| Leads table | `st.dataframe` with key `leads_table` |
| Placeholder badge | `st.caption` or `st.warning` containing the literal text `(placeholder)` |
