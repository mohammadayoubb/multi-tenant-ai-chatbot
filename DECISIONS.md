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

## Decision 6 — Widget loader stays hand-authored, not bundled (Amer, 2026-05-27)

Context: Feature 003 production-hardens [frontend/widget/public/widget.js](frontend/widget/public/widget.js) and adds [frontend/widget/vite.config.ts](frontend/widget/vite.config.ts). Two implementation paths were available: (a) keep the loader hand-authored at ES2019 syntax and let Vite's `public/` mechanism copy it verbatim, or (b) route the loader through a Vite library build with `target: 'es2019'` and `format: 'iife'`.

Decision: Keep the loader hand-authored. The new `vite.config.ts` sets `build.target: 'es2019'` for the React iframe app only. The loader ships byte-identical to its source: `dist/widget.js` SHA-256 equals `public/widget.js` SHA-256 after every build.

Consequences: PR diffs touch the actual shipping artifact, not bundler output — reviewers (especially for widget auth surface, which is constitution-risky) read what tenants execute. A vitest case enforces the ES2019 baseline by scanning the source for forbidden post-ES2019 syntax tokens and any `import` statements, so a developer reflexively typing `?.` or `await` at top level fails CI. The contract entity that mediates this — Vite's `public/` passthrough — is a documented Vite feature, not custom plumbing.

References: specs/003-widget-loader-hardening/research.md §R1, §R2, §R3; specs/003-widget-loader-hardening/contracts/widget-loader.md §C8.

## Decision 7 — Widget admin config: mock role dep, deferred schema columns, AuditLogger Protocol (Amer, 2026-05-27)

Context: Feature 004 ships the tenant-admin widget configuration page (`GET /widgets/config`, `PUT /widgets/config`, plus the Streamlit page). Three integration constraints needed an explicit decision rather than a silent workaround:

1. The platform's authenticated `tenant_admin` role dependency (Hiba-owned) does not exist yet.
2. The `widget_configs` table is missing two columns (`theme_json JSONB`, `greeting TEXT`) that this feature reads and writes.
3. Hiba's `TenantRepository.add_audit_log` is documented (CONTRACT.md §190) but not yet implemented.

Decision:

- **Role dep**: a mock `require_tenant_admin` in [app/api/deps.py](app/api/deps.py) reads `X-Concierge-Role` / `X-Concierge-Tenant-Id` headers, returns `Optional[TenantAdminContext]`, and refuses to operate outside `CONCIERGE_ENV=dev`. The route checks for `None` and emits the canonical 403 byte-response. Swap-replaceable by Hiba's real dep with a one-line import change once it lands.
- **Schema-pending columns**: `theme_json` and `greeting` are added to the `WidgetConfigDomain` Pydantic model with `None` defaults and are persisted via the existing `InMemoryWidgetRepository`. No SQL migration is shipped in this PR. **Tagged for Hiba review**; the SQL adapter (which currently raises `NotImplementedError`) lands in the PR that introduces Hiba's `widget_configs` column-add migration.
- **Audit logger**: a single-method `AuditLogger` Protocol in [app/services/widget_service.py](app/services/widget_service.py) defines the contract surface this feature consumes. The route wires a `_StubAuditLogger` no-op until Hiba's `TenantRepository.add_audit_log` is implemented; tests inject a fake via `app.dependency_overrides`. The two audit action strings `widget.origin_added` and `widget.origin_removed` are pre-existing entries in the audit vocabulary at CONTRACT.md:736-737 — no contract change needed.

Consequences: The feature ships behind two clearly-marked, swap-replaceable affordances (role dep + audit stub). Production cannot accidentally execute the affordances: the role-dep mock refuses non-dev environments, and the audit stub silently returns `None` (acceptable until Hiba's implementation ships because no production tenant-admin auth exists yet). Fail-closed semantics (FR-013, contract clause E2) are exercised in tests by injecting a fake `AuditLogger` that raises; the route catches and returns `{"error":"internal"}` 500. When Hiba's deps land, three locations swap: `require_tenant_admin` import in the route, `get_audit_logger` factory in the route, and the `widget_repo` SQL adapter implementation.

References: specs/004-widget-admin-config/research.md §R1, §R2; specs/004-widget-admin-config/plan.md Complexity Tracking; specs/004-widget-admin-config/contracts/audit-log-consumption.md §A1-A6.
