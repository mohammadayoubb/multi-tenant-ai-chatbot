# Contract: Widget Configuration HTTP Endpoints

**Feature**: 004-widget-admin-config
**Owner**: Amer
**Consumers**: admin Streamlit page ([admin/widget_page.py](../../../admin/widget_page.py)) and any future automation calling these endpoints with `tenant_admin` credentials.

Each clause below has a corresponding test in `tests/security/test_widget_admin_config.py` (HTTP layer) or `tests/unit/test_widget_config_service.py` (service layer).

---

## E1. `GET /widgets/config`

### Request

- Method: `GET`
- Path: `/widgets/config`
- Headers (mock dev mode, until Hiba's real dep lands):
  - `X-Concierge-Role: tenant_admin`
  - `X-Concierge-Tenant-Id: <uuid>`
- No request body.

### Response

- **200 OK** when the requesting tenant has a widget config row:
  ```json
  {
    "widget_id": "<uuid>",
    "allowed_origins": ["https://acme.com", "https://blog.acme.com"],
    "enabled": true,
    "theme_json": null,
    "greeting": null
  }
  ```
  Content-Type: `application/json`. No `tenant_id` in the response body (per data-model.md, the admin already knows their tenant id).

- **403 Forbidden** when the caller is not `tenant_admin`. Body: `{"error":"forbidden"}`. Same body whether the role is missing, wrong, or the row doesn't exist for the given tenant — indistinguishability prevents tenant-existence enumeration (matches token-endpoint pattern in feature 001).

### Behavior contract

- The response MUST reflect the current persisted row for the caller's tenant only. The repository function MUST be called with `tenant_id` from the trusted dep, never from a query parameter or header value other than the dep-validated one.
- If the row does not exist for the caller's tenant, the response is **403** (not 404) — same body as the unauthorized case.

---

## E2. `PUT /widgets/config`

### Request

- Method: `PUT`
- Path: `/widgets/config`
- Headers: same as E1.
- Body:
  ```json
  {
    "allowed_origins": ["https://acme.com", "https://blog.acme.com"],
    "enabled": true,
    "theme_json": {"primary": "#ff0066"},
    "greeting": "Hi from Acme"
  }
  ```

### Response

- **200 OK** on success. Body shape identical to E1's 200 response (echoes the new persisted state).
- **403 Forbidden** if the role is not `tenant_admin`. Body: `{"error":"forbidden"}`.
- **422 Unprocessable Entity** on validation failure:
  - Invalid origin URL (wrong scheme, missing host, malformed).
  - `enabled = true` AND post-normalized `allowed_origins == []`.
  - `greeting` longer than 280 characters.
  - `theme_json` not parseable as a JSON object.
  - Body shape: standard FastAPI validation error envelope (`{"detail": [...]}` with per-field errors). The body intentionally does NOT carry sensitive details from the row.
- **500 Internal Server Error** if `add_audit_log` raises or the transaction otherwise fails. The row is NOT updated (FR-013). Body: `{"error":"internal"}`. Trace logged server-side with the failure reason.

### Behavior contract

1. The request body MUST NOT contain `tenant_id`. Pydantic rejects extra fields by default in this feature's models; including a `tenant_id` field produces a 422.
2. The server MUST derive `tenant_id` from the trusted `require_tenant_admin` dep and use it for both the UPDATE WHERE clause and the audit log calls.
3. Each origin in the request body MUST be normalized server-side to `scheme://host[:port]` form (see [research.md §R3](../research.md)). The persisted list contains only normalized origins. The response echoes the normalized form.
4. The set difference between the new (normalized) origin list and the previously persisted origin list produces the audit-log call schedule:
   - For each origin in `new − previous`: one call to `add_audit_log(tenant_id=..., actor_role="tenant_admin", action="widget.origin_added", actor_id=..., metadata={"origin": ..., "widget_id": ...})`.
   - For each origin in `previous − new`: one call to `add_audit_log(...)` with action `"widget.origin_removed"` and the same metadata shape.
   - A save where `new == previous` produces ZERO audit log calls (FR-012).
5. The widget UPDATE and all audit log calls MUST execute within a single database transaction. If any audit log call raises, the transaction rolls back and the response is 500. The row state is unchanged.
6. Greeting and `theme_json` changes are NOT audited.

---

## E3. Cross-tenant access denial (SC-004)

- Caller authenticated as `tenant_admin` of tenant A submits a `GET /widgets/config` or `PUT /widgets/config` with a header attempting to address tenant B (e.g., header injection or future endpoint variants).
- The server MUST resolve `tenant_id` from the trusted dep only. The response MUST be **identical** to the case where the caller's tenant has no row. No cross-tenant data leak via response shape or timing.
- Tested by: `test_admin_config_cross_tenant_returns_403` — two seeded tenants, admin of A cannot see B's row.

---

## E4. Idempotency of saves

- A `PUT /widgets/config` with body **byte-identical** to the current persisted state MUST return 200 OK and produce **zero** audit log calls.
- A `PUT /widgets/config` that toggles `enabled` from `true` to `false` MUST NOT require a non-empty `allowed_origins` (FR-008 applies only when `enabled = true`).

---

## E5. Contract test mapping

| Clause | Test name |
|--------|-----------|
| E1 happy path | `test_get_widget_config_returns_current_row` |
| E1 role gate | `test_get_widget_config_without_admin_returns_403` |
| E2 happy path | `test_put_widget_config_updates_fields` |
| E2 role gate | `test_put_widget_config_without_admin_returns_403` |
| E2 validation: invalid URL | `test_put_widget_config_invalid_origin_returns_422` |
| E2 validation: enabled + empty origins | `test_put_widget_config_enabled_without_origins_returns_422` |
| E2 validation: greeting too long | `test_put_widget_config_greeting_too_long_returns_422` |
| E2 validation: theme not JSON object | `test_put_widget_config_invalid_theme_returns_422` |
| E2 audit count: 1 added | `test_put_widget_config_adds_origin_calls_audit_once` |
| E2 audit count: 1 removed | `test_put_widget_config_removes_origin_calls_audit_once` |
| E2 audit count: net change | `test_put_widget_config_mixed_change_audits_each_delta` |
| E2 fail-closed | `test_put_widget_config_audit_failure_rolls_back` |
| E3 cross-tenant | `test_admin_config_cross_tenant_returns_403` |
| E4 idempotent save | `test_put_widget_config_no_change_no_audit` |
| E4 toggle off with empty origins | `test_put_widget_config_disable_with_empty_origins_allowed` |
