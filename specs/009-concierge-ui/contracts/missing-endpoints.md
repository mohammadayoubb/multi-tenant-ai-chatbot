# Missing Backend Endpoints

Thirteen endpoints referenced by this UI plan are **not yet shipped**. They are now in scope for this feature and land in Phase 2A alongside the UI work. This file is the contract every endpoint MUST satisfy when implemented.

Until Phase 2A merges, the UI renders `(placeholder)` rows and a visible badge for each as a development-time fallback. Production code paths assume the real endpoints.

---

## 1. `PUT /tenants/{tid}/agent-config`

**Status:** model exists in [app/db/models.py](app/db/models.py) (`TenantAgentConfig`). Needs repo + service + route.

Request:
```json
{ "persona_name": "Acme Concierge",
  "greeting": "Hi! How can I help?",
  "tone": "professional",
  "language": "en",
  "business_rules": "...",
  "chips": ["...", "...", "...", "...", "...", "..."]   // 0..6 strings
}
```
Validation: `chips` length 0..6; each chip 1..40 chars.

Response 200: echoes the persisted shape.

**Dev-time UI fallback:** Agent Settings page shows the four product-default chips + form fields read from a hard-coded sample dict.

---

## 2. `GET /tenants/{tid}/agent-config`

Pair to the above. Widget calls this on first panel open to load chips + greeting.

Response 200: same shape as the PUT request.

---

## 3. `GET /tenants/{tid}/platform-guardrails`

**Status:** no model, no route. Likely a thin read of `guardrails/main.py` state.

Response 200:
```json
{ "platform_rules": [
    { "id": "block_cross_tenant_probe", "name": "...", "locked": true },
    { "id": "block_pii_extraction",     "name": "...", "locked": true } ],
  "tenant_blocked_topics": [ "competitor_pricing", ... ],
  "tenant_refusal_tone": "polite" }
```

**Dev-time UI fallback:** Guardrails page renders 4 sample platform rules with "Locked by platform" badge + empty tenant section.

---

## 4. `PATCH /escalations/{id}`

**Status:** `EscalationTicket` model exists in [app/db/models.py](app/db/models.py). Needs repo + service + route.

Request:
```json
{ "status": "pending" | "in_progress" | "resolved",
  "assignee_id": "<uuid-of-admin-user-of-same-tenant>" | null }
```

Server enforces:
- `id` belongs to the JWT's tenant (403 otherwise).
- `assignee_id` references an `admin_users` row with the same `tenant_id` (422 otherwise).
- Status change and assignee change each emit an audit-log event.

Response 200: returns the updated ticket.

**Dev-time UI fallback:** Escalations page shows 3 sample tickets; PATCH attempts no-op and show a toast "Endpoint not yet available".

---

## 5. `GET /escalations?tenant_id={tid}`

List endpoint for the Escalations table. Server scopes by JWT tenant; the query param is for the manager view only and is rejected when issued by a tenant_admin JWT for a different tenant.

Response 200:
```json
[ { "ticket_id": "<uuid>", "opened_at": "iso",
    "last_message_excerpt": "...",
    "status": "pending",
    "assignee_id": "<uuid>" | null,
    "assignee_name": "..." | null } ]
```

---

## 6. `GET /tenants/{tid}/admin-users`

**Status:** `admin_users` table exists. Needs a tiny read endpoint.

Server enforces: `tid` MUST equal the JWT's tenant_id (no cross-tenant read).

Response 200:
```json
[ { "actor_id": "<uuid>", "full_name": "Jane Doe", "email": "...",
    "role": "tenant_admin", "status": "active" } ]
```

Used exclusively by the Escalations assignee dropdown. **MUST NOT** be used for any other surface; emails are returned because the dropdown shows "Jane Doe (jane@acme.com)" for disambiguation.

**Dev-time UI fallback:** Escalations dropdown shows "(no admin users available — endpoint pending)" with the assign control disabled.

---

## 7. `PUT /tenants/{tid}/settings`

**Status:** no model yet. Scope of "settings" is specified below; `tenant_settings` table is introduced in migration `0006_tenant_settings.py` (task T034).

Request shape:
```json
{ "default_invite_ttl_seconds": 604800,
  "rate_limit_chat_per_minute": 30,
  "rate_limit_token_per_minute": 60 }
```

Server enforces: only `tenant_manager` role; values inside published min/max bounds; saving requires a confirmation modal client-side (FR-045).

**Dev-time UI fallback:** Settings page renders the form with placeholder values and a "Save" button that no-ops with a `(placeholder)` toast.

---

## 8. `POST /admin/invites/{token}/revoke`

**Status:** no route in [app/api/routes/admin_invites.py](app/api/routes/admin_invites.py). Repo has the row.

Requires adding a `revoked_at` column to `admin_invites` + a service method that:
- Refuses if `used_at` is set (returns 409).
- Refuses if the invite belongs to a different tenant than the caller's JWT tenant (returns 403).

Response 200: `{ "ok": true, "revoked_at": "iso" }`

---

## 9. `POST /admin/invites/{token}/resend`

**Status:** no route.

Re-mints token (issuing a new UUID), extends `expires_at` to `now + default_ttl`, returns the new token + URL.

Server enforces:
- Caller's JWT tenant matches invite's tenant (or caller is tenant_manager).
- Original invite is not `used` or `revoked` (else 409).

Response 200: same shape as `POST /admin/invites`.

---

## 10. `PUT /cms/pages/{id}`

**Status:** no route. `POST /cms/pages` (create) is shipped; edit is not.

Request:
```json
{ "title": "...", "slug": "...", "body": "markdown",
  "source_url": "https://...", "status": "draft" | "published" | "archived" }
```
Server enforces:
- Row's `tenant_id` MUST equal JWT `tenant_id` (403 otherwise).
- Body MUST NOT contain `tenant_id` (`extra=forbid`).
- Successful edit MUST emit an audit-log entry `cms.page_updated`.

Response 200: returns the updated row.

**Dev-time UI fallback:** Edit form disabled with a `(placeholder)` toast on save.

---

## 11. `PATCH /cms/pages/{id}/status`

**Status:** no route.

Request:
```json
{ "status": "draft" | "published" | "archived" }
```
Server enforces:
- Tenant scope as above.
- Successful change MUST emit `cms.page_published` or `cms.page_unpublished` audit-log event.
- Re-indexes the RAG vector store on publish (via the existing `app/rag/ingest.py` ingest path).

Response 200: returns the row.

**Dev-time UI fallback:** Publish / Unpublish buttons disabled with a `(placeholder)` toast.

---

## 12. `DELETE /cms/pages/{id}`

**Status:** no route.

Server enforces:
- Tenant scope as above.
- Soft-delete preferred (sets `archived` status + `deleted_at` timestamp) so audit trail is preserved.
- Successful delete MUST emit `cms.page_deleted` audit-log event.
- Re-indexes the RAG vector store to drop the page's chunks.

Response 204: empty body.

**Dev-time UI fallback:** Delete button disabled with a `(placeholder)` toast.

---

## 13. `GET /tenants` and `GET /audit-logs` (TM-scope)

These are the platform-wide reads for the Tenant Manager Tenants and Audit Logs tabs. The legacy `/tenants/*` routes (with platform-actor headers) exist but use a different auth path. Decision (Phase 2A tasks T039u + T039v): add admin-JWT-gated `GET /tenants` and `GET /audit-logs` alongside the legacy routes. The legacy routes remain for backward compatibility with any internal scripts; the UI consumes only the new admin-JWT-gated paths.

**Until T039u / T039v merge,** the TM Tenants and Audit Logs tabs render 4 sample rows with a `(placeholder)` badge.

---

## Roll-up table

| # | Endpoint | Backend state pre-Phase-2A | Phase 2A task(s) | Dev-time UI fallback |
|---|---|---|---|---|
| 1 | `PUT /tenants/{tid}/agent-config` | Model exists; needs route | T038 / T039 / T039a | Sample agent config + chips |
| 2 | `GET /tenants/{tid}/agent-config` | Model exists; needs route | T038 / T039 / T039a | Hard-coded chip defaults |
| 3 | `GET /tenants/{tid}/platform-guardrails` | No model, no route | T039i / T039j | 4 sample rules |
| 4 | `PATCH /escalations/{id}` | Model exists; needs route | T039c / T039d / T039e | Action disabled |
| 5 | `GET /escalations?tenant_id={tid}` | Model exists; needs route | T039c / T039d / T039e | 3 sample tickets |
| 6 | `GET /tenants/{tid}/admin-users` | Table exists; needs route | T039f / T039g | Dropdown disabled |
| 7 | `PUT /tenants/{tid}/settings` | No model, no route | T034 / T039l / T039m / T039n | Form no-ops |
| 8 | `POST /admin/invites/{token}/revoke` | No route, column add needed | T033 / T035 / T036 / T037 | Action disabled |
| 9 | `POST /admin/invites/{token}/resend` | No route | T035 / T036 / T037 | Action disabled |
| 10 | `PUT /cms/pages/{id}` | No route | T039p / T039q / T039r | Edit form disabled |
| 11 | `PATCH /cms/pages/{id}/status` | No route | T039p / T039q / T039r / T039s | Publish/Unpublish disabled |
| 12 | `DELETE /cms/pages/{id}` | No route | T039p / T039q / T039r | Delete disabled |
| 13a | `GET /tenants` (TM scope) | Legacy path exists; needs admin-JWT equiv | T039u | 4 sample tenants |
| 13b | `GET /audit-logs` (TM scope) | Legacy path exists; needs admin-JWT equiv | T039v | Sample feed |
