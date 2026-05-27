# Data Model: Tenant Admin Widget Configuration

**Feature**: 004-widget-admin-config
**Date**: 2026-05-27

This feature operates on one existing platform-owned table (`widget_configs`) and consumes one existing platform-owned function (`TenantRepository.add_audit_log`). No new tables. Two new columns are required on `widget_configs` — Hiba review needed.

---

## Entity: `widget_configs` row (existing table, two new columns)

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| `id` | UUID | yes | Primary key. Existing. |
| `tenant_id` | UUID NOT NULL | yes | **Tenant isolation key.** Existing. FK to `tenants.id`. |
| `widget_id` | UUID NOT NULL UNIQUE | yes | Public identifier visitors carry in the embed snippet. Existing. |
| `allowed_origins` | TEXT[] NOT NULL | yes | List of normalized origin strings. Existing. |
| `enabled` | BOOLEAN NOT NULL DEFAULT TRUE | yes | Existing. |
| `theme_json` | JSONB NULL | **NEW** | Free-form JSON blob; widget runtime theme support lands in a later phase (per /clarify Q3). Null = use platform default theme. |
| `greeting` | TEXT NULL | **NEW** | Optional greeting text shown to visitors. Max 280 chars (app-enforced). Null = use platform default greeting. |
| `created_at` / `updated_at` | TIMESTAMPTZ | yes | Existing. |

**Schema migration**: `ALTER TABLE widget_configs ADD COLUMN theme_json JSONB NULL, ADD COLUMN greeting TEXT NULL;` — owned by Hiba. Until that migration lands, `theme_json` and `greeting` are persisted **only** in the `InMemoryWidgetRepository` test affordance (already used pending the SQL adapter).

**Indexes**: No new indexes. Tenant-scoped lookups go through the existing tenant FK; widget-id lookups (token endpoint) use the existing unique index on `widget_id`.

**Row-level security**: Existing RLS policy `widget_configs_tenant_isolation` (Hiba-owned) already restricts SELECT/UPDATE to rows where `tenant_id = current_setting('app.tenant_id')`. The new columns are protected automatically by the existing policy.

---

## Domain models (Pydantic, in `app/domain/widget.py`)

### `WidgetConfigDomain` — MODIFIED (existing model gains 2 fields)

```python
class WidgetConfigDomain(BaseModel):
    id: UUID
    tenant_id: UUID
    widget_id: UUID
    allowed_origins: list[str]                # already exists
    enabled: bool                              # already exists
    tenant_status: Literal["active", "suspended", "erasing", "erased"]
    theme_json: dict | None = None             # NEW (Pydantic accepts None or a parsed dict)
    greeting: str | None = None                # NEW
```

The token endpoint's existing usage of this model is unchanged — it only reads `allowed_origins`, `enabled`, `tenant_status`. The two new fields are additive.

### `WidgetConfigResponse` — NEW (response body for GET /widgets/config)

```python
class WidgetConfigResponse(BaseModel):
    widget_id: UUID
    allowed_origins: list[str]
    enabled: bool
    theme_json: dict | None
    greeting: str | None
```

**Note**: `tenant_id` is intentionally **omitted** from the response. The admin already knows their own tenant id (it's in their session); echoing it back is unnecessary and risks leaking it to log files.

### `WidgetConfigUpdateRequest` — NEW (request body for PUT /widgets/config)

```python
class WidgetConfigUpdateRequest(BaseModel):
    allowed_origins: list[str]                 # list of origin strings, validated and normalized server-side
    enabled: bool
    theme_json: dict | None = None             # any parseable JSON object; pydantic enforces JSON parse via the dict type
    greeting: str | None = Field(default=None, max_length=280)
```

**Validation rules** (enforced in the route layer via Pydantic + a service-layer post-validator):
- `allowed_origins`: each item must parse as a URL with scheme `http` or `https` and a non-empty host. Service-layer post-validator normalizes (see R3 in research.md) and rejects with HTTP 422 if any item fails.
- `enabled = True` AND `allowed_origins == []` (after normalization and de-duplication) → HTTP 422.
- `greeting`: max 280 chars, enforced by `Field(max_length=280)` (HTTP 422 on overflow).
- `theme_json`: any parseable JSON object or null. Pydantic's `dict | None` accepts both. No further structural validation (per /clarify Q3).
- **Note on `tenant_id`**: the request body does NOT contain `tenant_id`. It is supplied by the trusted `require_tenant_admin` dep.

---

## Entity: `audit_logs` row (existing table, two new action values)

The audit log is platform-owned (Hiba). This feature **consumes** the function `TenantRepository.add_audit_log(...)` per [CONTRACT.md:190](../../CONTRACT.md#L190); it does not write to the table directly.

| Field | Value for this feature |
|-------|------------------------|
| `tenant_id` | Supplied from the `require_tenant_admin` dep's context |
| `actor_role` | `"tenant_admin"` |
| `actor_id` | Supplied from the dep's context (`str \| None` per CONTRACT.md) |
| `action` | One of `"widget.origin_added"` or `"widget.origin_removed"` (new values; no migration required since `action` is `TEXT`) |
| `metadata` | `{"origin": "<the normalized origin>", "widget_id": "<uuid>"}` |

**Cardinality**: One audit log call per **net** origin change, not per save. If a save adds 2 origins and removes 1, the service makes 3 audit log calls within the same transaction. No-op saves (list identical to stored) produce zero audit log calls.

**Action vocabulary registration**: The two new action strings (`widget.origin_added`, `widget.origin_removed`) are added to the documented action vocabulary in `CONTRACT.md` in the implementation PR (cross-owner doc update; Hiba review for the audit section).

---

## State transitions

The widget config has no formal state machine. The only state-machine-like behavior is the `enabled` flag combined with the `allowed_origins` list:

```text
                     ┌─────────────────────────────────────────┐
                     │     enabled=true,  origins != []        │ ← valid, widget operational
                     └─────────────────────────────────────────┘
                              ▲                ▲
                              │                │
                  toggle on   │                │  add origin (with enabled still true)
                              │                │
┌──────────────────────────────────────────┐   │
│     enabled=false, origins == anything   │───┘ ← valid, widget disabled
└──────────────────────────────────────────┘
                              │
                              │  toggle on AND origins == []
                              ▼
                     ┌─────────────────────────────────────────┐
                     │     enabled=true, origins == []         │ ← REJECTED at save (FR-008)
                     └─────────────────────────────────────────┘
```

The save is the only state-transition entry point. The state-transition rules are enforced atomically per save — there is no partial state.

---

## Validation rules summary

| Field | Rule | On violation |
|-------|------|--------------|
| `allowed_origins` items | Valid URL, scheme ∈ {http, https}, non-empty host | HTTP 422 |
| `allowed_origins` size (post-normalize, de-dup) | ≥ 1 if `enabled = true` | HTTP 422 |
| `greeting` | ≤ 280 chars (or null) | HTTP 422 |
| `theme_json` | Valid JSON (parseable as a dict, or null) | HTTP 422 |
| `tenant_id` in body | Not present | HTTP 422 (Pydantic extra-field rejection) |
| Role | Must be `tenant_admin` | HTTP 403 |
| Tenant scope | Caller's tenant only | HTTP 403 (indistinguishable from "row not found", per Principle I) |
