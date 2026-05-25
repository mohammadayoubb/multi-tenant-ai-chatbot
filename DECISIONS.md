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
