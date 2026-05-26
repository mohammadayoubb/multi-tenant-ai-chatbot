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

## Decision 4 — Widget Token Endpoint Owns Rate Limit Baseline (Amer)

Context: `POST /widgets/token` is anonymous and Internet-facing. The platform-level per-tenant rate limiter (CONTRACT.md §2.6) cannot fire until the tenant is resolved, but the entire point of the token endpoint is that the attacker is *trying to discover which tenant a widget_id maps to*. Without an endpoint-level baseline, the spec's failure-uniformity guarantee (FR-007) is theoretical — an attacker can probe millions of (widget_id, origin) pairs cheaply.

Decision: The widget token exchange feature owns a per-IP and per-widget rate baseline at the token endpoint specifically (default 10/min/IP, 60/min/widget; configurable per FR-018). Hiba's platform-level per-tenant limiter layers on top after tenant resolution. Rate-limited refusals follow the same indistinguishability rules as validation refusals (FR-017): same 403 body bytes, same headers.

Consequences: Enumeration probes are throttled regardless of which check would fail. Sub-millisecond timing residuals remain a theoretical concern (FR-008a mitigates the gross signal via mandatory widget-lookup before every refusal). Legitimate shared-IP scenarios (corporate NAT) may occasionally trip the per-IP baseline — affected visitors see the same neutral "Widget unavailable" indicator and tenants can request elevated limits out-of-band.

References: specs/001-widget-token-exchange/spec.md FR-015–FR-019; clarification Q1.

## Decision 5 — Parallel-Track Build for Phase 7 (Widget) During Team Phase 0 (Amer)

Context: The constitution's Principle VI declares a phased build order (Phase 0 specs → Phase 1 platform → … → Phase 7 widget). Strict serial interpretation would push widget token exchange to week 2+ and miss the demo schedule. PROJECT_PLAN.md's five-day plan explicitly schedules Amer to deliver widget token exchange on Wednesday in parallel with Hiba's Phase-1 platform work and Nasser's Phase-2 RAG work. The constitution's actual prohibition (Principle VI bullet 2) is on *reaching into another phase's files*, not on parallel work that respects ownership.

Decision: Amer builds Phase-7 widget work in parallel with the team's Phase 0/1/2 work, staying strictly inside his owned files (frontend/widget/, admin/, app/api/routes/widgets.py, app/services/widget_*.py, app/repositories/widget_repo.py, app/domain/widget.py, tests/security/test_widget_token*.py, tests/unit/test_widget_service.py, tests/smoke/test_widget_token_smoke.py). All cross-slice dependencies — widget_configs schema, tenant.status state machine, add_audit_log function — are consumed via the contracts in CONTRACT.md, not by reading or editing other owners' files. The InMemoryWidgetRepository is a documented temporary affordance until Hiba's widget_configs migration lands; it is removed in that same PR cycle.

Consequences: This DECISIONS.md entry IS the explicit team agreement required by constitution §Development Workflow ("Work outside the current phase MUST require explicit team agreement before being merged"). Reviewers reading only the constitution will see Principle VI cited here and not flag the work as a violation. If a teammate believes the parallel-track interpretation is wrong, this is the place to challenge it.

References: constitution §Core Principles VI; specs/001-widget-token-exchange/plan.md Complexity Tracking row 1; PROJECT_PLAN.md Wednesday slot.
