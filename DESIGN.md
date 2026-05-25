# Owner: Hiba
# DESIGN.md — Concierge System Design

## Tenant Isolation

Every tenant-owned row must include `tenant_id`.

Isolation is enforced in three layers:

1. PostgreSQL Row-Level Security.
2. Repository-layer tenant scoping.
3. Tenant-filtered pgvector retrieval.

## Roles

| Role | Scope | Can Do |
|---|---|---|
| tenant_manager | Platform | Create/suspend/erase tenants, view aggregate usage |
| tenant_admin | Tenant | Configure CMS, widget, persona, guardrails, leads |
| member/visitor | Public widget | Chat with tenant-scoped agent |

The tenant manager must not read tenant conversations, leads, or private CMS content.

## Runtime Flow

1. Tenant admin creates CMS content.
2. Backend embeds CMS content using hosted embeddings.
3. Embeddings are stored in pgvector with tenant_id.
4. Visitor loads widget with widget_id.
5. Loader exchanges widget_id + origin for a short-lived signed token.
6. Chat request reaches FastAPI.
7. Token is verified and tenant context is set.
8. Classifier router decides easy path or agent path.
9. Agent can call only: `rag_search`, `capture_lead`, `escalate`.
10. Guardrails validate input/output.
11. Logs and traces are redacted before storage.
