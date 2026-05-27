# Phase 1 Data Model: Admin Read-Only Pages

**Branch**: `005-admin-read-only-pages` | **Date**: 2026-05-27

This slice introduces **no** new persistent entities. The admin pages are read-only consumers of existing tenant-owned tables, accessed only via FastAPI HTTP endpoints. The model below describes the **response-shape projections** each page expects from the backend and the **view-model fields** rendered on screen.

Authoritative database schemas live in [CONTRACT.md §8.1](../../CONTRACT.md). This document is a projection contract, not a schema definition.

---

## Entity 1 — Tenant summary (US1)

**Source**: `GET /tenants/{tenant_id}` (Hiba, see CONTRACT.md §2.6 / §13)
**Backing table**: `tenants` (CONTRACT.md §8.1)

| Field | Type | Required for render | Notes |
|-------|------|---------------------|-------|
| `id` | UUID string | yes | Echoed for confirmation; not displayed prominently. |
| `name` | string | yes | Header card row 1. |
| `slug` | string | **optional** (treat as "—" if absent) | See research Decision 4 — present on the table but missing from CONTRACT.md §2.6 JSON example. |
| `status` | enum: `active` / `suspended` / `erasing` / `erased` | yes | Header card. |
| `plan` | string | **optional** (treat as "—" if absent) | Same gap as `slug`. |
| `created_at` | ISO 8601 datetime | yes | Header card. |
| `updated_at` | ISO 8601 datetime | no | Not displayed (kept for future use). |

**State transitions**: tenant lifecycle (`active → suspended → erasing → erased`) is owned by Hiba's tenant lifecycle slice. This page is read-only; the value is rendered as a chip/badge with no controls.

---

## Entity 2 — Audit log entry (US1)

**Source**: `GET /tenants/{tenant_id}/audit-logs` (Hiba, no published route yet — see research Decision 4)
**Backing table**: `audit_logs` (CONTRACT.md §8.1, §2.6 `TenantRepository.list_audit_logs`)

| Field | Type | Required for render | Notes |
|-------|------|---------------------|-------|
| `created_at` | ISO 8601 datetime | yes | Column 1, table sorted reverse-chronological. |
| `actor_role` | string | yes | Column 2. |
| `action` | string (from documented action vocabulary) | yes | Column 3. |
| `metadata_json` | JSON object | yes | Column 4. Renderer truncates the serialized form to 80 chars (FR-005). |
| `id` | UUID string | no | Carried but not rendered. |
| `tenant_id` | UUID string | no | Backend-derived from header; not rendered. |
| `actor_id` | string | no | Not rendered (could leak identifier). |

**Constraints**: The page renders the **20 most recent** entries (FR-005). If the backend returns more than 20, the page slices client-side; if it returns fewer, the page renders whatever is available with no error.

**Documented action vocabulary** (from CONTRACT.md §8.1): `tenant.provisioned, tenant.suspended, tenant.erasure_requested, tenant.erased, tenant.rate_limited, widget.origin_added, widget.origin_removed, cms.page_created, cms.page_updated, cms.page_deleted, lead.captured, conversation.escalated`. The page renders the raw string — no client-side mapping or localization in this slice.

---

## Entity 3 — CMS page summary (US2 list row)

**Source**: `GET /cms/pages` (Nasser/Hiba review, CONTRACT.md §13)
**Backing table**: `cms_pages` (CONTRACT.md §8.1)

| Field | Type | Required for render | Notes |
|-------|------|---------------------|-------|
| `id` | UUID string | yes (used for detail viewer routing) | Not necessarily shown in the table. |
| `title` | string | yes | Column 1. |
| `slug` | string | yes | Column 2. |
| `status` | enum: `draft` / `published` / `archived` | yes | Column 3 + filter dimension (FR-007). |
| `updated_at` | ISO 8601 datetime | yes | Column 4. |
| `created_at` | ISO 8601 datetime | no | Not rendered in list view. |

**Filter**: status filter is a Streamlit selectbox keyed `cms_status_filter` with options `all`, `draft`, `published`, `archived`. Selecting one narrows the rendered rows; selecting `all` resets.

---

## Entity 4 — CMS page detail (US2 detail viewer)

**Source**: same `GET /cms/pages` response (drill into a single row's full payload) or `GET /cms/pages/{id}` if available; both are acceptable since this is a read-only viewer.
**Backing table**: `cms_pages` (CONTRACT.md §8.1)

| Field | Type | Required for render | Notes |
|-------|------|---------------------|-------|
| `title` | string | yes | Rendered prominently. |
| `slug` | string | yes | Below title. |
| `body` | string (markdown) | yes | Rendered with `st.markdown`. |
| `source_url` | string (URL) or null | optional | Rendered as a link when present. |

**Read-only enforcement**: no edit / create / delete affordances anywhere in the viewer (FR-008).

---

## Entity 5 — Lead (US3)

**Source**: `GET /leads` (Nasser/Hiba review, no published route yet — see research Decision 4)
**Backing table**: `leads` (CONTRACT.md §8.1)

| Field | Type | Required for render | Notes |
|-------|------|---------------------|-------|
| `created_at` | ISO 8601 datetime | yes | Column 1. |
| `name` | string (nullable in schema) | yes (render as "—" when null) | Column 2. |
| `contact` | string (nullable in schema) | yes | Column 3 — **always redacted** via `redact_contact()`: first 3 chars + literal `***` (research Decision 6, FR-009). |
| `intent` | string | yes | Column 4. |
| `status` | enum: `captured` / `qualified` / `spam` / `erased` | yes | Column 5 + filter dimension (FR-010). The filter exposes only `captured` / `qualified` / `spam`; `erased` rows are not surfaced in this view. |
| `quality_score` | number (0.0000–1.0000, nullable) | yes | Column 6 — render as "—" when null. |
| `id` | UUID string | no | Not rendered. |
| `tenant_id` | UUID string | no | Backend-derived; not rendered. |
| `conversation_id` | UUID string | no | Not rendered (could be added in a future "open conversation" affordance; out of scope). |

**Filter**: status filter is a Streamlit selectbox keyed `leads_status_filter` with options `all`, `captured`, `qualified`, `spam`.

**Read-only enforcement**: no edit, qualify, mark-as-spam, or export controls (FR-010).

---

## Entity 6 — Usage rollup (US4)

**Source**: `GET /tenants/{tenant_id}/usage` (Hiba, no published route yet — see research Decision 4)
**Backing table**: `tenant_usage` (CONTRACT.md §8.1) — the backend aggregates rows into the rollup shape below.

```json
{
  "tenant_id": "uuid",
  "period": {
    "start": "2026-05-01T00:00:00Z",
    "end":   "2026-05-27T23:59:59Z"
  },
  "total_tokens": 0,
  "total_cost_usd": 0.0,
  "by_feature": {
    "chat":       { "tokens": 0, "cost_usd": 0.0 },
    "embedding":  { "tokens": 0, "cost_usd": 0.0 },
    "classifier": { "tokens": 0, "cost_usd": 0.0 },
    "rag":        { "tokens": 0, "cost_usd": 0.0 },
    "agent":      { "tokens": 0, "cost_usd": 0.0 },
    "guardrails": { "tokens": 0, "cost_usd": 0.0 }
  },
  "daily_cost_usd": [
    { "date": "2026-05-01", "cost_usd": 0.0 },
    { "date": "2026-05-02", "cost_usd": 0.0 }
  ]
}
```

| Field | Type | Required for render | Notes |
|-------|------|---------------------|-------|
| `total_tokens` | int | yes | "Tokens this month" metric. |
| `total_cost_usd` | number | yes | "Cost this month" metric. |
| `by_feature.<feature>.tokens` | int | yes (for each feature key) | Breakdown table column 1. |
| `by_feature.<feature>.cost_usd` | number | yes (for each feature key) | Breakdown table column 2. |
| `daily_cost_usd[i].date` | ISO 8601 date | yes | Line chart x-axis. |
| `daily_cost_usd[i].cost_usd` | number | yes | Line chart y-axis. |
| `period.start` / `period.end` | ISO 8601 datetime | optional | Rendered as a caption under the totals when present. |

**Feature vocabulary** is fixed by CONTRACT.md §8.1: `chat, embedding, classifier, rag, agent, guardrails`. Missing keys in the response default to `{"tokens": 0, "cost_usd": 0.0}` (research Decision 4 — defensive parsing of optional fields).

**Read-only enforcement**: no rate-limit configuration, no billing controls (FR-012).

---

## Cross-cutting view-model rules

1. **Tenant scoping**: every request's `tenant_id` comes from the `X-Concierge-Tenant-Id` dev header (research Decision 3), which is set in trusted server-side context — never from a query parameter or user input (constitution Principle I; spec FR-016).
2. **Defensive parsing**: required fields raise loudly (so we never silently render the wrong tenant's data); optional fields default to `None` / `[]` / `0` and are surfaced as "—" or empty rows in the UI.
3. **Placeholder fallback**: when any of the five consumed endpoints is missing or returns the placeholder shape, the page renders canned sample data in the exact projection above and adds a visible `(placeholder)` badge (research Decision 5, FR-003).
4. **Read-only**: no field on any of these entities is writable from `admin/` in this slice. There are no forms, no Save buttons, and no PUT/POST/DELETE/PATCH calls.
