# Implementation Plan: Concierge frontend / backend integration retrofit

**Branch**: `010-fe-be-integration` | **Date**: 2026-05-29 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/010-fe-be-integration/spec.md`

## Summary

Two tracks, single feature. **Track 1** closes the 13 missing endpoints from [009-concierge-ui/contracts/missing-endpoints.md](../009-concierge-ui/contracts/missing-endpoints.md) and removes every `(placeholder)` caption from the 10 affected admin pages. **Track 2** graduates the stub router and stub agent in [app/agent/](../../app/agent/) to the production shape mandated by [Concierge_Backend_Blueprint.md](../../Concierge_Backend_Blueprint.md): real ONNX classifier with a confidence threshold, a single tool-calling LLM with hard loop bounds, three hardened tools (`rag_search` lexical baseline, `capture_lead` with Pydantic schema + per-session rate limit, `escalate` with real `escalation_tickets` INSERT), Redis short-term memory with a justified 1800 s TTL, and version-controlled prompts at [app/prompts/system_prompt.md](../../app/prompts/system_prompt.md) parsed at runtime into PLATFORM_SYSTEM (locked) + TENANT_PERSONA (injected from `tenant_agent_configs`) + TOOL_SCHEMAS (generated from Pydantic).

**Load-bearing rule:** the frontend never decides tenant identity or role. `tenant_id`, role, and `actor_id` come only from server-issued JWTs; every request body uses Pydantic `extra=forbid`.

## Technical Context

**Language/Version**: Python 3.11+ (backend, admin), TypeScript 5 / React 18 (widget)
**Primary Dependencies**: FastAPI (async), SQLAlchemy 2 (async), Streamlit (admin), Vite + React (widget), Redis client, HTTPX, PyJWT, bcrypt, Pydantic v2. New for Track 2: an LLM tool-calling SDK — see [research.md §R1](research.md) for the deferred vendor choice (default recommendation: Anthropic Claude via `anthropic` SDK; OpenAI function-calling rejected as fallback).
**Storage**: PostgreSQL 15 + pgvector; Redis 7 (session memory only — no durable writes in this feature); HashiCorp Vault (secrets)
**Testing**: pytest (unit / integration / smoke / security), vitest (widget), Streamlit `AppTest` (admin), existing CI eval gates in [evals/](../../evals/)
**Target Platform**: Docker Compose stack ([docker-compose.yml](../../docker-compose.yml)) — Linux containers, no new service
**Project Type**: Multi-tenant SaaS web service with embeddable React widget + Streamlit admin
**Performance Goals**:
- Admin loading indicators visible within 200 ms of any fetch (FR-013)
- Widget chat round-trip uses synchronous request/response — agent path bounded at 5 tool iterations / 4000 tokens (FR-019)
- Across 100 sampled messages, ≥ 80 % served by workflow path; ≤ 20 % reach the agent (SC-003)
**Constraints**:
- No new Compose service, no new container image (FR-035; Decision 11 lean-image audit must remain green)
- No new dev-header auth surface (FR-036)
- Exactly 2 new migrations: `0005_admin_invites_revoked_at.py`, `0006_tenant_settings.py` + 1 ADD COLUMN (FR-037)
- No writes to `rag_chunks`, `messages`, or `traces` tables (FR-039)
- All 5 existing eval gates + lean-image-audit + smoke-e2e must remain green (FR-040, FR-041)
**Scale/Scope**: 13 new endpoints, 10 admin pages re-wired, 3 tools hardened, 1 router upgrade, 1 agent loop replacement, 1 prompt loader, ~30 new test files, ~16 new audit-log vocabulary entries (8 Track 1 + 8 Track 2)

## Constitution Check

*GATE: must pass before Phase 0 research. Re-evaluated after Phase 1 design.*

- [x] **Principle I (Tenant Isolation):** Every new repository method takes `tenant_id` explicitly OR sets `app.tenant_id` via the existing `TenantRepository._tenant_context()` pattern (FR-038). All Pydantic request bodies use `extra=forbid` so `tenant_id` / `actor_id` / `role` cannot be smuggled in (FR-003, FR-021). The agent's three tools derive `tenant_id` only from the `ChatService` trusted parameter sourced from the verified widget JWT (FR-022). No pgvector query is added (FR-039 — `rag_chunks` untouched). RLS policies untouched (FR-038). No new tenant-owned table is added; existing ones gain only `revoked_at` (`admin_invites`) and an additive `tenant_settings` row.
- [x] **Principle II (Layered Architecture):** Every new endpoint follows the route → service → repository triplet (Phase B task-per-endpoint structure). Routes contain no SQL; services own business logic (audit emission, role gating); repositories own queries (tenant-scoped). The agent (`app/agent/agent.py`) sits in the same layer as services and consumes repositories via existing service shims — it does not write SQL.
- [x] **Principle III (Bounded Agent):** No tool added, removed, or renamed. The three tools remain `{rag_search, capture_lead, escalate}` (FR-018). Loop caps remain `MAX_AGENT_ITERATIONS = 5`, `MAX_AGENT_TOKENS_PER_TURN = 4000` (FR-019). Every tool call schema-validated via Pydantic `extra=forbid` (FR-021). Every tool derives `tenant_id` from trusted context (FR-022). Platform refusal patterns remain in PLATFORM_SYSTEM block of `system_prompt.md` and cannot be weakened by tenant persona (FR-034).
- [x] **Principle IV (Defense-in-Depth Auth):** Widget token storage remains module-scope memory (FR-012). No `localStorage` / cookie surface added. CORS/CSP unchanged. Admin JWT signed HS256 via Vault-resolved `ADMIN_JWT_SECRET` (no new secret material — FR-036). Widget JWT signed HS256 via Vault-resolved `WIDGET_JWT_SECRET`. No new dev-header surface (FR-036). LLM provider API key (Track 2) resolved via Vault, not `.env`.
- [x] **Principle V (Lean Serving & Redaction):** No `torch` or `transformers` added to `modelserver` / `guardrails` containers (FR-035). The LLM provider SDK (anthropic / openai) lives in the `api` container, which is not a serving container under the lean-image-audit definition — verified in [research.md §R3](research.md). All persisted free-text passes through `app/infra/redaction.py` before write (FR-024, FR-028). No raw stack traces leaked to client (FR-007 — toast message is friendly only).
- [ ] **Principle VI (Phased Build):** **VIOLATION CITED — see Complexity Tracking row 1.** This feature touches Phase 4 (classifier router), Phase 5 (agent loop + tools + memory + prompts), and Phase 8 (admin UI) in the same feature. Justified per DECISION 17 precedent (Phase 2A bundling) and the explicit project-lead approval of the `backend-spec.md` Track 1 + Track 2 scope. Per the lifted-ownership policy (see auto-memory `feedback_ownership_policy.md`), per-owner phase lanes no longer apply; this principle still gates *unrelated* work being pulled into a feature, which the load-bearing seams in Complexity Tracking row 1 demonstrate is not the case here.
- [x] **Principle VII (Clean & Simple Code):** Smallest defensible implementation everywhere. Refactors and cleanup deferred to Phase E (post-merge of A–D); no refactor blocks endpoint or page delivery. No new abstractions introduced beyond what the contracts require. Existing canonical ID naming (`tenant_id`, never `business_id` etc.) preserved.

**Result:** 6 / 7 principles pass on first check. The one violation (Principle VI) is justified in Complexity Tracking with the simpler alternative ("ship two separate features") explicitly rejected.

## Project Structure

### Documentation (this feature)

```text
specs/010-fe-be-integration/
├── plan.md              # This file
├── research.md          # Phase 0 — vendor + threshold + lean-image decisions
├── data-model.md        # Phase 1 — entities for the 13 endpoints + Track-2 deltas
├── contracts/
│   ├── missing-endpoints.md          # Track-1 source of truth (re-references 009/)
│   ├── agent-internals.md            # Track-2 contracts (RouteDecision, tool schemas, prompt blocks, audit vocab)
│   └── audit-vocabulary.md           # New audit-log action strings (Track 1 + Track 2)
├── quickstart.md        # How a reviewer validates each phase end-to-end
├── checklists/
│   └── requirements.md  # (already created)
└── tasks.md             # Phase 2 output — generated by /speckit-tasks (NOT this command)
```

### Source Code (repository root)

Existing layout preserved. Touched paths:

```text
app/
├── api/
│   ├── deps.py                       # No new deps; existing ones reused
│   └── routes/
│       ├── admin_invites.py          # + revoke + resend routes
│       ├── cms.py                    # + PUT / PATCH status / DELETE routes
│       ├── escalations.py            # + GET ?tenant_id + PATCH /{id} routes
│       ├── tenants.py                # + agent-config GET/PUT, platform-guardrails GET,
│       │                             #   admin-users GET, settings PUT, TM-scope tenants GET
│       └── (new) admin_audit.py      # TM-scope /audit-logs GET
├── agent/
│   ├── router.py                     # Track-2 B'1: real modelserver call + confidence rule
│   ├── tools.py                      # Track-2 B'2: Pydantic schemas + rate limit + real escalate INSERT
│   └── agent.py                      # Track-2 B'3: real LLM tool-calling loop with caps
├── prompts/
│   ├── system_prompt.md              # Track-2 B'3: split into named blocks (file format change only)
│   └── (new) loader.py               # Parse + inject tenant persona at runtime
├── repositories/
│   ├── admin_invite_repo.py          # + mark_revoked
│   ├── admin_user_repo.py            # + list_by_tenant
│   ├── agent_config_repo.py          # + get_by_tenant + upsert
│   ├── escalation_repo.py            # + create()  (the load-bearing Track-2 prerequisite)
│   └── tenant_repo.py                # + list_for_manager + list_all_audit_logs
├── services/
│   ├── admin_invite.py               # + revoke() + resend()
│   ├── agent_config.py               # implement get / put
│   ├── chat_service.py               # consume new RouteDecision; emit memory.unavailable audit on Redis miss
│   ├── platform_guardrails.py        # + read() for admin UI
│   ├── rate_limiter.py               # + bucket type: lead:{tenant_id}:{session_id}
│   └── tenant_service.py             # + list_for_manager
└── db/
    └── migrations/versions/
        ├── 0005_admin_invites_revoked_at.py   # Already drafted — verify in A1
        └── 0006_tenant_settings.py            # Already drafted — verify in A2 + ADD COLUMN in A3

admin/
├── overview_page.py                  # Phase C: real KPIs from #1, #4, #5
├── agent_settings_page.py            # Phase C: real read/write via #1/#2
├── guardrails_page.py                # Phase C: real read via #3
├── escalations_page.py               # Phase C: real read/patch via #4, #5; assignee dropdown via #6
├── cms_page.py                       # Phase C: edit/publish/delete via #10/#11/#12
├── invites_page.py                   # Phase C: revoke/resend via #8/#9
├── settings_page.py                  # Phase C: real PUT via #7
├── tenants_page.py                   # Phase C: TM list via #13a
└── audit_page.py                     # Phase C: TM feed via #13b

frontend/widget/src/
└── api.ts                            # Phase C: fetchAgentConfig already calls #2 — keep
                                      #          AGENT_CONFIG_PLACEHOLDER as fail-soft only

tests/
├── unit/
│   ├── test_migrations.py            # NEW — Phase A
│   ├── test_router.py                # EXTEND — Phase B'1
│   ├── test_agent_loop.py            # NEW — Phase B'3
│   └── test_tool_schemas.py          # NEW — Phase B'2
├── integration/
│   ├── test_admin_*_page.py          # 10 new files — Phase C
│   ├── test_{endpoint}.py            # 13 new files — Phase B
│   ├── test_capture_lead_rate_limit.py    # NEW — Phase B'2
│   ├── test_escalate_real_ticket.py        # NEW — Phase B'2
│   └── test_chat_agent_path.py             # NEW — Phase B'3
├── security/
│   └── test_agent_prompt_injection.py      # NEW — Phase B'2
└── smoke/
    └── test_cross_tenant_e2e.py            # EXTEND — Phase D: +8 probes

evals/
└── agent_tool.py                     # Phase B'3: graduate from mock to real evaluator (closes BLOCKED.md N6)

.github/workflows/
└── ci.yml                            # Phase D: flip SMOKE_E2E_REQUIRE_FULL_STACK when probes pass
```

**Structure Decision**: Existing multi-module layout preserved. Backend = [app/](../../app/), admin UI = [admin/](../../admin/), widget = [frontend/widget/](../../frontend/widget/), evals = [evals/](../../evals/). No new top-level directory. No new Compose service. No new docs directory outside `specs/010-fe-be-integration/`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| **Principle VI (Phased Build) — feature spans Phases 4, 5, and 8** | The 13 missing endpoints (Phase 8 surface) and the agent retrofit (Phase 4/5 surface) share two load-bearing seams: (a) the `EscalationRepository.create()` method that the `escalate` tool needs is the same one that `PATCH /escalations/{id}` (#4) needs rows from; (b) the prompt loader's tenant persona block is sourced from `PUT /tenants/{tid}/agent-config` (#1) and `GET /tenants/{tid}/agent-config` (#2). Shipping the two phases separately would require either stubbing the seam twice (in Phase 8 then ripping out for Phase 5) or shipping Phase 5 against a placeholder agent-config — both worse than bundling. | Splitting into two features (one per phase) was rejected because (i) the integration would then require a third feature to wire the seams, (ii) the placeholder-fallback UX would persist for two more release cycles on the admin pages most demoed to customers, and (iii) the team-agreement requirement under Principle VI is satisfied by the user's explicit approval of `backend-spec.md` Track 1 + Track 2 scope and by DECISION 17's precedent (Phase 2A bundling). Phase B' is gated on Phase B endpoints #1 + #2 landing first, so the order discipline is preserved within the single feature. |

No other violations.
