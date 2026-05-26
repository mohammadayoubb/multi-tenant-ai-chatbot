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
