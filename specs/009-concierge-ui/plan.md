# Implementation Plan: Concierge UI

**Branch**: `009-concierge-ui` | **Date**: 2026-05-29 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/009-concierge-ui/spec.md`

## Summary

Ship the complete user-facing surface of Concierge across three roles (visitor, tenant admin, tenant manager) on top of the existing backend (admin auth, widget token exchange, chat, CMS-create, leads, audit logs, usage). Thirteen backend endpoints are confirmed missing — they are now in scope for this feature and land alongside the UI in a dedicated backend-gap-closure phase, so the UI consumes real endpoints end-to-end. Placeholder fallbacks remain as a development-time safety net only.

Approach: build incrementally across seven phases — (A) foundations + auth UX, (2A) backend gap closure (13 endpoints + supporting migrations + integration tests), (3) US1 visitor widget, (4) US2 tenant admin completion, (5) US3 tenant manager completion, (6) US4 widget componentization + bubble launcher + a11y, (7) demo seed + smoke. Phase A lands first as a pure-refactor PR so later phases reuse the same shared helpers. Phase 2A lands before any UI phase that consumes its endpoints. Token-storage discipline (no `localStorage` / cookies / `sessionStorage`) is already enforced by 4 vitest tests and remains a non-negotiable invariant.

## Technical Context

**Language/Version**: Python 3.11 (admin / backend), TypeScript 5 + React 18 (widget), ES2019 (widget loader script)
**Primary Dependencies**: Streamlit (admin UI), Vite (widget build), httpx (admin → API), FastAPI + PyJWT (backend, existing), pytest + Streamlit AppTest (admin tests), vitest + @testing-library/react (widget tests)
**Storage**: PostgreSQL + pgvector (existing); Redis (existing). This plan adds **two migrations**: `0005_admin_invites_revoked_at.py` (column add) and `0006_tenant_settings.py` (new table or columns on `tenants` — see Phase 2A). No new tenant-bearing entities — all additions are tenant-scoped extensions of existing rows. Browser storage: in-memory only — `localStorage` / `sessionStorage` / cookies are forbidden by Constitution Principle IV and enforced by vitest.
**Testing**: pytest (admin AppTest, integration), vitest (widget components + storage discipline), axe-core (widget a11y), Playwright optional for cross-tenant smoke
**Target Platform**: Admin renders on ≥1024 px (laptop / tablet-landscape); widget renders on any modern evergreen browser (desktop ≥640 px and mobile <640 px sheet mode)
**Project Type**: Web — admin (Streamlit single-page dispatcher) + widget (embeddable Vite/React iframe); both consume the existing FastAPI backend
**Performance Goals**: Widget first feedback ≤200 ms after send (SC-001); widget bundle ≤80 KB gzipped, loader ≤5 KB gzipped (SC-007); admin first paint ≤1 s on a local backend (SC-007)
**Constraints**: Tenant isolation (Principle I) — every UI fetch must derive `tenant_id` from a backend-issued token, never UI input. No `tenant_id` field on any form. Every new backend route MUST derive `tenant_id` from the verified JWT (admin or widget) and MUST NOT accept it from a request body. Streamlit ceiling accepted for admin (mobile out of scope; documented in DECISIONS.md).
**Scale/Scope**: ~22 admin page modules (12 existing, ~10 new), ~7 widget components (2 existing, ~6 new + 1 reducer + 1 a11y helper), 13 backend endpoints (with supporting services + repos + 2 migrations), 7 phases across ~11 PRs.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design (see end of file).*

- [x] **Principle I (Tenant Isolation):** every UI fetch derives `tenant_id` from a backend-issued token (admin JWT for admin surfaces; widget JWT for widget). The UI surfaces zero forms accepting `tenant_id`, role, or signing secret (FR-002). Tenant manager cannot reach tenant content endpoints (FR-046, SC-004). Every new backend route added in Phase 2A derives `tenant_id` from the verified JWT, rejects body-supplied `tenant_id` with `extra=forbid`, and is scoped at the repository layer.
- [x] **Principle II (Layered Architecture):** UI calls API only via `admin/_admin_http.py` (admin) and `frontend/widget/src/api.ts` (widget). No SQL anywhere in `admin/` or `frontend/`. Phase 2A keeps the route → service → repository layering for every new endpoint; no SQL in routes; no business logic in repositories.
- [x] **Principle III (Bounded Agent):** no new agent tool; agent loop limits unchanged. Quick-action chips (FR-064) only inject text into the input — they do not create a new tool surface.
- [x] **Principle IV (Defense-in-Depth Auth):** widget token kept in module-scope memory only — enforced by 4 existing vitest tests in [__tests__/api.test.ts](frontend/widget/src/__tests__/api.test.ts) which this plan keeps green. Admin JWT lives only in `st.session_state`. Anti-enumeration error collapse retained on login (FR-010) and widget refusals (Edge Cases). New backend routes added in Phase 2A pull secrets from Vault (via existing `app/services/admin_settings.py`); no `.env` committed.
- [x] **Principle V (Lean Serving & Redaction):** no `torch`/`transformers` added (this plan touches no model code). Widget telemetry (`telemetry.ts`) is a console-only no-op stub that emits zero PII and no token strings. New audit-log emissions in Phase 2A redact metadata (no raw PII / no token strings).
- [x] **Principle VI (Phased Build):** the UI half of this work corresponds to Constitution Phase 7 (Widget) and Phase 8 (Admin UI); the backend gap closure in Phase 2A closes leftover items from Constitution Phases 1, 2, and 5. The phase ordering inside this feature (2A before any consuming UI phase) preserves the dependency discipline the constitution requires.
- [x] **Principle VII (Clean & Simple Code):** every new admin page module is targeted at ~120 LOC (shared `_table.py` / `_kpi.py` / `_status_pill.py` / `_empty.py` carry the boilerplate). Widget reshape **extracts** components from the existing 231-LOC `ChatPane.tsx` — no new abstraction layer. New backend services in Phase 2A follow the existing thin-route-thin-service shape (e.g., `app/services/admin_invite.py` style). Canonical IDs (`tenant_id`, `widget_id`, `session_id`) preserved.

All seven principles pass. No Complexity Tracking entry required.

## Project Structure

### Documentation (this feature)

```text
specs/009-concierge-ui/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output — UI-side entity & state shapes
├── quickstart.md        # Phase 1 output — local-run walkthrough
├── contracts/           # Phase 1 output — endpoint shapes the UI consumes
│   ├── admin-routes.md
│   ├── widget-routes.md
│   └── missing-endpoints.md
├── checklists/
│   └── requirements.md  # Already created by /speckit-specify
├── spec.md              # Already created
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
admin/
├── _admin_http.py            # EXISTS — keep
├── _table.py                 # NEW — shared table renderer (Phase A)
├── _kpi.py                   # NEW — KPI card grid (Phase A)
├── _status_pill.py           # NEW — tenant/lead/ticket/invite pill (Phase A)
├── _empty.py                 # NEW — empty-state card (Phase A)
├── brand.py                  # EXISTS — extend with COLORS/SPACING/RADIUS (Phase A)
├── auth_state.py             # EXISTS — keep
├── streamlit_app.py          # EXISTS — extend dispatcher per phase
├── login_page.py             # EXISTS — refine (Phase B)
├── accept_invite_page.py     # EXISTS — refine (Phase B)
├── access_denied_page.py     # EXISTS — keep
├── platform_dashboard_page.py # EXISTS — extend into full TM dashboard (Phase D)
├── tenant_dashboard.py       # NEW — dispatcher for TA tabs (Phase C PR1)
├── overview_page.py          # NEW — shared TA/TM overview (Phase C PR1 / Phase D)
├── cms_page.py               # EXISTS — refine table (Phase C PR1)
├── agent_settings_page.py    # NEW — Agent + chip list (Phase C PR2)
├── guardrails_page.py        # NEW — read-only platform rails + tenant rules (Phase C PR2)
├── widget_page.py            # EXISTS — refine theme preview (Phase C PR1)
├── leads_page.py             # EXISTS — refine table (Phase C PR1)
├── escalations_page.py       # NEW — status + assignee dropdown (Phase C PR3)
├── usage_page.py             # EXISTS — refine chart (Phase C PR1)
├── audit_page.py             # NEW — TA tenant-scoped + TM platform-scope (Phase C PR3 / Phase D PR2)
├── tenants_page.py           # NEW — TM tenants table (Phase D PR1)
├── invites_page.py           # NEW — TM invites table (Phase D PR2)
└── settings_page.py          # NEW — TM platform settings (Phase D PR2)

frontend/widget/
├── public/
│   └── widget.js             # EXISTS — keep (loader)
└── src/
    ├── main.tsx              # EXISTS — reshape into thin orchestrator (Phase E PR1)
    ├── api.ts                # EXISTS — keep (token store + fetch)
    ├── types.ts              # EXISTS — extend with reducer state types
    ├── styles.css            # EXISTS — split into tokens + per-component (Phase E)
    ├── tokens.css            # NEW — CSS custom properties (Phase A)
    ├── telemetry.ts          # NEW — console-only no-op stub (Phase A)
    ├── state/
    │   └── useChatReducer.ts # NEW — extracted from ChatPane (Phase E PR1)
    ├── components/
    │   ├── Bubble.tsx        # NEW — floating launcher (Phase E PR1)
    │   ├── Panel.tsx         # NEW — dialog shell (Phase E PR1)
    │   ├── Message.tsx       # NEW — bubble + citation chip + ticket pill (Phase E PR1)
    │   ├── QuickActions.tsx  # NEW — chip row (Phase E PR1)
    │   ├── StatusBanner.tsx  # NEW — idle/sending/error/expired/blocked (Phase E PR1)
    │   ├── EmptyState.tsx    # NEW — first-open greeting card (Phase E PR1)
    │   ├── ChatPane.tsx      # EXISTS — slimmed; eventually deleted at end of PR1
    │   └── ChatInput.tsx     # EXISTS — keep, light props change
    └── a11y/
        └── FocusTrap.tsx     # NEW — small audited helper (Phase E PR2)

app/                          # Backend additions (Phase 2A)
├── api/routes/
│   ├── admin_invites.py      # EXISTS — extend with revoke + resend (Phase 2A)
│   ├── tenants.py            # EXISTS — extend with agent-config + admin-users + platform-guardrails + settings + TM tenants/audit reads (Phase 2A)
│   ├── cms.py                # EXISTS — extend with edit + status + delete (Phase 2A)
│   └── escalations.py        # NEW — list + patch routes (Phase 2A)
├── services/
│   ├── admin_invite.py       # EXISTS — extend with revoke + resend (Phase 2A)
│   ├── agent_config.py       # NEW — read + upsert + chip validation (Phase 2A)
│   ├── escalation.py         # NEW — list + patch + assignee tenant-scope check (Phase 2A)
│   ├── tenant_settings.py    # NEW — TM-scope upsert + validation (Phase 2A)
│   └── platform_guardrails.py # NEW — thin snapshot reader (Phase 2A)
├── repositories/
│   ├── admin_invite_repo.py  # EXISTS — extend with mark_revoked + resend (Phase 2A)
│   ├── agent_config_repo.py  # NEW (Phase 2A)
│   ├── escalation_repo.py    # NEW (Phase 2A)
│   ├── admin_user_repo.py    # EXISTS — extend with list_by_tenant (Phase 2A)
│   ├── tenant_settings_repo.py # NEW (Phase 2A)
│   └── cms_repo.py           # EXISTS — extend with update / set_status / delete (Phase 2A)
└── db/migrations/versions/
    ├── 0005_admin_invites_revoked_at.py # NEW (Phase 2A)
    └── 0006_tenant_settings.py          # NEW (Phase 2A)

tests/
├── unit/                     # admin AppTest harnesses for each new page + service-level unit tests
├── integration/              # multi-page admin flows + tenant-isolation negatives + new backend endpoint tests
└── smoke/
    └── test_cross_tenant_e2e.py # EXISTS — extend with widget-UI assertions (Phase 7)

frontend/widget/src/__tests__/
├── api.test.ts               # EXISTS — keep green (storage discipline)
├── chat.test.tsx             # EXISTS — reshape selectors as components extract
├── reducer.test.ts           # NEW — pure-function tests for useChatReducer
├── bubble.test.tsx           # NEW — open/close, focus return
├── panel.test.tsx            # NEW — dialog role, focus trap, ESC
└── responsive.test.tsx       # NEW — mobile sheet mode breakpoint
```

**Structure Decision**: Web — admin (Streamlit modules under `admin/`) + widget (Vite/React under `frontend/widget/`) + the missing backend endpoints under `app/`. The plan does not touch `modelserver/` or `guardrails/` runtime code (Constitution Principle V — lean serving images preserved).

## Phase Outputs

- **Phase 0 — Outline & Research:** [research.md](research.md)
  - 10 research areas (Streamlit a11y ceiling, focus-trap build-vs-buy, Streamlit AppTest placeholder pattern, theme JSON sandbox, mobile sheet implementation, vitest reshape strategy, axe-core wiring, bubble state location, chip storage shape, shared audit page). All `NEEDS CLARIFICATION` entries resolved before exiting Phase 0.

- **Phase 1 — Design & Contracts:** [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)
  - `data-model.md` documents UI-side entity shapes (admin session, widget session, chat message, reducer state) plus the existing DB-side shapes Phase 2A will expose; no new tenant-bearing entities.
  - `contracts/` documents the shape of every backend endpoint the UI consumes (admin-routes.md, widget-routes.md) and the thirteen endpoints Phase 2A will deliver (missing-endpoints.md).
  - `quickstart.md` is a step-by-step "stand up the demo" walkthrough.

- **Phase 2A — Backend gap closure:** lands in tasks.md as a dedicated phase with route + service + repository + migration tasks per endpoint plus integration tests. Sequenced before Phases 3–6 because the UI phases consume the endpoints.

- **Phase 2 (tasks) — generated by `/speckit-tasks`** (not by this command).

## Complexity Tracking

> No principle violations. No entries required.

## Post-Design Constitution Re-Check

*Performed after Phase 1 artifacts are written.* See bottom of [research.md](research.md) and the recap at the end of [data-model.md](data-model.md). Summary:

- [x] Principle I — Tenant isolation unchanged by design artifacts. Contracts confirm every tenant-scoped endpoint (existing + Phase 2A additions) derives `tenant_id` server-side and rejects body-supplied `tenant_id`.
- [x] Principle II — UI layer never reaches past the API boundary; no SQL introduced in `admin/` or `frontend/`. Phase 2A backend additions respect routes → services → repositories.
- [x] Principle III — Agent tool surface unchanged; chip list is presentation data, not a tool.
- [x] Principle IV — Token discipline preserved; vitest harness extended, not relaxed. Phase 2A endpoints all live behind `require_admin_session` or `get_tenant_id_from_widget_token`.
- [x] Principle V — No model code touched; telemetry stub emits no PII; audit-log emissions in Phase 2A redact metadata.
- [x] Principle VI — UI phases sit inside Constitution Phases 7 + 8; Phase 2A closes leftover backend items from Phases 1, 2, and 5 in a controlled, dependency-ordered way.
- [x] Principle VII — Shared helpers reduce LOC across new pages; widget reshape extracts, does not abstract; Phase 2A reuses existing service patterns.

All gates pass after design. Ready for `/speckit-tasks`.
