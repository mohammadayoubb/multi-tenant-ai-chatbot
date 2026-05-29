# Data Model — 010 fe/be integration retrofit

Phase 1 output. Names every entity touched by this feature, the new fields, the validation rules, and the audit events emitted on state transitions.

## Tables modified

### `admin_invites` (Track 1, migration 0005)

| Column | Type | Notes |
|---|---|---|
| `revoked_at` | `TIMESTAMPTZ NULL` | New. Set by `AdminInviteRepository.mark_revoked()`. Read by `accept()` to refuse revoked invites with the same canned response as expired ones. |

State transitions:

```
pending  ──┬──► used      (on accept)
           ├──► expired   (passive, expires_at < now())
           └──► revoked   (revoked_at set)
```

All three terminal states surface the same canned "invite unavailable" message to the public read endpoint — no enumeration channel.

### `tenant_settings` (Track 1, migration 0006)

| Column | Type | Notes |
|---|---|---|
| `tenant_id` | `UUID NOT NULL PK FK → tenants(id)` | RLS enforced via `tenant_isolation` policy. |
| `default_invite_ttl_seconds` | `INTEGER NOT NULL DEFAULT 604800` | 7 days. Clamped 3600 ≤ x ≤ 2592000 (1 hour to 30 days). |
| `rate_limit_chat_per_minute` | `INTEGER NOT NULL DEFAULT 30` | Clamped 1 ≤ x ≤ 600. |
| `rate_limit_token_per_minute` | `INTEGER NOT NULL DEFAULT 60` | Clamped 1 ≤ x ≤ 600. |
| `rate_limit_lead_per_session` | `INTEGER NOT NULL DEFAULT 5` | **Phase A3 add-column.** Used by Track-2 capture_lead bucket. Clamped 1 ≤ x ≤ 50. |
| `created_at` / `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | Updated on every PUT. |

Audit event on PUT: `tenant.settings_updated` with metadata `{actor_id, changed_fields: [name → (old, new)]}` (values redacted before persist).

### `tenant_agent_configs` (Track 1, no schema change — created in migration 0004, written in this feature)

Already exists. This feature implements the missing GET / PUT pair and consumes the row at runtime via the prompt loader.

| Field | Validation |
|---|---|
| `persona_name` | str, 1..80 chars |
| `greeting` | str, 1..280 chars |
| `tone` | enum: `professional`, `friendly`, `concise`, `playful` |
| `language` | ISO 639-1 code (`en`, `de`, `fr`, ...) |
| `business_rules` | str, 0..2000 chars; redacted before write |
| `chips` | `string[]`, length 0..6, each chip 1..40 chars |

State machine: single state (`active`); no soft-delete. Updates emit `tenant.agent_config_updated`.

### `escalation_tickets` (Track 2 — table from migration 0004, **first writes** in this feature)

Already created. Phase B2 lands `EscalationRepository.create()` so the `escalate` tool can produce real rows.

| Field | Validation |
|---|---|
| `ticket_id` | UUID PK, server-generated |
| `tenant_id` | FK → tenants(id), RLS-enforced |
| `conversation_id` | str (session_id from widget JWT) |
| `status` | enum: `pending` (default), `in_progress`, `resolved` |
| `assignee_id` | UUID FK → admin_users(actor_id); same-tenant FK constraint enforced at PATCH time |
| `opened_at` | TIMESTAMPTZ, server-set |
| `last_message_excerpt` | str ≤ 200 chars, redacted |

State transitions and audit events:

```
(none)   ── escalate tool ──►  pending     emits escalation.created
pending  ── PATCH #4         ─►  in_progress  emits escalation.status_changed
in_progress ── PATCH #4      ─►  resolved     emits escalation.status_changed
{any}    ── PATCH #4 assignee ─►  (assignee)   emits escalation.assignee_changed
```

A single PATCH that changes both status and assignee emits **two** separate audit entries (one per delta) — required by FR-002.

### `cms_pages` (Track 1, no schema change)

Already created. This feature implements PUT (#10), PATCH status (#11), DELETE (#12).

Status transitions and audit events:

```
draft  ── PATCH /status ─►  published    emits cms.page_published
            (RAG re-index hook OMITTED — N1 follow-on)

published ── PATCH /status ─► draft / archived  emits cms.page_unpublished

{any}  ── DELETE        ─►  archived (soft)  emits cms.page_deleted
            sets deleted_at = now()
```

### `leads` (Track 2, no schema change)

The `capture_lead` tool already writes here. Track-2 hardens the tool boundary:

| Field | Validation (NEW Pydantic schema) |
|---|---|
| `name` | optional, 1..200 chars |
| `contact` | optional, email-or-phone regex |
| `intent` | required, 1..1000 chars, redacted before persist |
| `tenant_id` | server-supplied from ChatService — **never from tool arguments** |
| `session_id` | server-supplied |
| `status` | default `new`; never settable from tool arguments |
| `quality_score` | computed server-side (existing logic); never from tool arguments |

Audit events: `lead.captured` on success; `lead.rate_limited` when bucket cap hit.

### `audit_logs` (no schema change, vocabulary expansion only)

The existing redaction-on-metadata pattern is preserved. See [contracts/audit-vocabulary.md](contracts/audit-vocabulary.md) for the full list of 16 new action strings (8 Track 1 + 8 Track 2).

## Redis keys

### Session memory (existing, contract restated)

- Key: `session:{tenant_id}:{session_id}`
- Value: JSON list of `{role, content (redacted), timestamp}` objects
- TTL: 1800 seconds (30 minutes)
- Max length: 12 messages (FIFO trim on append)
- Fail-soft: if Redis unavailable, chat continues without memory; one `memory.unavailable` audit per session.

### Rate-limit buckets

- New key: `lead:{tenant_id}:{session_id}` — Phase B'2.
- Backing: in-process dict in `RateLimiterService` (matches existing IP / widget buckets — not Redis-shared).
- Window: 1 hour rolling.
- Cap: `tenant_settings.rate_limit_lead_per_session`, default 5.

No new Redis key types introduced.

## Pydantic models (new)

### Track 1

| Model | Module | Forbidden fields |
|---|---|---|
| `AgentConfigPutRequest` | `app/schemas/agent_config.py` (new) | `tenant_id`, `actor_id`, `role`, `created_at`, `updated_at` |
| `AgentConfigResponse` | same | n/a |
| `PlatformGuardrailsResponse` | `app/schemas/guardrails.py` (new) | n/a |
| `EscalationListItem` | `app/schemas/escalation.py` (extend) | n/a |
| `EscalationPatchRequest` | same | `tenant_id`, `actor_id`, `ticket_id`, `opened_at` |
| `AdminUserListItem` | `app/schemas/admin_user.py` (new) | n/a |
| `TenantSettingsPutRequest` | `app/schemas/tenant_settings.py` (extend) | `tenant_id`, `created_at`, `updated_at` |
| `InviteRevokeResponse` | `app/schemas/admin_invite.py` (extend) | n/a |
| `InviteResendResponse` | same | n/a |
| `CmsPageUpdateRequest` | `app/schemas/cms.py` (extend) | `tenant_id`, `created_by`, `created_at`, `updated_at`, `deleted_at` |
| `CmsPageStatusPatchRequest` | same | everything except `status` |
| `TenantListItem` | `app/schemas/tenant.py` (extend) | n/a |
| `AuditLogFeedItem` | `app/schemas/audit.py` (new) | n/a |

All models use `model_config = ConfigDict(extra="forbid")`.

### Track 2

| Model | Module | Notes |
|---|---|---|
| `RouteDecision` | `app/agent/router.py` | extends existing dataclass to include `confidence: float` |
| `RagSearchArgs` | `app/agent/tools.py` | `query: str`, `top_k: int` (1..10 clamp), `extra="forbid"` |
| `CaptureLeadArgs` | same | `name`, `contact`, `intent` validated as per `leads` table above |
| `EscalateArgs` | same | `reason: str` (1..280 chars), `extra="forbid"`. No `conversation_id` (server-supplied) |

## Constraints summary

- Every new model: `extra="forbid"`.
- Every new repository method: takes `tenant_id` explicitly, validates server-side, sets RLS context.
- Every new write: emits an audit-log entry from the service layer (not the route).
- No new table. No new pgvector index. No new Redis key type.
