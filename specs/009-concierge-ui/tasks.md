---
description: "Concierge UI implementation tasks"
---

# Tasks: Concierge UI

**Input**: Design documents from `specs/009-concierge-ui/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included. The spec defines automated checks (vitest storage discipline, AppTest placeholder fallback, axe-core a11y, cross-tenant negatives) as load-bearing for SC-003/SC-004/SC-005/SC-008.

**Organization**: Tasks are grouped by user story. The four stories map to the four user stories in [spec.md](spec.md): US1 Visitor widget (P1), US2 Tenant Admin (P1), US3 Tenant Manager (P2), US4 Bubble launcher + a11y/responsive (P3).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4); omitted for Setup / Foundational / Polish

## Path Conventions

- Web app structure per [plan.md](plan.md) §Project Structure: admin Streamlit modules under `admin/`, widget Vite/React modules under `frontend/widget/src/`, backend untouched under `app/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add dev-deps, scaffold directories, place empty stub files so Phase 2 can land them atomically.

- [X] T001 [P] Add `@axe-core/react` to widget devDependencies in [frontend/widget/package.json](frontend/widget/package.json)
- [X] T002 [P] Create empty directories `frontend/widget/src/state/` and `frontend/widget/src/a11y/` with placeholder `.gitkeep` files
- [X] T003 [P] Create empty stub `admin/_table.py` with module docstring only
- [X] T004 [P] Create empty stub `admin/_kpi.py` with module docstring only
- [X] T005 [P] Create empty stub `admin/_status_pill.py` with module docstring only
- [X] T006 [P] Create empty stub `admin/_empty.py` with module docstring only
- [X] T007 [P] Create empty stub `frontend/widget/src/tokens.css`
- [X] T008 [P] Create empty stub `frontend/widget/src/telemetry.ts` exporting `emit()` no-op

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared helpers, design tokens, widget componentization (extracted but always-open), and auth UX polish. Every user story depends on these landing first.

**⚠️ CRITICAL**: No user story tasks may begin until Phase 2 is complete.

### Admin shared helpers

- [X] T010 Extend [admin/brand.py](admin/brand.py) with `COLORS`, `SPACING`, `RADIUS` constant blocks alongside existing `PRODUCT_NAME` / `PRODUCT_TAGLINE`
- [X] T011 [P] Implement `render_table(rows, columns, *, filters=None, empty_state=None, key=None)` in `admin/_table.py` reusing st.dataframe
- [X] T012 [P] Implement `render_kpi_row(items)` in `admin/_kpi.py` — list of `(label, value, delta?)` tuples; uses st.metric
- [X] T013 [P] Implement `render_status(value, *, kind)` in `admin/_status_pill.py` — kinds: `tenant`, `lead`, `ticket`, `invite`; renders colored badge
- [X] T014 [P] Implement `render_empty_state(title, message, *, primary_cta=None)` in `admin/_empty.py`

### Widget design tokens + telemetry

- [X] T015 [P] Define widget design tokens in `frontend/widget/src/tokens.css` — `--c-bg`, `--c-fg`, `--c-bubble`, `--c-accent`, `--s-1..-4`, `--radius-sm/-md`, `--motion-fast/-slow`
- [X] T016 [P] Import `tokens.css` from `frontend/widget/src/styles.css` (single `@import` at top)
- [X] T017 [P] Implement `emit(name, props={})` console-only telemetry in `frontend/widget/src/telemetry.ts`; redact any field named `token`, `email`, `password`

### Widget componentization (extraction only — UX still always-open)

- [X] T018 Extract `state/useChatReducer.ts` from current ChatPane state machine — exports `initialState`, `reducer(state, action)` as pure functions plus a `useChatReducer()` hook returning `{state, open, close, send, retry, reset}`
- [X] T019 [P] Extract `frontend/widget/src/components/Bubble.tsx` — props `{onClick, label, themeColor}`; pure presentation
- [X] T020 [P] Extract `frontend/widget/src/components/Panel.tsx` — props `{onClose, children, themeColor}`; provides scrollable layout shell; **no** dialog role yet (added in US4)
- [X] T021 [P] Extract `frontend/widget/src/components/Message.tsx` — props `{message: ChatMessage}`; renders user/assistant bubble + citation chips + ticket pill
- [X] T022 [P] Extract `frontend/widget/src/components/QuickActions.tsx` — props `{chips: string[], onPick(text)}`; renders chip row; renders nothing if `chips.length === 0`
- [X] T023 [P] Extract `frontend/widget/src/components/StatusBanner.tsx` — props `{state}`; renders status text per `idle | sending | error | expired`
- [X] T024 [P] Extract `frontend/widget/src/components/EmptyState.tsx` — first-open greeting card
- [X] T025 Reshape `frontend/widget/src/main.tsx` into a thin orchestrator: consumes `useChatReducer`, renders `<Panel><StatusBanner/><MessageList><Message/>...</MessageList><QuickActions/><ChatInput/></Panel>`. **Renders Panel always-open** in this phase (bubble logic comes in US4).
- [X] T026 Delete obsolete code from `frontend/widget/src/components/ChatPane.tsx` (replaced by extracted components); keep `ChatInput.tsx`

### Widget reducer + smoke tests

- [X] T027 [P] Add `frontend/widget/src/__tests__/reducer.test.ts` — pure-function tests for every transition (`OPEN`, `CLOSE`, `SEND_START`, `SEND_OK`, `SEND_ERROR`, `SESSION_EXPIRED`, `RETRY_LAST`, `RESET`)
- [X] T028 Update `frontend/widget/src/__tests__/chat.test.tsx` selectors to query the new component DOM; **all existing assertions MUST still pass** (regression net)
- [X] T029 Verify `frontend/widget/src/__tests__/api.test.ts` still passes unchanged (storage discipline)

### Auth UX polish (Phase B from plan)

- [X] T030 Refine [admin/login_page.py](admin/login_page.py) — loading spinner during submit, generic error collapse text ("Invalid email or password"), "Have an invite?" link, button disable on submit
- [X] T031 Refine [admin/accept_invite_page.py](admin/accept_invite_page.py) — pre-mount preview render, terminal banner for non-pending status (used / expired / revoked / unknown), post-accept auto-login via existing `POST /admin/login` call
- [X] T032 [P] Add `tests/integration/test_admin_login_flow.py` cases for 5 negative login causes — all returning the same canonical 401 body

**Checkpoint**: Phase 2 complete. Widget renders identically to today (always-open) but is internally split. Admin login + invite flows polished. Phase 2A may now begin.

---

## Phase 2A: Backend Gap Closure (Blocking Prerequisites for UI Phases)

**Purpose**: Implement the 13 missing backend endpoints documented in [contracts/missing-endpoints.md](contracts/missing-endpoints.md) so the UI consumes real endpoints instead of placeholder fallbacks. Each endpoint follows the constitution's routes → services → repositories layering.

**⚠️ CRITICAL**: Phase 2A blocks Phases 3–6. Placeholder fallbacks in UI tasks remain as a development safety net but are NOT the target state.

### Migrations (sequential — must merge before downstream services run)

- [X] T033 Add Alembic migration `app/db/migrations/versions/0005_admin_invites_revoked_at.py` — adds `revoked_at TIMESTAMPTZ NULL` column on `admin_invites`; idempotent backfill (no-op for existing rows). Update `AdminInvite` ORM model in [app/db/models.py](app/db/models.py).
- [X] T034 Add Alembic migration `app/db/migrations/versions/0006_tenant_settings.py` — adds `tenant_settings` table with `tenant_id UUID NOT NULL UNIQUE REFERENCES tenants(id) ON DELETE CASCADE`, `default_invite_ttl_seconds INT NOT NULL DEFAULT 604800`, `rate_limit_chat_per_minute INT NOT NULL DEFAULT 30`, `rate_limit_token_per_minute INT NOT NULL DEFAULT 60`, plus RLS policy `tenant_isolation` (same expression as other tenant tables). Add `TenantSettings` ORM model in [app/db/models.py](app/db/models.py).

### Admin invite revoke / resend

- [X] T035 [P] Extend [app/repositories/admin_invite_repo.py](app/repositories/admin_invite_repo.py) with `mark_revoked(token, revoked_at) -> AdminInvite | None` and `resend(token, new_token, new_expires_at) -> AdminInvite | None` (both tenant-aware via repository scoping).
- [X] T036 [P] Extend [app/services/admin_invite.py](app/services/admin_invite.py) with `revoke_invite(token, actor)` and `resend_invite(token, actor)` — enforce: invite belongs to actor's tenant (or actor is tenant_manager), `used_at` is null (409 otherwise), not already revoked (409 otherwise). Emit `admin.invite_revoked` / `admin.invite_resent` audit events.
- [X] T037 [P] Extend [app/api/routes/admin_invites.py](app/api/routes/admin_invites.py) with `POST /admin/invites/{token}/revoke` and `POST /admin/invites/{token}/resend`. Both gated by `require_admin_session`.
- [X] T037t [P] Add `tests/integration/test_admin_invite_revoke_resend.py` — happy path; already-used → 409; already-revoked → 409; cross-tenant attempt → 403 (TA-scope) / 200 (TM-scope).

### Tenant agent-config (get / put)

- [X] T038 [P] Add `app/repositories/agent_config_repo.py` exposing `get_by_tenant(tenant_id)` and `upsert(tenant_id, config_dict)` over the existing `TenantAgentConfig` model in [app/db/models.py](app/db/models.py).
- [X] T039 [P] Add `app/services/agent_config.py` with `AgentConfigService.get_for_tenant(tid)` and `.update_for_tenant(tid, body, actor)` — validate chip-list length 0..6 and chip strings 1..40 chars (422 otherwise). Emit `agent_config_updated` audit event with redacted metadata (no PII).
- [X] T039a [P] Add routes `GET /tenants/{tid}/agent-config` and `PUT /tenants/{tid}/agent-config` to [app/api/routes/tenants.py](app/api/routes/tenants.py). GET accepts either admin JWT (TA self-scope) or widget JWT (own-tenant); PUT requires `require_tenant_admin` and tenant_id MUST match path.
- [X] T039b [P] Add `tests/integration/test_agent_config_endpoint.py` — happy GET/PUT; chip count > 6 → 422; cross-tenant TA → 403; widget JWT can GET own tenant; widget JWT cannot PUT.

### Escalations (list + patch + assignee dropdown)

- [X] T039c [P] Add `app/repositories/escalation_repo.py` with `list_by_tenant(tenant_id)`, `get(ticket_id)`, `update_status_and_assignee(ticket_id, status, assignee_id)` over the existing `EscalationTicket` model.
- [X] T039d [P] Add `app/services/escalation.py` — list scoped to JWT tenant; patch validates assignee belongs to same tenant (422 if foreign or unknown); emit `escalation.status_changed` and `escalation.assignee_changed` audit events.
- [X] T039e [P] Add new `app/api/routes/escalations.py` with `GET /escalations?tenant_id={tid}` and `PATCH /escalations/{id}`. Register router in [app/api/main.py](app/api/main.py).
- [X] T039f [P] Extend [app/repositories/admin_user_repo.py](app/repositories/admin_user_repo.py) with `list_by_tenant(tenant_id) -> list[AdminUser]` (only `active` status, only `tenant_admin` or `tenant_manager` roles).
- [X] T039g [P] Add route `GET /tenants/{tid}/admin-users` to [app/api/routes/tenants.py](app/api/routes/tenants.py) — `require_admin_session`, path tid MUST equal JWT tenant_id (403 otherwise).
- [X] T039h [P] Add `tests/integration/test_escalations_endpoint.py` — list filters by tenant; PATCH status transitions; foreign-tenant assignee → 422; cross-tenant ticket → 403; audit events recorded.

### Platform guardrails read

- [X] T039i [P] Add `app/services/platform_guardrails.py` with `snapshot() -> dict` returning `{ platform_rules: [...], tenant_blocked_topics: [...], tenant_refusal_tone: ... }` — composed from `guardrails/main.py` rule registry (read-only) and the tenant agent-config row.
- [X] T039j [P] Add route `GET /tenants/{tid}/platform-guardrails` to [app/api/routes/tenants.py](app/api/routes/tenants.py) — `require_admin_session`, returns the snapshot scoped to the path tenant.
- [X] T039k [P] Add `tests/integration/test_platform_guardrails_endpoint.py` — read returns platform + tenant sections; cross-tenant path → 403; never mutates state.

### Tenant settings (TM-scope)

- [X] T039l [P] Add `app/repositories/tenant_settings_repo.py` with `get_or_create(tenant_id) -> TenantSettings` (creates defaults on first read) and `update(tenant_id, body)`.
- [X] T039m [P] Add `app/services/tenant_settings.py` — only `tenant_manager` role permitted; validate `default_invite_ttl_seconds` between 3600 and 30·24·3600, rate-limit ints between 1 and 1000; emit `tenant_settings_updated` audit event.
- [X] T039n [P] Add route `PUT /tenants/{tid}/settings` to [app/api/routes/tenants.py](app/api/routes/tenants.py) — `require_admin_session` + role check at service layer.
- [X] T039o [P] Add `tests/integration/test_tenant_settings_endpoint.py` — TM can PUT; TA → 403; out-of-bounds values → 422; audit event present.

### CMS edit / publish / delete

- [X] T039p [P] Extend [app/repositories/cms_repo.py](app/repositories/cms_repo.py) with `update(page_id, tenant_id, body) -> CmsPage | None`, `set_status(page_id, tenant_id, status) -> CmsPage | None`, `soft_delete(page_id, tenant_id) -> bool` (sets `archived` + `deleted_at` timestamp).
- [X] T039q [P] Extend the CMS service layer (or add `app/services/cms_pages.py` if not present) with corresponding `update` / `set_status` / `delete` methods; emit `cms.page_updated` / `cms.page_published` / `cms.page_unpublished` / `cms.page_deleted` audit events.
- [X] T039r [P] Add routes `PUT /cms/pages/{id}`, `PATCH /cms/pages/{id}/status`, `DELETE /cms/pages/{id}` to [app/api/routes/cms.py](app/api/routes/cms.py). All gated by `require_tenant_admin`; tenant_id derived from JWT only; body uses `extra=forbid`.
- [X] T039s [P] After status flips to `published` or back to `draft` / `archived`, re-trigger the RAG ingest pipeline for the affected page (call into the existing ingest service in `app/rag/ingest.py`).
- [X] T039t [P] Add `tests/integration/test_cms_edit_publish_delete.py` — update happy path; cross-tenant page id → 403; tenant_id smuggled in body → 422; delete soft-deletes; status PATCH emits audit event; published status re-indexes.

### TM-scope platform reads (tenants list + audit-logs feed)

- [X] T039u [P] Add admin-JWT-gated `GET /tenants` to [app/api/routes/tenants.py](app/api/routes/tenants.py) — `require_admin_session` with role check `tenant_manager`; returns paginated list using existing `TenantRepository.list_all`. Existing legacy platform-actor-header route untouched.
- [X] T039v [P] Add admin-JWT-gated `GET /audit-logs` to [app/api/routes/tenants.py](app/api/routes/tenants.py) — `require_admin_session` with role check `tenant_manager`; filterable by `actor`, `tenant_id`, `action`, `date_from`, `date_to`. Backed by a new `TenantRepository.list_audit_logs_platform_scope` method.
- [X] T039w [P] Add `tests/integration/test_tm_platform_reads.py` — TM can read both; TA → 403 on both; cross-content denial holds (no CMS body / lead detail returned).

**Checkpoint**: Phase 2A complete. All 13 endpoints live, every endpoint has integration coverage, every audit event fires, RLS holds. UI phases can begin and consume real endpoints.

---

## Phase 3: User Story 1 — Visitor chats with the embedded widget (Priority: P1) 🎯 MVP

**Goal**: A visitor on an allow-listed origin sends FAQ / sales / human-request / unsafe messages and gets the four expected reply categories, with citation chips, ticket pills, chip insertion, and chat history that survives close-and-reopen within the page lifetime.

**Independent Test**: Drop the widget script tag on `host-test.html`, open browser, exchange one message of each canonical type, observe (a) RAG answer with citation chips, (b) lead-capture confirmation + a lead row visible from a tenant admin session, (c) ticket pill + an escalation row visible from a tenant admin session, (d) friendly refusal of cross-tenant probe. Then close the panel, reopen, confirm history is intact; refresh the page, confirm history is gone.

### Tests for User Story 1

- [X] T040 [P] [US1] Add `frontend/widget/src/__tests__/chip_render.test.tsx` — verify quick-action chips render from a mocked agent-config response and clicking inserts text into input
- [X] T041 [P] [US1] Add citation-rendering cases to `chat.test.tsx` — assistant message with `citations:[{title,url}]` renders source chip with clickable link
- [X] T042 [P] [US1] Add ticket-pill rendering case — assistant message with `route:"escalate"` + `ticket_id` renders pill
- [X] T043 [P] [US1] Add char-counter case — input above 2000 chars shows counter and rejects send
- [X] T044 [P] [US1] Add close-and-reopen test — send messages, dispatch `CLOSE`, dispatch `OPEN`, assert message history persists; assert `RESET` clears it
- [X] T045 [P] [US1] Add `tests/integration/test_widget_chat_flow.py` E2E case for the four canonical visitor flows (FAQ, lead, escalate, refusal) using FastAPI TestClient
- [X] T045a [P] [US1] Add `tests/security/test_widget_refusal_symmetry.py` — assert byte-identical `403 {"error":"widget_unavailable"}` body across all refusal causes (origin mismatch, unknown widget_id, suspended tenant, rate-limited) — anti-enumeration regression for SC-008
- [X] T045b [P] [US1] Add `frontend/widget/src/__tests__/latency.test.tsx` — mock `/chat` with a 500 ms delayed response; assert user-bubble + spinner render synchronously (before the response resolves) — SC-001 first-feedback budget

### Implementation for User Story 1

- [X] T046 [P] [US1] Extend [frontend/widget/src/api.ts](frontend/widget/src/api.ts) with `fetchAgentConfig()` calling `GET /tenants/{tid}/agent-config` (delivered by T039a). On 404 (dev-time only, before Phase 2A merges) fall back to hard-coded defaults with a `_placeholder:true` flag; in normal operation the real endpoint MUST respond 200.
- [X] T047 [US1] Wire main.tsx to call `fetchAgentConfig()` on first panel mount and pass `greeting` to EmptyState and `chips` to QuickActions
- [X] T048 [P] [US1] Render citation chips in `frontend/widget/src/components/Message.tsx` for assistant messages with non-empty `citations`; each chip is an `<a target="_blank" rel="noopener noreferrer">`
- [X] T049 [P] [US1] Render ticket pill in `Message.tsx` for assistant messages with `route === "escalate"` and a `ticket_id`
- [X] T050 [P] [US1] Add 2000-char cap + counter to [frontend/widget/src/components/ChatInput.tsx](frontend/widget/src/components/ChatInput.tsx); reject send above the cap
- [X] T051 [US1] Wire `RESET` dispatch in `main.tsx` to the page's `visibilitychange → hidden` + `pagehide` events (FR-070)
- [X] T052 [US1] Render `_placeholder:true` agent-config response with a small "(sample greeting)" footer note inside the panel

**Checkpoint**: US1 functional. Visitor walk passes the Independent Test above using only the existing live backend endpoints plus the placeholder fallback for `/tenants/{tid}/agent-config`.

---

## Phase 4: User Story 2 — Tenant admin configures their own tenant (Priority: P1)

**Goal**: Tenant admin signs in and operates every TA tab (Overview, CMS, Agent Settings, Guardrails, Widget Settings, Origin Allow-list, Leads, Escalations, Usage, Audit) for their own tenant only.

**Independent Test**: Sign in as a seeded tenant admin, change one writable field per tab (add CMS page, edit greeting, add origin, change escalation status), sign out, sign back in, confirm each change persisted. Sign in as a second tenant admin — confirm none of the first tenant's data is visible.

### Tests for User Story 2

- [X] T060 [P] [US2] Add `tests/integration/test_admin_overview_page.py` — KPI cards render real data + placeholder fallback
- [X] T061 [P] [US2] Add `tests/integration/test_admin_cms_create.py` — POST /cms/pages with tenant_id from JWT only (422 if body smuggles tenant_id)
- [X] T062 [P] [US2] Add `tests/integration/test_admin_agent_settings.py` — happy path + chip-list cap (>6 rejected) + placeholder fallback when endpoint absent
- [X] T063 [P] [US2] Add `tests/integration/test_admin_guardrails.py` — read-only platform rules render with "Locked by platform"; tenant section editable
- [X] T064 [P] [US2] Add `tests/integration/test_admin_widget_theme.py` — invalid theme JSON rejected inline; valid one updates live preview; bad contrast triggers fallback
- [X] T065 [P] [US2] Add `tests/integration/test_admin_escalations.py` — status PATCH + assignee dropdown (placeholder until backend live); cross-tenant ticket 403
- [X] T066 [P] [US2] Add `tests/integration/test_admin_audit_tab.py` — TA Audit tab lists own-tenant events; cross-tenant path returns 403
- [X] T067 [P] [US2] Add `tests/integration/test_admin_leads_no_export.py` — no download/export control rendered

### Implementation for User Story 2

- [X] T068 [P] [US2] Create `admin/overview_page.py` — KPI cards for TA: tenant name, widget enabled, leads 30d, escalations open, conversations 30d, tokens, cost; uses `_kpi.render_kpi_row`
- [X] T069 [P] [US2] Create `admin/tenant_dashboard.py` — dispatcher for TA tabs (Overview, CMS, Agent, Guardrails, Widget, Leads, Escalations, Usage, Audit); routes by sidebar selection
- [X] T070 [P] [US2] Refine [admin/cms_page.py](admin/cms_page.py) — use `_table.render_table`, add Create/Edit/Publish/Unpublish/Delete actions wired to `POST /cms/pages` (existing) + `PUT /cms/pages/{id}` (T039r) + `PATCH /cms/pages/{id}/status` (T039r) + `DELETE /cms/pages/{id}` (T039r). Confirmation modal required on Delete.
- [X] T071 [P] [US2] Create `admin/agent_settings_page.py` — form with persona name, greeting, tone dropdown, language dropdown, business rules textarea, **quick-action chip list editor** (one-per-line, max 6). Save → `PUT /tenants/{tid}/agent-config` (T039a). Client-side mirrors the server's 0..6 / 1..40-char validation.
- [X] T072 [P] [US2] Create `admin/guardrails_page.py` — read-only platform rules table with "Locked by platform" badge + tenant rules editor (blocked topics list, refusal tone dropdown). Read via `GET /tenants/{tid}/platform-guardrails` (T039j). Tenant edits persisted through the agent-config PUT (T039a).
- [X] T073 [P] [US2] Refine [admin/widget_page.py](admin/widget_page.py) — add theme JSON sandbox parser per [research.md](research.md) R4 (allow-listed keys, contrast-fallback check); add Copy snippet button generating `<script src=… data-widget-id=… data-backend-url=…>`
- [X] T074 [P] [US2] Refine [admin/leads_page.py](admin/leads_page.py) — use `_table.render_table`; explicitly **omit** export/download controls (FR-024)
- [X] T075 [P] [US2] Create `admin/escalations_page.py` — table of tickets from `GET /escalations` (T039e); status dropdown + assignee dropdown populated from `GET /tenants/{tid}/admin-users` (T039g); save calls `PATCH /escalations/{id}` (T039e). Tenant-foreign assignee selection is impossible by construction (dropdown only lists same-tenant users).
- [X] T076 [P] [US2] Refine [admin/usage_page.py](admin/usage_page.py) — use `_kpi.render_kpi_row` for headline + `_table.render_table` for feature breakdown; existing chart kept
- [X] T077 [P] [US2] Create `admin/audit_page.py` — accepts a `role` parameter; for TA renders `GET /tenants/{tid}/audit-logs` for signed-in tenant only (FR-030); used by both TA + TM (R10)
- [X] T078 [US2] Update [admin/streamlit_app.py](admin/streamlit_app.py) dispatcher to route TA role to `tenant_dashboard.render()` with the new tabs registered

**Checkpoint**: US2 functional. Tenant admin walk passes the Independent Test, including the cross-tenant-isolation negative.

---

## Phase 5: User Story 3 — Tenant manager runs the platform without seeing tenant content (Priority: P2)

**Goal**: Tenant manager signs in, provisions tenants, issues / revokes / resends invites, monitors aggregate usage, reviews platform-wide audit logs, edits non-sensitive settings. Cannot reach any tenant CMS / lead / conversation content.

**Independent Test**: Sign in as tenant manager, create a tenant, issue an invite, watch the invited admin complete the accept flow. Confirm: new tenant visible in Tenants table; manager cannot navigate to any /cms/pages, /leads, /chat-history, or per-tenant CMS body via any UI path; all admin actions appear in the Audit Logs tab.

### Tests for User Story 3

- [X] T080 [P] [US3] Add `tests/integration/test_tm_cannot_read_tenant_content.py` — issue a TM JWT, assert 403 for `/cms/pages`, `/leads`, `/chat-history`, `/tenants/{tid}/escalations`
- [X] T081 [P] [US3] Add `tests/integration/test_tm_tenants_actions.py` — create / suspend / erase with confirmation gating; audit-log entry per action
- [X] T082 [P] [US3] Add `tests/integration/test_tm_invites_revoke_resend.py` — placeholder fallback when endpoints missing; happy path when present
- [X] T083 [P] [US3] Add `tests/integration/test_tm_audit_filter.py` — filter by actor / tenant / action / date returns the right slice

### Implementation for User Story 3

- [X] T084 [P] [US3] Extend [admin/platform_dashboard_page.py](admin/platform_dashboard_page.py) — TM Overview KPIs (total tenants, active, suspended, monthly cost, open audit-flagged actions) using `_kpi.render_kpi_row`
- [X] T085 [P] [US3] Create `admin/tenants_page.py` — sortable table from `GET /tenants` (T039u); Create modal; Suspend with confirmation modal; Trigger erasure with double-confirmation (uses existing erasure endpoint). View metadata modal. Never expose content totals beyond aggregate counts.
- [X] T086 [P] [US3] Create `admin/invites_page.py` — table of all invites across tenants; Invite-new-admin form (move from platform_dashboard); Revoke via `POST /admin/invites/{token}/revoke` (T037); Resend via `POST /admin/invites/{token}/resend` (T037).
- [X] T087 [P] [US3] Extend `admin/audit_page.py` (from T077) with TM render path — backed by `GET /audit-logs` (T039v); filter by actor / tenant / action / date; detail modal pretty-prints JSON metadata.
- [X] T088 [P] [US3] Create `admin/settings_page.py` — form for default invite TTL, rate-limit defaults; Save requires confirmation modal; persists via `PUT /tenants/{tid}/settings` (T039n).
- [X] T089 [P] [US3] Extend [admin/usage_page.py](admin/usage_page.py) with TM aggregate view (per-tenant filter + chart). Same module, role-gated render branch
- [X] T090 [US3] Update [admin/streamlit_app.py](admin/streamlit_app.py) dispatcher to route TM role to a TM-tabs sidebar (Overview, Tenants, Invites, Usage & Cost, Audit Logs, Settings)

**Checkpoint**: US3 functional. Tenant manager Independent Test passes including the cross-content negative.

---

## Phase 6: User Story 4 — Bubble launcher + a11y/responsive (Priority: P3)

**Goal**: Flip the widget from always-open to bubble-launcher with click-to-open; wire dialog role, focus trap, ESC, focus return, mobile sheet, reduced-motion, axe-clean; apply empty-state component to admin tables.

**Independent Test**: Reload `host-test.html` — only bubble visible. Click bubble → panel opens. ESC closes, focus back on bubble. Resize to 360 px → panel becomes full-screen sheet. Enable prefers-reduced-motion → no transitions play. Vitest axe-core scan reports 0 serious/critical violations.

### Tests for User Story 4

- [X] T100 [P] [US4] Add `frontend/widget/src/__tests__/bubble.test.tsx` — initial state shows bubble only; click opens panel; close returns to bubble
- [X] T101 [P] [US4] Add `frontend/widget/src/__tests__/panel.test.tsx` — `role="dialog"` + `aria-modal="true"` present; focus trap wraps both directions; ESC closes and returns focus to bubble
- [X] T102 [P] [US4] Add `frontend/widget/src/__tests__/responsive.test.tsx` — at viewport 360 px wide, panel computed style matches full-viewport mode
- [X] T103 [P] [US4] Add `frontend/widget/src/__tests__/axe.test.tsx` — mount `<App>` open + closed; assert `@axe-core/react` reports zero `serious` + `critical` violations
- [X] T104 [P] [US4] Add `frontend/widget/src/__tests__/reduced_motion.test.tsx` — with `matchMedia('(prefers-reduced-motion: reduce)')` mock returning `matches:true`, assert transition durations are `0ms`

### Implementation for User Story 4

- [X] T105 [US4] Update `frontend/widget/src/main.tsx` orchestrator: render `<Bubble onClick={open}/>` when `state.open === false`; render `<Panel onClose={close}>...</Panel>` when `state.open === true`
- [X] T106 [US4] Wire postMessage iframe-resize handshake in [frontend/widget/public/widget.js](frontend/widget/public/widget.js) ↔ `main.tsx` — collapsed: 80×80 px; open: 380×560 px; mobile (<640): full-viewport
- [X] T107 [P] [US4] Implement `frontend/widget/src/a11y/FocusTrap.tsx` — ~30-line two-element wraparound helper per [research.md](research.md) R2; props `{initialFocusRef?, onEscape}`
- [X] T108 [US4] Wrap `Panel.tsx` children in `<FocusTrap onEscape={onClose}>` and add `role="dialog"` + `aria-modal="true"` + `aria-labelledby` pointing at the header's title element
- [X] T109 [P] [US4] Add `@media (max-width: 639px)` rules in `Panel.tsx`'s scoped styles — `inset: 0`, `padding-top: env(safe-area-inset-top)`, etc.
- [X] T110 [P] [US4] Gate all CSS transitions on `@media (prefers-reduced-motion: no-preference)` in `tokens.css` + per-component styles
- [X] T111 [P] [US4] Implement WCAG contrast-fallback helper in `frontend/widget/src/theme.ts` — compute 4.5:1 ratio against panel background; if tenant `primary_color` fails, fall back to `var(--c-accent)` and emit `telemetry.emit('theme_contrast_fallback')`
- [X] T112 [P] [US4] Add live region (`aria-live="polite"`) to message list in `Panel.tsx` so assistive tech announces new assistant messages without stealing focus
- [X] T113 [P] [US4] Apply `EmptyState.tsx` to chat history first-open in `main.tsx`
- [X] T114 [P] [US4] Apply `admin/_empty.render_empty_state` to every admin table when rows are empty — sweep `cms_page.py`, `leads_page.py`, `escalations_page.py`, `invites_page.py`, `tenants_page.py`, `audit_page.py`
- [X] T115 [P] [US4] Apply `admin/_status_pill.render_status` consistently across `tenants_page.py`, `leads_page.py`, `escalations_page.py`, `invites_page.py`

**Checkpoint**: US4 functional. Bubble UX, a11y, responsive, reduced-motion, axe-clean. Empty states applied across admin.

---

## Phase 7: Polish & Cross-Cutting

**Purpose**: Demo seed, smoke test extensions, documentation, CI budget checks, DECISIONS entries.

- [X] T120 [P] Create `scripts/seed_demo.py` populating 2 tenants × 2 CMS pages × 3 leads × 2 escalations + the widget configs + a first tenant_admin per tenant
- [X] T121 [P] Extend [tests/smoke/test_cross_tenant_e2e.py](tests/smoke/test_cross_tenant_e2e.py) with widget-UI assertions — same-page close/reopen preserves history; refresh resets; cross-tenant probe collapsed to generic refusal
- [X] T122 [P] Update [RUNBOOK.md](RUNBOOK.md) Demo Flow to follow [quickstart.md](quickstart.md) §3 step-by-step
- [X] T123 [P] Add `lighthouse-ci` bundle-size budget check to [.github/workflows/ci.yml](.github/workflows/ci.yml) — widget bundle ≤80 KB gzipped, loader ≤5 KB gzipped (SC-007)
- [X] T123a [P] Add `tests/perf/test_admin_first_paint.py` — Streamlit AppTest harness measures wall-clock time from request to first widget render for Login, TA Overview, and TM Overview; fails if any exceeds 1 second on a local backend (SC-007 admin first-paint budget)
- [X] T123b [P] Add admin overflow check to T128 quickstart validation — open TA dashboard at 1280 × 800 and confirm no horizontal scroll / no clipped KPI cards / no overflowing tables (SC-006 admin viewport)
- [X] T124 [P] Add DECISIONS.md entry — "UI Streamlit ceiling accepted; mobile admin out of scope" (research R1)
- [X] T125 [P] Add DECISIONS.md entry — "Widget state machine extracted to useChatReducer; pure-function reducer for testability" (research R6)
- [X] T126 [P] Add DECISIONS.md entry — "Backend gap closure bundled with UI: the 13 missing endpoints from contracts/missing-endpoints.md ship inside this feature (Phase 2A) rather than being deferred. UI placeholder fallbacks remain only as a development-time safety net."
- [X] T127 [P] Add DECISIONS.md entry — "Widget bubble launcher introduced as new UX state; iframe sized 80×80 collapsed / 380×560 open" (research R8)
- [X] T128 Run [specs/009-concierge-ui/quickstart.md](specs/009-concierge-ui/quickstart.md) end-to-end on a fresh clone; capture any drift between doc and reality; fix doc

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)** — no dependencies; can start immediately.
- **Foundational (Phase 2)** — depends on Setup; BLOCKS all user stories.
- **Backend Gap Closure (Phase 2A)** — depends on Phase 2 in name only; in practice migrations and backend services are file-disjoint from Phase 2 work and may run in parallel with Phase 2. BLOCKS the UI tasks that consume the new endpoints (most of US2 and US3; some of US1).
- **US1 (Phase 3, P1)** — depends on Phase 2; T046 also depends on T039a (agent-config GET).
- **US2 (Phase 4, P1)** — depends on Phase 2 + most of Phase 2A: T070 depends on T039r (CMS edit / status / delete), T071 on T039a, T072 on T039j, T075 on T039e + T039g.
- **US3 (Phase 5, P2)** — depends on Phase 2 + Phase 2A: T085 on T039u, T086 on T037, T087 on T039v, T088 on T039n. The TM Audit Logs view (T087) reuses `audit_page.py` created in US2 (T077); start T087 after T077 lands or stub locally.
- **US4 (Phase 6, P3)** — depends on Phase 2 only (component split). The empty-state sweep (T114) needs the US2 / US3 pages to exist; sequence T114 after Phases 4 + 5.
- **Polish (Phase 7)** — depends on all US complete.

### Within Each User Story

- Tests for the story land first (or alongside) — they ARE the Independent Test bar.
- Inside US2 / US3, page modules are file-disjoint so most `[P]` tasks parallelize.
- Inside US4, components are file-disjoint EXCEPT T105 + T108 both touch the panel surface — sequence them.

### Parallel Opportunities

- Phase 1: T001–T008 all `[P]`.
- Phase 2 admin helpers: T010 sequential (touches existing file); T011–T014 `[P]` after T010 lands the design tokens.
- Phase 2 widget components: T019–T024 all `[P]` (different files); T018 must land first because they consume the reducer; T025 + T026 sequenced last.
- Phase 2A: T033 + T034 sequential (migrations). After migrations land, all service/repo/route groups (T035–T037, T038–T039b, T039c–T039h, T039i–T039k, T039l–T039o, T039p–T039t, T039u–T039w) are file-disjoint and can run `[P]` across groups; within a group, repo → service → route is sequential.
- Phase 3 tests: T040–T045, T045a, T045b all `[P]`.
- Phase 3 implementation: T046–T052 — T047 depends on T046; T051 depends on T025; T048 / T049 / T050 are `[P]` against each other.
- Phase 4 implementation: T068–T077 all `[P]` (different files); T078 must come last (dispatcher wiring).
- Phase 5 implementation: T084–T089 all `[P]`; T090 must come last.
- Phase 6 implementation: T105–T112 a mix per the note above; T114 + T115 `[P]`.
- Phase 7: T120–T127, T123a, T123b all `[P]`; T128 must come last (validates everything).

---

## Parallel Example: User Story 2

```bash
# After T010 lands, launch all admin helpers in parallel:
Task: "Implement render_table() in admin/_table.py"
Task: "Implement render_kpi_row() in admin/_kpi.py"
Task: "Implement render_status() in admin/_status_pill.py"
Task: "Implement render_empty_state() in admin/_empty.py"

# After Phase 2 lands, launch US2 page builds in parallel:
Task: "Create admin/overview_page.py with TA KPI cards"
Task: "Create admin/agent_settings_page.py with chip list editor"
Task: "Create admin/guardrails_page.py with locked-by-platform read-only view"
Task: "Create admin/escalations_page.py with assignee dropdown"
Task: "Create admin/audit_page.py with role-gated render path"
Task: "Refine admin/cms_page.py with shared _table helper"
Task: "Refine admin/widget_page.py with theme JSON sandbox"
Task: "Refine admin/leads_page.py (no export controls)"
Task: "Refine admin/usage_page.py with shared _kpi helper"
```

---

## Implementation Strategy

### MVP First (Phases 1 → 2 → minimum 2A → US1)

1. Phase 1 Setup — 1 day.
2. Phase 2 Foundational — 2–3 days (componentization + auth polish).
3. Phase 2A — minimum needed for US1: T033 + T038 + T039 + T039a + T039b (agent-config GET, ~1 day).
4. Phase 3 US1 — 2 days (chips + citations + persistence).
5. **STOP and VALIDATE**: run the visitor walk from the Independent Test. Demo if green.

That's the MVP demo — visitor sees the polished chat surface with real per-tenant chips. The widget is still always-open (no bubble yet) but otherwise complete.

### Incremental Delivery

1. MVP ships after US1.
2. Add US2 (TA dashboard) — own-tenant configuration ships.
3. Add US3 (TM dashboard) — platform operator ships.
4. Add US4 (bubble + a11y) — production-grade polish ships.
5. Phase 7 — demo seed, smoke extension, RUNBOOK refresh, CI budgets, DECISIONS.md.

### Parallel Strategy

With multiple developers (or sequential effort) after Phase 2 lands:

- Phase 2A backend groups (six file-disjoint groups) can be picked up in parallel.
- US1 / US2 / US3 UI work can start as soon as the specific backend endpoints they depend on land — see the per-task dependency annotations.
- US4 (FocusTrap + reduced-motion + axe + responsive) is largely orthogonal and can spike in parallel with US2 / US3, but the empty-state and status-pill sweeps (T114, T115) need their pages to exist — sequence after Phases 4 + 5.

---

## Notes

- `[P]` = different files, no dependencies on incomplete tasks.
- `[Story]` label maps task to a spec.md user story.
- Tests are included because cross-tenant isolation (SC-003 / SC-004), a11y (SC-005), and storage discipline (Constitution Principle IV) are load-bearing for this feature.
- The 13 missing backend endpoints from [contracts/missing-endpoints.md](contracts/missing-endpoints.md) are implemented in Phase 2A and consumed by the UI for real. Placeholder fallbacks survive only as a development-time safety net — production code paths assume real endpoints.
- Commit after each logical group (typically a single page module or a single component extraction).
- Stop at each Checkpoint to validate the relevant Independent Test before moving on.
