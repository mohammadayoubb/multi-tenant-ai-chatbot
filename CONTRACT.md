# Owner: All
# Team Contract - Concierge

This contract is the shared working agreement for the Concierge group project.
Every member must read it before editing code.

`Agent.md` remains the main safety and phase-order source of truth. This file
turns those rules into practical ownership, naming, and interface contracts. If
this file conflicts with `Agent.md`, follow `Agent.md` first, then update this
contract with team agreement.

## 1. Main Rule

Tenant isolation is the highest priority.

Tenant A must never access Tenant B data, vectors, leads, conversations,
embeddings, prompts, widget config, costs, sessions, audit logs, or traces.

No member may weaken tenant isolation, guardrails, auth, or redaction to make a
feature easier.

## 2. Team Ownership

| Member | Name | Owns |
| --- | --- | --- |
| A | Hiba | Platform, PostgreSQL, tenancy, RLS, roles, provisioning, erasure, audit logs, cost/rate limits |
| B | Nasser | Agent, RAG, router, tools, memory, prompts, CMS behavior, leads, RAG/agent evals |
| C | Ayoub | Classifier, modelserver, guardrails, redaction, service-to-service auth, Vault, tracing |
| D | Amer | React widget, admin UI, widget auth UI flow, origin allowlist UI, Docker, CI/CD, smoke tests |

Path ownership follows the `# Owner: ...` header at the top of each file.
If a file has no owner header, ask the team before editing it.

## 2.1 Assignment Notes From The PDF

The assignment PDF confirms that Owner A owns the platform and isolation slice.
For Hiba, this means:

- tenant model
- PostgreSQL schema for tenant/platform tables
- Alembic baseline and DB migrations for tenant/platform tables
- Postgres RLS policies
- per-request tenant context setup/reset
- three-role model: `tenant_manager`, `tenant_admin`, `member`
- Tenant Manager provisioning flow
- audit log
- per-tenant cost attribution
- per-tenant rate limiting
- tenant erasure path
- DESIGN.md scaling story for 10 tenants vs 1,000 tenants

The PDF also says the Monday skeleton is shared team work. Hiba may help with
the first `docker-compose` skeleton if the team agrees, but Dockerfiles, CI/CD,
and smoke tests remain Amer's long-term ownership in this repository contract.

## 2.2 Parallel Development Contract

This file is the source of truth for how the four parts connect. Each member can
work in parallel without waiting for another member as long as their code matches
the contracts below.

Internal implementation can change freely inside an owned file. Public contracts
must not change without updating this file first.

Public contracts include:

- route paths
- function names
- input fields
- output fields
- table names
- enum values
- error names/status codes

If a member needs another member's part, they should use the contract here, not
invent a new name.

## 2.3 Shared IDs And Types

Use these fields everywhere:

| Field | Type | Meaning |
| --- | --- | --- |
| `tenant_id` | UUID string | Trusted tenant identity |
| `widget_id` | UUID string | Public widget config identity |
| `session_id` | string | Visitor browser chat session |
| `conversation_id` | UUID string | Stored conversation identity |
| `page_id` | UUID string | CMS page identity |
| `chunk_id` | UUID string | RAG chunk identity |
| `lead_id` | UUID string | Captured lead identity |
| `ticket_id` | UUID string | Human escalation identity |
| `actor_id` | string | Authenticated user or system actor |
| `trace_id` | string | Request/trace correlation id |

Do not use alternate names such as `business_id`, `client_id`, `org_id`,
`customer_id`, `chat_id`, or `userTenantId`.

## 2.4 Shared Enums

Roles:

```text
tenant_manager
tenant_admin
member
visitor
```

Tenant statuses:

```text
active
suspended
erasing
erased
```

Router labels:

```text
faq
sales
support
spam
human_request
ambiguous
```

Chat routes:

```text
workflow
agent
blocked
escalate
```

Tool names:

```text
rag_search
capture_lead
escalate
```

## 2.5 Trusted Tenant Context Contract

All tenant-owned reads/writes must receive tenant identity from this trusted
context:

```python
class TenantContext:
    tenant_id: UUID
    actor_id: str | None
    actor_role: str
    widget_id: UUID | None
    session_id: str | None
    origin: str | None
```

Rules:

- Visitors never send trusted `tenant_id` in the body.
- Widget/chat routes derive `tenant_id` from a signed widget token.
- Admin routes derive `tenant_id` and role from authenticated server context.
- Repositories accept `tenant_id` as a required argument for tenant-owned data.
- RLS context must be set before tenant-owned DB queries and reset afterward.

## 2.6 Hiba Platform Contract

Hiba provides tenant identity, tenant lifecycle, RLS, audit, usage, and rate
limit services.

Required service functions:

```python
TenantService.provision_tenant(name: str, actor_id: str) -> TenantDomain
TenantService.suspend_tenant(tenant_id: UUID, actor_id: str, reason: str | None) -> TenantDomain
TenantService.erase_tenant(tenant_id: UUID, actor_id: str, reason: str | None) -> ErasureResult
TenantService.record_usage(tenant_id: UUID, usage: UsageEvent) -> None
TenantService.check_rate_limit(tenant_id: UUID, action: str) -> RateLimitResult
```

Required repository functions:

```python
TenantRepository.create(name: str) -> Tenant
TenantRepository.get_by_id(tenant_id: UUID) -> Tenant | None
TenantRepository.set_status(tenant_id: UUID, status: str) -> Tenant | None
TenantRepository.add_audit_log(
    tenant_id: UUID,
    actor_role: str,
    action: str,
    actor_id: str | None = None,
    metadata: dict | None = None,
) -> AuditLog
TenantRepository.list_audit_logs(tenant_id: UUID) -> list[AuditLog]
```

Required RLS helpers:

```python
set_tenant_context(session, tenant_id: UUID) -> None
reset_tenant_context(session) -> None
```

Tenant response:

```json
{
  "id": "uuid",
  "name": "string",
  "status": "active",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

Erasure response:

```json
{
  "tenant_id": "uuid",
  "status": "erased",
  "deleted_rows": {
    "cms_pages": 0,
    "rag_chunks": 0,
    "leads": 0,
    "conversations": 0,
    "widget_configs": 0
  },
  "deleted_blobs": 0,
  "deleted_sessions": 0,
  "trace_id": "string"
}
```

Usage event:

```json
{
  "tenant_id": "uuid",
  "feature": "chat|embedding|classifier|rag|agent",
  "units": 1,
  "unit_type": "tokens|requests|seconds",
  "estimated_cost_usd": 0.0,
  "trace_id": "string"
}
```

## 2.7 Nasser Agent/RAG Contract

Nasser provides the router, RAG retrieval, bounded agent, memory, and three
tools.

Required router function:

```python
route_message(message: str) -> str
```

Return one router label from section 2.4.

Required RAG function:

```python
retrieve_chunks(tenant_id: UUID, query: str, top_k: int = 5) -> list[RagChunk]
```

RAG chunk:

```json
{
  "chunk_id": "uuid",
  "tenant_id": "uuid",
  "page_id": "uuid",
  "text": "string",
  "score": 0.0,
  "source_title": "string"
}
```

Required agent function:

```python
run_agent(tenant_id: UUID, message: str, session_id: str) -> AgentResult
```

Agent result:

```json
{
  "answer": "string",
  "used_tools": ["rag_search"],
  "route": "agent",
  "citations": [],
  "escalated": false
}
```

The agent has exactly three tools:

```python
rag_search(tenant_id: UUID, query: str, top_k: int = 5) -> RagSearchResult
capture_lead(tenant_id: UUID, conversation_id: UUID, name: str | None, contact: str | None, intent: str) -> LeadResult
escalate(tenant_id: UUID, conversation_id: UUID, reason: str) -> EscalationResult
```

Tool result shapes:

```json
{
  "rag_search": {
    "answer": "string",
    "chunks": []
  },
  "capture_lead": {
    "lead_id": "uuid",
    "status": "captured"
  },
  "escalate": {
    "ticket_id": "uuid",
    "status": "escalated"
  }
}
```

Rules:

- The model may not provide trusted `tenant_id`.
- The agent loop max iterations is 5.
- The agent max token budget per turn is 4000.
- Redis memory keys must use `session:{tenant_id}:{session_id}`.

## 2.8 Ayoub Classifier/Guardrails Contract

Ayoub provides classifier, guardrails, redaction, service auth, Vault, and
tracing.

Classifier HTTP endpoint:

```text
POST /classify
```

Classifier request:

```json
{
  "tenant_id": "uuid",
  "text": "string",
  "trace_id": "string"
}
```

Classifier response:

```json
{
  "label": "faq|sales|support|spam|human_request|ambiguous",
  "confidence": 0.0,
  "latency_ms": 0,
  "model_version": "string"
}
```

Guardrails HTTP endpoint:

```text
POST /check
```

Guardrails request:

```json
{
  "tenant_id": "uuid",
  "text": "string",
  "direction": "input|output",
  "trace_id": "string"
}
```

Guardrails response:

```json
{
  "allowed": true,
  "reason": null,
  "redacted_text": "string"
}
```

Rules:

- Platform rails are mandatory for all tenants.
- Tenant rails can add restrictions but cannot weaken platform rails.
- Service-to-service calls require a Vault-backed service credential.
- Logs/traces must store redacted text only.
- Modelserver images must not include `torch` or `transformers`.

## 2.9 Amer Widget/Admin/CI Contract

Amer provides the widget, admin UI, widget token exchange UI flow, Docker, CI/CD,
and smoke tests.

Widget token endpoint:

```text
POST /widgets/token
```

Widget token request:

```json
{
  "widget_id": "uuid",
  "origin": "https://tenant-site.example"
}
```

Widget token response:

```json
{
  "token": "jwt",
  "expires_in": 900,
  "session_id": "string"
}
```

JWT claims:

```json
{
  "tenant_id": "uuid",
  "widget_id": "uuid",
  "origin": "https://tenant-site.example",
  "session_id": "string",
  "exp": 0
}
```

Chat endpoint:

```text
POST /chat
```

Chat request:

```json
{
  "message": "string",
  "session_id": "string"
}
```

Chat response:

```json
{
  "answer": "string",
  "route": "workflow|agent|blocked|escalate",
  "used_tools": ["rag_search"],
  "citations": [],
  "ticket_id": null
}
```

Rules:

- Widget tokens are stored in memory only.
- Do not store widget tokens in `localStorage`, cookies, or persistent browser storage.
- Server validates `origin` against tenant allowed origins.
- CORS and CSP are defense-in-depth, not authentication.

## 3. Do Not Edit Another Member's Files

Do not edit a file owned by another member unless one of these is true:

- The owner explicitly approves the change.
- The change is required to fix a broken integration and the owner is told.
- The team agrees to move ownership of that file.

When touching another member's file, add a short note in the PR description:

```text
Cross-owner change:
- File:
- Owner:
- Reason:
- Approved by:
```

## 4. Cross-Review Rules

Hiba must review before merge when a change touches:

- `tenant_id`
- RLS
- tenant-owned tables
- tenant-scoped repository queries
- tenant provisioning, suspension, erasure
- audit logs
- cost/rate limits

Ayoub must review before merge when a change touches:

- guardrails
- redaction
- Vault
- secrets
- service-to-service auth
- traces/logging of sensitive data

Amer must review before merge when a change touches:

- Dockerfiles
- `docker-compose.yml`
- GitHub Actions
- widget build/deploy flow
- smoke tests

Nasser must review before merge when a change touches:

- agent loop
- tools
- RAG
- CMS content behavior
- prompts
- agent/RAG evals

## 5. Protected Files

These files require explicit team confirmation before editing:

```text
.env.example
.gitignore
.dockerignore
docker-compose.yml
Makefile
.github/workflows/*
app/config.py
app/main.py
app/api/deps.py
app/api/middleware.py
app/core/security.py
app/core/logging.py
app/db/session.py
app/db/migrations/*
app/infra/vault.py
app/infra/guardrails.py
prompts/system.md
guardrails/rails/*
modelserver/model_card.json
eval_thresholds.yaml
```

## 6. Shared Naming Rules

Use `snake_case` for Python functions, variables, table names, columns, and JSON
fields.

Use `PascalCase` for Python classes and Pydantic models.

Use these ID names exactly:

| Entity | ID field |
| --- | --- |
| Tenant | `tenant_id` |
| Widget | `widget_id` |
| Session | `session_id` |
| Conversation | `conversation_id` |
| CMS page | `page_id` |
| RAG chunk | `chunk_id` |
| Lead | `lead_id` |
| Escalation ticket | `ticket_id` |
| User/actor | `actor_id` |
| Trace | `trace_id` |

Do not invent alternate names like `business_id`, `client_id`, `org_id`,
`customer_id`, `chat_id`, or `userTenantId` for tenant-scoped concepts.

## 7. Database Contract

Hiba owns the database safety contract.

Every tenant-owned table must include:

```text
tenant_id UUID NOT NULL
created_at
updated_at
```

Every repository query against a tenant-owned table must include an explicit
tenant filter:

```python
.where(Model.tenant_id == tenant_id)
```

Every pgvector/RAG similarity query must include:

```sql
WHERE tenant_id = :tenant_id
```

Tenant identity must come from trusted server context only. Never trust
`tenant_id` from a visitor request body.

## 8. Canonical Tables

Use these table names unless the team updates this contract:

| Table | Owner | Purpose |
| --- | --- | --- |
| `tenants` | Hiba | Tenant account and lifecycle status |
| `audit_logs` | Hiba | Tenant-scoped platform actions |
| `tenant_usage` | Hiba | Cost/rate limit tracking |
| `cms_pages` | Nasser/Hiba review | Tenant CMS content |
| `rag_chunks` | Nasser/Hiba review | Tenant-scoped vector chunks |
| `leads` | Nasser/Hiba review | Captured visitor leads |
| `conversations` | Nasser/Hiba review | Tenant-scoped chat conversations |
| `widget_configs` | Amer/Hiba review | Tenant widget config and allowed origins |
| `traces` | Ayoub/Hiba review | Redacted traces only |

## 8.1 Database Structure Contract

This is the shared DB structure all members must build against. Hiba owns the
database safety contract. Feature owners can implement behavior around these
tables, but table/column changes must be reviewed by Hiba and reflected here.

All tenant-owned tables must include:

```text
tenant_id UUID NOT NULL
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
```

### `tenants`

Owner: Hiba

Purpose: platform tenant account and lifecycle state.

```text
id UUID PRIMARY KEY
name VARCHAR(255) NOT NULL UNIQUE
slug VARCHAR(255) NOT NULL UNIQUE
status VARCHAR(50) NOT NULL
plan VARCHAR(50) NOT NULL
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
```

Allowed `status` values:

```text
active
suspended
erasing
erased
```

### `users`

Owner: Hiba/Amer review

Purpose: authenticated admin/platform users. This may be managed through
`fastapi-users`.

```text
id UUID PRIMARY KEY
email VARCHAR(320) NOT NULL UNIQUE
hashed_password TEXT NOT NULL
is_active BOOLEAN NOT NULL
is_superuser BOOLEAN NOT NULL
is_verified BOOLEAN NOT NULL
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
```

### `tenant_memberships`

Owner: Hiba

Purpose: maps users to tenant roles.

```text
id UUID PRIMARY KEY
tenant_id UUID NOT NULL REFERENCES tenants(id)
user_id UUID NOT NULL REFERENCES users(id)
role VARCHAR(50) NOT NULL
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
UNIQUE (tenant_id, user_id)
```

Allowed `role` values:

```text
tenant_manager
tenant_admin
member
```

### `audit_logs`

Owner: Hiba

Purpose: tenant-scoped audit trail for Tenant Manager and admin actions.

```text
id UUID PRIMARY KEY
tenant_id UUID NOT NULL REFERENCES tenants(id)
actor_id VARCHAR(255)
actor_role VARCHAR(50) NOT NULL
action VARCHAR(100) NOT NULL
metadata_json JSONB NOT NULL
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
```

Required audited actions:

```text
tenant.provisioned
tenant.suspended
tenant.erasure_requested
tenant.erased
tenant.rate_limited
widget.origin_added
widget.origin_removed
cms.page_created
cms.page_updated
cms.page_deleted
lead.captured
conversation.escalated
```

### `tenant_usage`

Owner: Hiba

Purpose: per-tenant cost and rate-limit accounting.

```text
id UUID PRIMARY KEY
tenant_id UUID NOT NULL REFERENCES tenants(id)
feature VARCHAR(50) NOT NULL
units INTEGER NOT NULL
unit_type VARCHAR(50) NOT NULL
estimated_cost_usd NUMERIC(12, 6) NOT NULL
trace_id VARCHAR(255)
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
```

Allowed `feature` values:

```text
chat
embedding
classifier
rag
agent
guardrails
```

### `tenant_rate_limits`

Owner: Hiba

Purpose: per-tenant configured rate limits.

```text
id UUID PRIMARY KEY
tenant_id UUID NOT NULL REFERENCES tenants(id)
action VARCHAR(100) NOT NULL
limit_count INTEGER NOT NULL
window_seconds INTEGER NOT NULL
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
UNIQUE (tenant_id, action)
```

### `widget_configs`

Owner: Amer/Hiba review

Purpose: widget identity, allowed origins, theme, and greeting.

```text
id UUID PRIMARY KEY
tenant_id UUID NOT NULL REFERENCES tenants(id)
widget_id UUID NOT NULL UNIQUE
allowed_origins_json JSONB NOT NULL
theme_json JSONB NOT NULL
greeting TEXT NOT NULL
enabled BOOLEAN NOT NULL
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
```

### `tenant_agent_configs`

Owner: Nasser/Ayoub/Hiba review

Purpose: tenant persona, enabled tools, and tenant-editable rails.

```text
id UUID PRIMARY KEY
tenant_id UUID NOT NULL REFERENCES tenants(id)
persona TEXT NOT NULL
enabled_tools_json JSONB NOT NULL
tenant_rails_json JSONB NOT NULL
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
```

Allowed enabled tools:

```text
rag_search
capture_lead
escalate
```

### `cms_pages`

Owner: Nasser/Hiba review

Purpose: tenant CMS content used by the public site and RAG.

```text
id UUID PRIMARY KEY
tenant_id UUID NOT NULL REFERENCES tenants(id)
title VARCHAR(255) NOT NULL
slug VARCHAR(255) NOT NULL
body TEXT NOT NULL
source_url TEXT
status VARCHAR(50) NOT NULL
created_by VARCHAR(255)
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
UNIQUE (tenant_id, slug)
```

Allowed `status` values:

```text
draft
published
archived
```

### `rag_chunks`

Owner: Nasser/Hiba review

Purpose: tenant-scoped chunks and embeddings for RAG.

```text
id UUID PRIMARY KEY
tenant_id UUID NOT NULL REFERENCES tenants(id)
page_id UUID NOT NULL REFERENCES cms_pages(id)
chunk_index INTEGER NOT NULL
text TEXT NOT NULL
embedding VECTOR NOT NULL
metadata_json JSONB NOT NULL
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
UNIQUE (tenant_id, page_id, chunk_index)
```

Every query against `rag_chunks` must include:

```sql
WHERE tenant_id = :tenant_id
```

### `conversations`

Owner: Nasser/Amer/Hiba review

Purpose: tenant-scoped visitor conversations.

```text
id UUID PRIMARY KEY
tenant_id UUID NOT NULL REFERENCES tenants(id)
widget_id UUID REFERENCES widget_configs(widget_id)
session_id VARCHAR(255) NOT NULL
status VARCHAR(50) NOT NULL
started_at TIMESTAMP NOT NULL
last_message_at TIMESTAMP
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
UNIQUE (tenant_id, session_id)
```

Allowed `status` values:

```text
open
escalated
closed
erased
```

### `messages`

Owner: Nasser/Ayoub/Hiba review

Purpose: redacted conversation messages and tool traces.

```text
id UUID PRIMARY KEY
tenant_id UUID NOT NULL REFERENCES tenants(id)
conversation_id UUID NOT NULL REFERENCES conversations(id)
role VARCHAR(50) NOT NULL
content_redacted TEXT NOT NULL
tool_name VARCHAR(100)
metadata_json JSONB NOT NULL
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
```

Allowed `role` values:

```text
visitor
assistant
tool
system
```

Do not store raw unredacted PII or secrets in `messages`.

### `leads`

Owner: Nasser/Hiba review

Purpose: captured visitor leads.

```text
id UUID PRIMARY KEY
tenant_id UUID NOT NULL REFERENCES tenants(id)
conversation_id UUID REFERENCES conversations(id)
name VARCHAR(255)
contact VARCHAR(255)
intent VARCHAR(255) NOT NULL
status VARCHAR(50) NOT NULL
quality_score NUMERIC(5, 4)
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
```

Allowed `status` values:

```text
captured
qualified
spam
erased
```

### `escalation_tickets`

Owner: Nasser/Hiba review

Purpose: human follow-up requests.

```text
id UUID PRIMARY KEY
tenant_id UUID NOT NULL REFERENCES tenants(id)
conversation_id UUID NOT NULL REFERENCES conversations(id)
reason TEXT NOT NULL
status VARCHAR(50) NOT NULL
assigned_to VARCHAR(255)
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
```

Allowed `status` values:

```text
open
in_progress
resolved
erased
```

### `traces`

Owner: Ayoub/Hiba review

Purpose: redacted observability and request trace data.

```text
id UUID PRIMARY KEY
tenant_id UUID NOT NULL REFERENCES tenants(id)
trace_id VARCHAR(255) NOT NULL
component VARCHAR(100) NOT NULL
event_name VARCHAR(100) NOT NULL
redacted_payload_json JSONB NOT NULL
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
```

Do not store raw secrets, raw prompts, or raw PII in `traces`.

### `erasure_jobs`

Owner: Hiba

Purpose: tracks right-to-erasure work.

```text
id UUID PRIMARY KEY
tenant_id UUID NOT NULL REFERENCES tenants(id)
requested_by VARCHAR(255) NOT NULL
status VARCHAR(50) NOT NULL
deleted_counts_json JSONB NOT NULL
started_at TIMESTAMP
completed_at TIMESTAMP
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
```

Allowed `status` values:

```text
pending
running
completed
failed
```

## 9. Hiba Interface Contract

Hiba-owned services should expose these names:

```python
TenantService.provision_tenant(...)
TenantService.suspend_tenant(...)
TenantService.erase_tenant(...)
TenantService.record_usage(...)
TenantService.check_rate_limit(...)
```

Hiba-owned repositories should expose these names:

```python
TenantRepository.create(...)
TenantRepository.get_by_id(...)
TenantRepository.set_status(...)
TenantRepository.add_audit_log(...)
TenantRepository.list_audit_logs(...)
```

RLS helpers should keep these exact names:

```python
set_tenant_context(session, tenant_id)
reset_tenant_context(session)
```

All Tenant Manager actions must call `add_audit_log`.

## 10. Nasser Interface Contract

The agent has exactly three tools:

```python
rag_search(...)
capture_lead(...)
escalate(...)
```

Do not add a fourth tool without updating this contract and `DECISIONS.md`.

RAG retrieval must keep this function name:

```python
retrieve_chunks(tenant_id, query, top_k=5)
```

Router behavior must keep this function name:

```python
route_message(message)
```

Agent tool calls must derive `tenant_id` from trusted context, never from tool
arguments supplied by the model.

## 11. Ayoub Interface Contract

Guardrails endpoint:

```text
POST /check
```

Guardrail request fields:

```text
tenant_id
text
```

Guardrail response fields:

```text
allowed
reason
```

Modelserver responses must include:

```text
label
confidence
latency_ms
model_version
```

No serving image may include `torch` or `transformers`.

## 12. Amer Interface Contract

Widget token exchange route:

```text
POST /widgets/token
```

Public chat route:

```text
POST /chat
```

Widget session/token payload fields:

```text
tenant_id
widget_id
origin
session_id
exp
```

The widget must store the token in memory only. Do not use `localStorage`,
cookies, or browser persistence for widget tokens.

## 13. API Route Naming

Use these route groups:

| Route | Owner | Purpose |
| --- | --- | --- |
| `POST /tenants` | Hiba | Provision tenant |
| `GET /tenants/{tenant_id}` | Hiba | Tenant metadata only |
| `POST /tenants/{tenant_id}/suspend` | Hiba | Suspend tenant |
| `DELETE /tenants/{tenant_id}` | Hiba | Erase tenant |
| `GET /cms/pages` | Nasser/Hiba review | List tenant CMS pages |
| `POST /cms/pages` | Nasser/Hiba review | Create tenant CMS page |
| `POST /widgets/token` | Amer/Hiba review | Issue widget token |
| `POST /chat` | Nasser/Amer/Hiba review | Visitor chat |

Routes must not accept trusted `tenant_id` in the request body. Path parameters
may identify a target tenant for Tenant Manager actions, but the actor's role
must come from auth/session context.

## 14. Config, Pyproject, Docker

`pyproject.toml` is shared backend configuration. Do not add dependencies without
checking the owner of the feature that needs them.

Dockerfiles and CI/CD are Amer-owned. Do not edit Dockerfiles or GitHub Actions
unless Amer approves.

Serving containers must stay lean. Do not add training-only libraries to serving
containers.

## 15. Testing Contract

Every behavior change needs tests.

Hiba tests must include:

- happy path for provisioning/suspension/erasure
- tenant isolation path
- audit log path
- role refusal path

Nasser tests must include:

- RAG tenant filter path
- agent tool-selection path
- tool schema validation path

Ayoub tests must include:

- guardrail refusal path
- redaction path
- model artifact validation path

Amer tests must include:

- widget token exchange path
- origin allowlist path
- smoke test path

## 16. Decision Rules

Update `DECISIONS.md` before or immediately after a major decision.

Major decisions include:

- changing tenant ID type
- adding/removing tables
- changing route names
- changing tool names
- changing auth/token flow
- changing model choice
- changing eval thresholds
- changing Docker/CI behavior

## 17. Pre-Merge Checklist

Before opening a PR, confirm:

- [ ] I changed only files I own, or I have owner approval.
- [ ] No hardcoded secrets.
- [ ] No `.env` committed.
- [ ] No raw PII, secrets, stack traces, or prompts in logs.
- [ ] Every tenant-owned table has `tenant_id UUID NOT NULL`.
- [ ] Every tenant-owned repository query is scoped by `tenant_id`.
- [ ] RLS or tenant scoping was reviewed by Hiba.
- [ ] Guardrails, redaction, Vault, or credentials were reviewed by Ayoub.
- [ ] Docker/CI changes were reviewed by Amer.
- [ ] Agent/RAG/tool changes were reviewed by Nasser.
- [ ] Tests were added or updated.
- [ ] `DECISIONS.md` was updated if needed.
- [ ] Lint, type check, and tests pass.
