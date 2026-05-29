# Admin-Routes Contract (UI consumer view)

What the Streamlit admin pages send and expect from the backend. Every request below carries `Authorization: Bearer <admin-jwt>` unless marked **public**. Endpoints in *italics* are shipped today; **bold** ones are listed in [missing-endpoints.md](missing-endpoints.md) and the UI mocks them with `(placeholder)` until they land.

---

## Authentication

### *POST /admin/login* — public

Request:
```json
{ "email": "admin@example.com", "password": "..." }
```
Response 200:
```json
{ "token": "<jwt>", "expires_in": 28800, "actor_id": "<uuid>",
  "tenant_id": "<uuid>", "role": "tenant_admin" | "tenant_manager",
  "full_name": "Jane Doe" }
```
Response 401:
```json
{ "error": "invalid_credentials" }
```
Every failure cause collapses to this same body — anti-enumeration is server-enforced.

---

### *POST /admin/invites* — admin

Request:
```json
{ "email": "newadmin@example.com", "role": "tenant_admin",
  "tenant_id": "<uuid>", "ttl_seconds": 604800 }
```
Response 200:
```json
{ "token": "<uuid>", "email": "...", "role": "tenant_admin",
  "tenant_id": "<uuid>", "expires_at": "iso-8601" }
```

### *GET /admin/invites/{token}* — public (preview)

Response 200:
```json
{ "email": "newadmin@example.com", "role": "tenant_admin",
  "tenant_name": "Acme", "expires_at": "iso-8601",
  "status": "pending" | "used" | "expired" }
```

### *POST /admin/invites/{token}/accept* — public

Request:
```json
{ "full_name": "Jane Doe", "password": "...", "confirm_password": "..." }
```
Response 200: `{ "ok": true }` (UI then calls `POST /admin/login` automatically).

### **POST /admin/invites/{token}/revoke** — admin *(MISSING)*

Used by Tenant Manager Invites tab; mocked until live.

### **POST /admin/invites/{token}/resend** — admin *(MISSING)*

Re-mints token + extends expiry; mocked until live.

---

## Tenant content (Tenant Admin tab consumers)

### *GET /cms/pages* — admin

Response 200:
```json
[ { "id": "<uuid>", "title": "...", "slug": "...",
    "status": "draft" | "published" | "archived", "updated_at": "iso" } ]
```

### *POST /cms/pages* — admin

Request:
```json
{ "title": "...", "slug": "...", "body": "markdown",
  "source_url": "https://...", "status": "draft" | "published" }
```
`tenant_id` derived from JWT; rejected with 422 if present in the body (`extra=forbid`).

### *GET /leads* — admin

Response 200:
```json
[ { "id": "<uuid>", "captured_at": "iso", "name": "...",
    "contact": "...",                 // backend full; UI masks at render
    "intent": "...", "status": "captured" | "qualified" | "spam",
    "score": 0.0 } ]
```

### *GET /widgets/config* — admin
### *PUT /widgets/config* — admin

Request to PUT:
```json
{ "allowed_origins": ["https://..."], "theme_json": {...},
  "greeting": "string <=280 chars", "enabled": true }
```
Backend audit-logs each added/removed origin. UI passes the entire desired allow-list; backend computes the delta.

### *GET /tenants/{tid}/audit-logs* — admin

Response 200:
```json
[ { "created_at": "iso", "actor_role": "tenant_admin",
    "actor_name": "...", "action": "widget.origin_added",
    "metadata": { ... } } ]
```
Tenant admin: `tid` MUST equal JWT `tenant_id` (server enforces 403 cross-tenant).
Tenant manager: `tid` may be any tenant.

### *GET /tenants/{tid}/usage?days=30* — admin

Response 200:
```json
{ "total_tokens": 12345, "total_cost_usd": 3.45,
  "by_feature": { "chat": { "tokens": ..., "cost_usd": ... }, ... },
  "daily_cost_usd": [ { "date": "yyyy-mm-dd", "cost_usd": 0.12 }, ... ] }
```

---

## Net-new endpoints needed by this UI

All listed below are NEW — built in Phase 2A. See [missing-endpoints.md](missing-endpoints.md) for full shapes and [tasks.md](../tasks.md) for the implementing tasks.

- **GET / PUT /tenants/{tid}/agent-config**
- **GET /tenants/{tid}/platform-guardrails**
- **PATCH /escalations/{id}**
- **GET /escalations?tenant_id={tid}** — list-by-tenant
- **GET /tenants/{tid}/admin-users** — feeds the escalation-assignee dropdown
- **PUT /tenants/{tid}/settings** — TM-scope
- **POST /admin/invites/{token}/revoke**
- **POST /admin/invites/{token}/resend**
- **PUT /cms/pages/{id}** — CMS edit
- **PATCH /cms/pages/{id}/status** — publish / unpublish
- **DELETE /cms/pages/{id}** — soft delete
- **GET /tenants** — TM tenants table (admin-JWT-gated; legacy `/tenants/*` platform-actor route untouched)
- **GET /audit-logs** — TM platform-wide feed

---

## Error contract (consistent across all admin routes)

| Status | UI handler |
|---|---|
| 200/201 | render success state |
| 401 | clear `admin_token`, `st.rerun()` → login |
| 403 | render inline "Not authorized" (no redirect) |
| 404 | render "(placeholder)" fallback if read; inline error if write |
| 409 | render "Conflict — refresh and retry" |
| 422 | parse `{ "errors": [...] }`, render per-field inline |
| 5xx | render generic "Something went wrong, please try again" |
