# Owner: Hiba
# DECISIONS.md

## Decision 1 — Use Hybrid Router + Agent

Context: Not every message needs expensive agent reasoning.

Decision: Use a classifier router for easy cases and a bounded tool-calling agent for ambiguous or multi-step turns.

Consequences: Lower cost, better control, and more predictable behavior.

## Decision 2 — Use RLS + Repository Scoping

Context: Tenant isolation is the highest-risk requirement.

Decision: Enforce isolation with Postgres RLS and still filter by tenant_id inside repositories.

Consequences: RLS protects against forgotten filters, while repository scoping keeps the code explicit.

## Decision 3 — Use Signed Widget Tokens

Context: CORS only protects browsers and is not authentication.

Decision: The loader exchanges widget_id + origin for a signed, short-lived token.

Consequences: Raw curl requests with copied widget_id cannot access tenant chat APIs without a valid token.

## Decision 4 — Use UUID Tenant IDs and Audited Tenant Management

Context: Tenant isolation is easier to reason about when tenant identifiers are globally unique and platform actions are traceable.

Decision: Tenant and tenant-owned records use UUID identifiers, and tenant provisioning/suspension actions require the tenant_manager role plus a tenant-scoped audit log.

Consequences: Repository scoping can consistently filter on UUID tenant_id, and platform lifecycle actions have an auditable trail.

## Decision 5 — Track Usage, Rate Limits, and Erasure in Tenant Scope

Context: Hiba's platform slice needs cost attribution, configurable action limits, and traceable tenant erasure without leaking cross-tenant data.

Decision: Record usage as tenant-scoped events, check rate limits from tenant-scoped windows, and return erasure results with scoped deleted-row counts plus audit events.

Consequences: Platform controls can block over-limit tenants, attribute cost by tenant_id, and prove erasure actions through audit logs and erasure job metadata.

## Decision 6 — Enforce Tenant Isolation With Postgres RLS Policies

Context: Repository filters are necessary but not enough for the highest-risk tenant-owned tables.

Decision: The initial Hiba migration enables and forces RLS on tenant-owned tables, using `app.tenant_id` as the trusted Postgres session setting.

Consequences: Tenant-owned reads and writes require the server to set tenant context before queries, giving the database a second isolation boundary.
