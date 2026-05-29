# Track-1 endpoint contracts

The authoritative endpoint contracts for the 13 missing endpoints are owned by [`specs/009-concierge-ui/contracts/missing-endpoints.md`](../../009-concierge-ui/contracts/missing-endpoints.md). This file is a **delta layer** for 010 and does not duplicate the source.

This feature implements all 13 endpoints to the contract in 009 unchanged, with the following 010-specific notes layered on top.

## 010 deltas

### Auth dep selection (binding)

The 009 contract leaves several routes "auth dep TBD". Locked here:

| # | Endpoint | Auth dep | Role gate (in-service) |
|---|---|---|---|
| #1 | `PUT /tenants/{tid}/agent-config` | `require_tenant_admin` | none beyond dep |
| #2 | `GET /tenants/{tid}/agent-config` | `require_tenant_admin` OR `get_tenant_id_from_widget_token` | widget JWT only valid for `tid == jwt.tenant_id` |
| #3 | `GET /tenants/{tid}/platform-guardrails` | `require_tenant_admin` | none beyond dep |
| #4 | `PATCH /escalations/{id}` | `require_admin_session` | `tenant_admin` OR `tenant_manager` of the ticket's tenant |
| #5 | `GET /escalations?tenant_id={tid}` | `require_admin_session` | TM can query other tenants; TA scoped to JWT tenant |
| #6 | `GET /tenants/{tid}/admin-users` | `require_admin_session` | `tid == jwt.tenant_id` always |
| #7 | `PUT /tenants/{tid}/settings` | `require_admin_session` | service rejects if `role != "tenant_manager"` |
| #8 | `POST /admin/invites/{token}/revoke` | `require_admin_session` | service rejects cross-tenant unless TM |
| #9 | `POST /admin/invites/{token}/resend` | `require_admin_session` | as above |
| #10 | `PUT /cms/pages/{id}` | `require_tenant_admin` | row tenant == JWT tenant |
| #11 | `PATCH /cms/pages/{id}/status` | `require_tenant_admin` | as above |
| #12 | `DELETE /cms/pages/{id}` | `require_tenant_admin` | as above |
| #13a | `GET /tenants` (TM-scope, admin-JWT) | `require_admin_session` | TM only |
| #13b | `GET /audit-logs` (TM-scope) | `require_admin_session` | TM only |

### Audit-log emission per write (binding)

See [audit-vocabulary.md](audit-vocabulary.md) for the full vocabulary. Per endpoint:

- #1 PUT agent-config → `tenant.agent_config_updated`
- #4 PATCH escalation → up to **two** events: `escalation.status_changed` if status delta; `escalation.assignee_changed` if assignee delta. Per FR-002 each delta is its own event.
- #7 PUT settings → `tenant.settings_updated`
- #8 revoke → `admin.invite_revoked`
- #9 resend → `admin.invite_resent`
- #10 PUT cms → `cms.page_updated`
- #11 PATCH cms/status → `cms.page_published` or `cms.page_unpublished` per target status
- #12 DELETE cms → `cms.page_deleted`

Read endpoints (#2, #3, #5, #6, #13a, #13b) do **not** emit audit entries.

### Response shape for #11 publish (RAG re-index hook deferred)

#11 PATCH `/cms/pages/{id}/status` ships **without** the RAG re-index hook — that hook is the N1 follow-on (see BLOCKED.md). The route returns 200 with the updated row; the audit entry records the status change; downstream RAG indexing is a separate feature.

### Response shape for #5 list

The 009 contract listed `last_message_excerpt`. Until durable `messages` table writes ship (out of scope — see Assumption "messages table durable persistence is out of scope"), the field returns the value stored on `escalation_tickets.last_message_excerpt` (set at `escalate` tool invocation from the last redacted Redis memory entry). When a session has no captured excerpt, the field returns `""`.

### Cross-tenant 403 byte-uniform body

Every cross-tenant refusal returns:

```json
{ "error": "forbidden" }
```

with HTTP status 403 and no `WWW-Authenticate`, no per-case detail string. Validated by smoke probes in Phase D.

### Pagination

- #5 GET /escalations: no pagination; tenant-scoped list bounded at the natural escalation count (≤ hundreds per tenant in expected scale).
- #13b GET /audit-logs: supports `?since={iso}` `?until={iso}` `?actor_role` `?tenant_id` `?action` query params; cursor pagination deferred to a follow-on if list exceeds 1000 rows in practice.
- All other list endpoints: bounded at single-page-of-rows; pagination explicitly out of scope (FR-039 prevents new caching/indexing work).
