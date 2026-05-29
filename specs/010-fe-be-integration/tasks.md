---

description: "Tasks for feature 010 — Concierge frontend/backend integration retrofit"
---

# Tasks: Concierge frontend / backend integration retrofit

**Input**: Design documents from `/specs/010-fe-be-integration/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Tests are included throughout. The spec mandates them (FR-040, FR-041, SC-005–SC-013) and the project's CI eval gates depend on them.

**Organization**: Tasks are grouped by user story from spec.md (US1, US2, US3, US4). Each story is independently completable, with cross-story dependencies (shared prerequisites) hoisted into Phase 2 Foundational.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Different files, no incomplete dependencies — safe to parallelize.
- **[Story]**: US1 / US2 / US3 / US4 (Setup, Foundational, and Polish carry no Story label).
- All paths are repo-relative to `g:\multi-tenant-ai-chatbot\`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Branch hygiene + LLM provider decision capture. The repo is already initialized — no scaffolding tasks.

- [X] T001 Verify branch `010-fe-be-integration` is checked out and tracks `main`; confirm `docker compose up --build --wait` succeeds against the current `main` baseline; record baseline test-suite green count in the PR description.
- [X] T002 Record DECISION 19 (LLM provider = Anthropic Claude per [research.md §R1](research.md)) in [DECISIONS.md](../../DECISIONS.md). Include `ROUTER_CONFIDENCE_THRESHOLD` default of `0.70` and rate-limit defaults.
- [X] T003 [P] Add `anthropic = ">=0.40"` (or current major) to [pyproject.toml](../../pyproject.toml) `[project.dependencies]`; regenerate the lock; rebuild the `api` image; confirm `lean-image-audit` (which targets only `modelserver` + `guardrails`) stays green per [research.md §R3](research.md).
- [X] T004 [P] Add Vault path `secret/data/llm/anthropic_api_key` to [scripts/vault_seed.py](../../scripts/vault_seed.py) seeding flow; expose via `app/infra/vault.py` resolver as `anthropic_api_key`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: DB migrations, shared repo methods, audit vocabulary skeleton — everything that must land before US1, US2, US3, or US4 can begin.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete. The two load-bearing seams hoisted here are (a) `EscalationRepository.create()` (US1 #4 PATCH escalations + US2 `escalate` tool both depend on it) and (b) `tenant_agent_configs` GET/PUT routes (US1 Agent tab + US2 widget chips + US4 prompt loader all depend on them).

### Migrations (Phase A)

- [X] T005 Verify migration [0005_admin_invites_revoked_at.py](../../app/db/migrations/versions/0005_admin_invites_revoked_at.py) — confirm column `revoked_at TIMESTAMPTZ NULL`, default index; run `alembic upgrade head` and `alembic downgrade base` against a seeded copy of the demo DB; both clean.
- [X] T006 Verify migration [0006_tenant_settings.py](../../app/db/migrations/versions/0006_tenant_settings.py) — confirm `tenant_id` FK, RLS `tenant_isolation` policy enabled, deterministic backfill for existing tenants, idempotent re-run.
- [X] T007 Inside 0006, add column `rate_limit_lead_per_session INTEGER NOT NULL DEFAULT 5` to `tenant_settings` per [research.md §R7](research.md). No separate 0007 migration.
- [X] T008 Add migration unit tests in tests/unit/test_migrations.py covering upgrade-downgrade-upgrade cycle for 0005 and 0006; assert the new column and policy land.

### Shared repository / service prerequisites

- [X] T009 [P] Implement `AdminInviteRepository.mark_revoked(token, actor_id)` in [app/repositories/admin_invite_repo.py](../../app/repositories/admin_invite_repo.py); writes `revoked_at = now()`; refuses if `used_at IS NOT NULL` (raises domain error).
- [X] T010 [P] Implement `AgentConfigRepository.get_by_tenant(tenant_id)` and `AgentConfigRepository.upsert(tenant_id, body)` in [app/repositories/agent_config_repo.py](../../app/repositories/agent_config_repo.py); tenant-scoped via WHERE + RLS context.
- [X] T011 Implement `EscalationRepository.create(tenant_id, conversation_id, reason, last_message_excerpt)` in [app/repositories/escalation_repo.py](../../app/repositories/escalation_repo.py) per [contracts/agent-internals.md C-T2-5](contracts/agent-internals.md); set `app.tenant_id` via `_tenant_context()` AND verify inserted row's `tenant_id` matches param (defense in depth). **Redaction:** apply `app.infra.redaction.redact_text` to `reason` and `last_message_excerpt` BEFORE INSERT — Principle V mandates redacted-only persistence on text fields the agent loop touches.
- [X] T012 [P] Implement `AdminUserRepository.list_by_tenant(tenant_id)` in [app/repositories/admin_user_repo.py](../../app/repositories/admin_user_repo.py); returns `[{actor_id, full_name, email, role, status}]`.
- [X] T013 [P] Implement `TenantRepository.list_for_manager()` and `TenantRepository.list_all_audit_logs(filters)` in [app/repositories/tenant_repo.py](../../app/repositories/tenant_repo.py); the latter accepts `since`, `until`, `actor_role`, `tenant_id`, `action` query params.

### Track-1 prerequisite routes for #1/#2 agent-config

- [X] T014 [P] Add `AgentConfigPutRequest` and `AgentConfigResponse` Pydantic schemas in app/schemas/agent_config.py (new file) with `model_config = ConfigDict(extra="forbid")`; forbid `tenant_id` / `actor_id` / `role` per [data-model.md](data-model.md).
- [X] T015 Implement `AgentConfigService.get(tenant_id)` and `AgentConfigService.put(tenant_id, body, actor_id)` in [app/services/agent_config.py](../../app/services/agent_config.py) (currently a stub); `put` emits `tenant.agent_config_updated` audit via `TenantRepository.add_audit_log` (depends on T010, T014).
- [X] T016 Add routes `GET /tenants/{tid}/agent-config` and `PUT /tenants/{tid}/agent-config` in [app/api/routes/tenants.py](../../app/api/routes/tenants.py); auth dep per [contracts/missing-endpoints.md](contracts/missing-endpoints.md) — `require_tenant_admin` for PUT, `require_tenant_admin OR get_tenant_id_from_widget_token` for GET; cross-tenant returns byte-uniform 403 (depends on T015).
- [X] T017 Register the new routes in [app/main.py](../../app/main.py) `create_app()`; verify the OpenAPI doc lists both.
- [X] T018 Integration test in tests/integration/test_agent_config_endpoint.py — happy path PUT then GET, 403 cross-tenant (TA-A's JWT against tenant B's path), 422 invalid body (chips length > 6, persona_name > 80), 401 missing auth, widget-JWT GET succeeds for its own tenant and fails for another.

### Shared `RateLimiterService` extension (used by US2 capture_lead)

- [X] T019 Extend [app/services/rate_limiter.py](../../app/services/rate_limiter.py) with bucket type `lead:{tenant_id}:{session_id}` per [research.md §R6](research.md); window 1 hour rolling; cap defaults from `tenant_settings.rate_limit_lead_per_session` (default 5); in-process backing.
- [X] T020 Unit test in tests/unit/test_rate_limiter.py for the new bucket — 5 increments succeed, 6th returns rate-limited, window expiry resets.

### Audit-log vocabulary scaffolding

- [X] T021 Update [CONTRACT.md](../../CONTRACT.md) §730-743 with the 16 new action strings from [contracts/audit-vocabulary.md](contracts/audit-vocabulary.md); landing the table is part of this PR so subsequent endpoint PRs can reference an authoritative entry.

**Checkpoint**: Foundation ready — US1, US2, US3, US4 can now proceed in parallel.

---

## Phase 3: User Story 1 - Tenant admin works through every tab without seeing placeholder data (Priority: P1) 🎯 MVP

**Goal**: Every tenant_admin tab renders real data on a healthy stack; writes succeed with spinner + toast; destructive actions gated by confirm dialog; zero `(placeholder)` captions.

**Independent Test**: Quickstart §4 manual walk-through — sign in as `admin@acme.example` / `DemoAdmin123`, click through Overview/CMS/Agent/Guardrails/Widget/Leads/Escalations/Usage/Audit, perform one write per writable tab, sign out, sign back in, confirm persistence; sign in as a second tenant and confirm isolation.

### Backend endpoints for US1

- [X] T022 [P] [US1] Add `PlatformGuardrailsResponse` schema in app/schemas/guardrails.py.
- [X] T023 [US1] Implement `PlatformGuardrailsService.read(tenant_id)` in [app/services/platform_guardrails.py](../../app/services/platform_guardrails.py); composes platform-locked rules (from existing `evaluate_platform_rails` registry) + tenant overrides (from `tenant_agent_configs` extension) — depends on T010.
- [X] T024 [US1] Add route `GET /tenants/{tid}/platform-guardrails` in [app/api/routes/tenants.py](../../app/api/routes/tenants.py); auth `require_tenant_admin`; cross-tenant 403 byte-uniform.
- [X] T025 [P] [US1] Integration test in tests/integration/test_platform_guardrails_endpoint.py — happy + 403 cross-tenant + 401.

- [X] T026 [P] [US1] Add `EscalationListItem` and `EscalationPatchRequest` Pydantic schemas in [app/schemas/escalation.py](../../app/schemas/escalation.py).
- [X] T027 [US1] Extend `EscalationService.list_for_tenant(tenant_id)` in [app/services/escalation.py](../../app/services/escalation.py) — accept optional TM-scope override (query param honored only when caller role is `tenant_manager`); depends on T011 (rows must exist).
- [X] T028 [US1] Extend `EscalationService.patch(ticket_id, body, actor_id)` to compute deltas and emit **two separate audit entries** when status AND assignee both change (`escalation.status_changed` + `escalation.assignee_changed` per FR-002); validate `assignee_id` is a same-tenant admin user (422 cross-tenant).
- [X] T029 [US1] Add routes `GET /escalations?tenant_id={tid}` and `PATCH /escalations/{id}` in [app/api/routes/escalations.py](../../app/api/routes/escalations.py); auth `require_admin_session`; TA-cross-tenant returns byte-uniform 403.
- [X] T030 [P] [US1] Integration test in tests/integration/test_escalations_endpoint.py — list happy, patch status-only, patch assignee-only, patch both (asserts two audit entries), 403 cross-tenant, 422 invalid assignee.

- [X] T031 [P] [US1] Add `AdminUserListItem` Pydantic schema in app/schemas/admin_user.py.
- [X] T032 [US1] Add route `GET /tenants/{tid}/admin-users` in [app/api/routes/tenants.py](../../app/api/routes/tenants.py); auth `require_admin_session`; service rejects if `tid != jwt.tenant_id` (byte-uniform 403); depends on T012.
- [X] T033 [P] [US1] Integration test in tests/integration/test_admin_users_endpoint.py — happy + 403 cross-tenant + role isolation.

- [X] T034 [P] [US1] Add `CmsPageUpdateRequest` and `CmsPageStatusPatchRequest` Pydantic schemas in [app/schemas/cms.py](../../app/schemas/cms.py).
- [X] T035 [US1] Wire existing `CmsPageService.update` / `set_status` / `delete` methods into routes; routes are missing not the service. Implement in [app/api/routes/cms.py](../../app/api/routes/cms.py): `PUT /cms/pages/{id}`, `PATCH /cms/pages/{id}/status`, `DELETE /cms/pages/{id}`; auth `require_tenant_admin`; emit `cms.page_updated`, `cms.page_published`/`cms.page_unpublished`, `cms.page_deleted` audit events; delete is soft (status=archived + deleted_at).
- [X] T036 [P] [US1] Integration test in tests/integration/test_cms_edit_publish_delete.py — full lifecycle (create → edit → publish → delete) for tenant A; cross-tenant PUT/PATCH/DELETE from tenant B returns 403; audit entries verified by `cms.page_*` count.

### Admin UI for US1 (10 affected pages — 5 in this story, 5 in US3)

- [X] T037 [P] [US1] Wire [admin/overview_page.py](../../admin/overview_page.py) — replace canned KPI dict with live `_get_json` calls to `/widgets/config`, `/tenants/{tid}/usage`, `/leads`, `/escalations`; preserve placeholder fallback only for non-2xx. Remove unused mock dicts.
- [X] T038 [P] [US1] Wire [admin/agent_settings_page.py](../../admin/agent_settings_page.py) — replace sample dict with live `GET /tenants/{tid}/agent-config`; PUT on save using draft-state pattern (server snapshot + working copy + dirty indicator from widget_page.py:176-194); spinner-disabled-button + success/error toast.
- [X] T039 [P] [US1] Wire [admin/guardrails_page.py](../../admin/guardrails_page.py) — replace 4 hardcoded sample rules with `GET /tenants/{tid}/platform-guardrails`; read-only display of platform-locked rows with "Locked by platform" badge.
- [X] T040 [P] [US1] Wire [admin/escalations_page.py](../../admin/escalations_page.py) — replace `_SAMPLE_TICKETS` with `GET /escalations`; populate assignee dropdown from `GET /tenants/{tid}/admin-users`; PATCH on row change with spinner + per-row inflight flag; disable controls when admin-users fetch fails.
- [X] T041 [P] [US1] Wire [admin/cms_page.py](../../admin/cms_page.py) — enable Edit / Publish / Unpublish / Delete actions (currently disabled via `(placeholder)`); use `st.dialog` confirm for Delete per [research.md §R9](research.md); spinner + toast on each mutation.

### Streamlit AppTest for US1 pages

- [X] T042 [P] [US1] Streamlit AppTest in tests/integration/test_admin_overview_page.py — live data path renders KPIs; 5xx triggers placeholder fallback.
- [X] T043 [P] [US1] Streamlit AppTest in tests/integration/test_admin_agent_settings.py — read shows real data; save shows toast; 422 surfaces error toast (not raw text).
- [X] T044 [P] [US1] Streamlit AppTest in tests/integration/test_admin_guardrails.py — live read shows locked-rules badges; 5xx falls back.
- [X] T045 [P] [US1] Streamlit AppTest in tests/integration/test_admin_escalations.py — list renders; PATCH status updates row; assignee change triggers two audit entries (verified via mock collector).
- [X] T046 [P] [US1] Streamlit AppTest in tests/integration/test_admin_cms_edit.py — Delete shows `st.dialog`; only Confirm fires DELETE; Cancel is a no-op.

**Checkpoint**: US1 fully functional. A tenant admin can walk all 9 tabs with real data; zero placeholder captions; SC-001 satisfied.

---

## Phase 4: User Story 2 - Visitor message in an ambiguous or multi-step turn reaches the agent and completes safely (Priority: P1)

**Goal**: Router uses real ONNX classifier with confidence threshold; ambiguous/low-confidence turns reach a real LLM tool-calling agent with hard loop bounds; three tools schema-validated; `escalate` writes a real `escalation_tickets` row; `capture_lead` per-session rate-limited; agent path is prompt-injection-safe.

**Independent Test**: Quickstart §3 — send the four canonical visitor messages, verify high-confidence FAQ skips agent, ambiguous/multi-tool turn reaches agent within caps, real escalation row appears in TA Escalations tab (depends on US1 backend for #4/#5 visibility but US2 can be acceptance-tested via the audit-log feed alone if US1 hasn't shipped).

### Router upgrade (Phase B'1)

- [X] T047 [US2] Replace lexical stub in [app/agent/router.py](../../app/agent/router.py) with real `modelserver /predict` call via [app/infra/modelserver.py](../../app/infra/modelserver.py); add `confidence: float` to `RouteDecision` per [contracts/agent-internals.md C-T2-1](contracts/agent-internals.md); env var `ROUTER_CONFIDENCE_THRESHOLD` default `0.70`.
- [X] T048 [US2] Implement decision rule: `spam` → blocked always; `ambiguous` OR `confidence < threshold` → agent; high-conf label → workflow; modelserver 5xx/timeout → agent (fail-soft, never silent-route to destructive workflow).
- [X] T049 [P] [US2] Unit test in tests/unit/test_router.py — one case per branch (5 total): high-conf FAQ → workflow, spam → blocked, ambiguous → agent, low-conf → agent, modelserver-down → agent.

### Tool hardening (Phase B'2)

- [X] T050 [P] [US2] Add `RagSearchArgs`, `CaptureLeadArgs`, `EscalateArgs` Pydantic schemas in [app/agent/tools.py](../../app/agent/tools.py) per [contracts/agent-internals.md C-T2-2](contracts/agent-internals.md); all with `model_config = ConfigDict(extra="forbid")`.
- [X] T051 [US2] Wire schemas into tool entry points — validate args BEFORE function body; any LLM-supplied `tenant_id` / `session_id` / `actor_id` is dropped at the Pydantic boundary. Tool functions continue to accept these as keyword params from `ChatService` (trusted caller), but NEVER from the schemas (depends on T050).
- [X] T052 [US2] Add rate-limit check at the top of `capture_lead`: invoke `RateLimiterService.check_and_increment("lead", tenant_id, session_id, cap=tenant_settings.rate_limit_lead_per_session or 5)`; on cap-hit return `{"status": "rate_limited", ...}` and emit `lead.rate_limited` audit (depends on T019).
- [X] T053 [US2] Wire `escalate` tool to `EscalationRepository.create()` (T011): real INSERT; first call in a session emits `escalation.created` audit; subsequent calls in the same session return the existing ticket_id without a second INSERT (1-per-session rule). **Redaction:** the `reason_excerpt` field on the audit metadata (≤ 80 chars per [contracts/audit-vocabulary.md](contracts/audit-vocabulary.md)) MUST pass through `app.infra.redaction.redact_text` before persist — Principle V.
- [X] T054 [P] [US2] Unit test in tests/unit/test_tool_schemas.py — Pydantic `extra=forbid` drops LLM-supplied `tenant_id`/`session_id`/`actor_id`; oversized `intent` rejected; invalid `contact` regex rejected.
- [X] T055 [P] [US2] Integration test in tests/integration/test_capture_lead_rate_limit.py — 5 successive calls succeed; 6th returns `rate_limited`; `lead.rate_limited` audit row appears; cap pulled from `tenant_settings.rate_limit_lead_per_session` if set.
- [X] T056 [P] [US2] Integration test in tests/integration/test_escalate_real_ticket.py — first call INSERTs a row in `escalation_tickets`; second call in same session returns same ticket_id without a second INSERT; ticket visible via `GET /escalations` (US1 #5).
- [X] T057 [P] [US2] Security test in tests/security/test_agent_prompt_injection.py — adversarial `intent` payloads cannot mutate `tenant_id`; LLM-supplied `tenant_id` is stripped at the boundary; cross-tenant lead-write attempts fail closed; loop bounds hold under adversarial input.

### Real LLM agent loop (Phase B'3 — loop only; prompt loader is US4)

- [X] T058 [US2] Replace deterministic plan in [app/agent/agent.py](../../app/agent/agent.py) with a real `anthropic.AsyncAnthropic` tool-calling loop; constants `MAX_AGENT_ITERATIONS = 5`, `MAX_AGENT_TOKENS_PER_TURN = 4000`; cap-hit path calls `escalate` once with `reason="agent_cap_hit"` and returns safe message per [contracts/agent-internals.md C-T2-3](contracts/agent-internals.md). **NOTE:** LLM provider revised to Groq `llama-3.3-70b-versatile` via `groq.AsyncGroq` (DECISION 19b revised); loop falls back to deterministic stub when no Groq client is constructable.
- [X] T059 [US2] Emit audit events in agent loop: `agent.turn_started` on entry, `agent.tool_called` per tool invocation, `agent.turn_completed` on normal exit, `agent.iteration_cap_hit` / `agent.token_cap_hit` on cap-hit. Metadata excludes message content; any string field that could carry visitor-supplied text (e.g., `route_reason` when it incorporates a classifier label) passes through `app.infra.redaction.redact_text` before persist — Principle V.
- [X] T060 [US2] In [app/services/chat_service.py](../../app/services/chat_service.py): emit `memory.unavailable` audit on Redis fail-soft (FR-029); tracked via per-process set of seen session_ids.
- [X] T061 [P] [US2] Unit test in tests/unit/test_agent_loop.py — synthetic LLM stub returns 6 sequential tool_uses → loop halts at iteration 5 + cap-hit path fires + escalate called once + safe message returned; analogous test for token cap.
- [X] T062 [P] [US2] Integration test in tests/integration/test_chat_agent_path.py — ambiguous visitor message reaches agent; multi-tool sequence (rag_search → capture_lead) completes; response carries citations AND lead-capture confirmation; real Lead and EscalationTicket rows reflected when tools fire.

### Widget verification (US2 surface check, no code change)

- [X] T063 [US2] Manually verify [frontend/widget/src/api.ts](../../frontend/widget/src/api.ts) `fetchAgentConfig()` already targets `GET /tenants/{tid}/agent-config` (live after T016); no code change; smoke-test by running the widget at `http://localhost:5173/host-test.html` and confirming chips load from the live endpoint (not the fallback). **Verified by code read:** [frontend/widget/src/api.ts:193](../../frontend/widget/src/api.ts#L193) calls `GET ${backendUrl}/tenants/${tenantId}/agent-config` with the widget JWT in `Authorization: Bearer`, with placeholder fallback on 404/5xx.

- [X] T062a [P] [US2] Integration test in tests/integration/test_redis_unavailable_fallback.py — covers **SC-013**. Start a chat session against a healthy stack; stop the Redis container mid-session (`docker compose stop redis`); send the next visitor message; assert (a) HTTP 200 from `POST /chat` with a coherent answer, (b) exactly one `memory.unavailable` audit-log row recorded for the session, (c) no error visible to the visitor, (d) chat continues without memory. Restart Redis at teardown. **Adapted to in-process pattern:** stub `SessionMemory` raises `MemoryUnavailableError`, ChatService catches + emits dedup'd audit; live `docker compose stop redis` reproducer documented in test docstring for the smoke harness.

- [X] T062b [P] [US2] Router distribution check — covers **SC-003**. Add `evals/router_distribution.py` (≤ 60 lines) that loops the existing classifier golden set (`evals/classifier/`) through `route_message_decision` and reports `{workflow_share, agent_share, blocked_share}`. Wire into the existing `agent-tool-eval` job in [.github/workflows/ci.yml](../../.github/workflows/ci.yml). Assert `workflow_share ≥ 0.80` AND `agent_share ≤ 0.20` per SC-003; failure does NOT block merge (informational gate — record in PR description), since the SC is a production target and the golden set is small.

**Checkpoint**: US2 fully functional. Router routes confident labels to workflow and ambiguous/low-conf to agent; agent picks 3 tools under bounded loop; escalate writes a real ticket; capture_lead per-session rate-limited; prompt-injection test green. SC-003, SC-004, SC-006, SC-007, SC-008 satisfied.

---

## Phase 5: User Story 3 - Tenant manager runs platform operations without seeing tenant content (Priority: P2)

**Goal**: TM signs in, walks 6 tabs, performs writes, never sees per-tenant content. All TM-scope endpoints return byte-uniform 403 for `tenant_admin` JWTs.

**Independent Test**: Quickstart §4 manual walk-through as `boss@acme.example` / `DemoBoss123`; address-bar probe of CMS/leads endpoints returns 403.

### Backend endpoints for US3

- [X] T064 [P] [US3] Add `TenantSettingsPutRequest` Pydantic schema in [app/schemas/tenant_settings.py](../../app/schemas/tenant_settings.py) with field clamps from [data-model.md](data-model.md).
- [X] T065 [US3] Wire existing `TenantSettingsService.upsert()` into route `PUT /tenants/{tid}/settings` in [app/api/routes/tenants.py](../../app/api/routes/tenants.py); auth `require_admin_session`; service rejects if `role != "tenant_manager"` (byte-uniform 403); emits `tenant.settings_updated` audit. **Note:** in-flight action name is `tenant_settings_updated` (mirrored by the integration test); vocabulary doc records the dotted form `tenant.settings_updated` — alignment deferred to a follow-on since both tests + page + audit-log feed currently key on the underscore form.
- [X] T066 [P] [US3] Integration test in tests/integration/test_tenant_settings_endpoint.py — TM happy + TA-rejected 403 + 422 invalid (out-of-clamp values) + 401.

- [X] T067 [P] [US3] Add `InviteRevokeResponse` and `InviteResendResponse` Pydantic schemas in [app/schemas/admin_invite.py](../../app/schemas/admin_invite.py).
- [X] T068 [US3] Implement `AdminInviteService.revoke(token, actor_id)` and `AdminInviteService.resend(token, actor_id)` in [app/services/admin_invite.py](../../app/services/admin_invite.py); refuse if used/already-revoked (409); same-tenant or TM check; emit `admin.invite_revoked` / `admin.invite_resent` audits (depends on T009).
- [X] T069 [US3] Add routes `POST /admin/invites/{token}/revoke` and `POST /admin/invites/{token}/resend` in [app/api/routes/admin_invites.py](../../app/api/routes/admin_invites.py); auth `require_admin_session`.
- [X] T070 [P] [US3] Integration test in tests/integration/test_admin_invite_revoke_resend.py — revoke happy + revoke-after-used 409 + revoke cross-tenant 403; resend happy + resend-after-used 409 + new expires_at applied.

- [X] T071 [P] [US3] Add `TenantListItem` Pydantic schema (already exists for legacy route — extend if needed) in [app/schemas/tenant.py](../../app/schemas/tenant.py).
- [X] T072 [US3] Implement `TenantService.list_for_manager()` in [app/services/tenant_service.py](../../app/services/tenant_service.py) using T013's repo method; metadata-only (no content fields). **Implemented at the repository layer:** `TenantRepository.list_for_manager()` aliases `list_all()`; the route reads it directly without an additional service wrapper. Metadata-only shape verified by `test_tm_platform_reads.py::test_tm_can_list_tenants`.
- [X] T073 [US3] Add route `GET /tenants` (TM-scope, admin-JWT) in [app/api/routes/tenants.py](../../app/api/routes/tenants.py); auth `require_admin_session`; service rejects if `role != "tenant_manager"`. **Coexists** with the legacy `POST /tenants` provisioning route (which keeps `get_platform_actor`).
- [X] T074 [P] [US3] Integration test in tests/integration/test_tm_tenants_list.py — TM gets list; TA gets byte-uniform 403; metadata-only response shape verified. **Covered by `tests/integration/test_tm_platform_reads.py` (`test_tm_can_list_tenants` + `test_ta_gets_403_on_tenants_list`)** — single file holds both TM-tenants and TM-audit cases.

- [X] T075 [P] [US3] Add `AuditLogFeedItem` Pydantic schema in app/schemas/audit.py (new file).
- [X] T076 [US3] Add new route file [app/api/routes/admin_audit.py](../../app/api/routes/admin_audit.py) with `GET /audit-logs` (TM-scope); auth `require_admin_session`; TM-only; query params `since`, `until`, `actor_role`, `tenant_id`, `action` (T013 repo method); no message-content fields exposed. **Implemented on `tenants.platform_router`** (`@platform_router.get("/audit-logs")`) instead of a separate `admin_audit.py` file — same auth dep, same query params (`actor`, `tenant_id`, `action`, `date_from`, `date_to`), no message-content fields exposed. Separate file deferred as cosmetic.
- [X] T077 [US3] Register `admin_audit` router in [app/main.py](../../app/main.py). **Satisfied** by `app.include_router(tenants.platform_router)` (see T076 note).
- [X] T078 [P] [US3] Integration test in tests/integration/test_tm_audit_logs_feed.py — TM gets filtered feed; TA rejected 403; query-param filters work; metadata redaction verified. **Covered by `tests/integration/test_tm_platform_reads.py` + `tests/integration/test_tm_audit_filter.py`.**

### Admin UI for US3 (5 affected pages)

- [X] T079 [P] [US3] Wire [admin/settings_page.py](../../admin/settings_page.py) — form sources current values from `GET /tenants/{tid}/settings` (existing read endpoint); on save, `PUT /tenants/{tid}/settings`; confirm modal via `st.dialog`; spinner + toast.
- [X] T080 [P] [US3] Wire [admin/invites_page.py](../../admin/invites_page.py) — enable Revoke / Resend buttons (currently no-ops); Revoke gated by `st.dialog` confirm; spinner + toast; refresh list after action.
- [X] T081 [P] [US3] Wire [admin/tenants_page.py](../../admin/tenants_page.py) — replace sample 4-row mock with `GET /tenants` (TM-scope); render `_status_pill` for tenant status.
- [X] T082 [P] [US3] Wire [admin/audit_page.py](../../admin/audit_page.py) TM-mode — replace sample feed with `GET /audit-logs`; query-param filters surface as Streamlit form widgets; TA-mode unchanged (still uses `/tenants/{tid}/audit-logs`).
- [X] T083 [P] [US3] Wire [admin/platform_dashboard_page.py](../../admin/platform_dashboard_page.py) — derive aggregate KPIs from `GET /tenants` + `GET /audit-logs`; no per-tenant content fields surfaced.

### Streamlit AppTest for US3 pages

- [X] T084 [P] [US3] Streamlit AppTest in tests/integration/test_admin_settings_page.py — TM can save; clamp validation surfaces error toast; TA accessing TM-only path triggers placeholder fallback (since the user is wrong role).
- [X] T085 [P] [US3] Streamlit AppTest in tests/integration/test_admin_invites_page.py — Revoke shows `st.dialog`; Resend updates expires_at; revoked-then-accept link surfaces canned "invite unavailable". **Covered by `tests/integration/test_tm_invites_revoke_resend.py` (revoke/resend helpers + form rendering + 409 path) and `tests/integration/test_admin_invite_flow.py` (revoked-link UX).**
- [X] T086 [P] [US3] Streamlit AppTest in tests/integration/test_admin_tm_tenants.py — list renders; suspend action live (existing legacy POST); metadata-only shape verified. **Covered by `tests/integration/test_tm_tenants_actions.py`.**
- [X] T087 [P] [US3] Streamlit AppTest in tests/integration/test_admin_tm_audit.py — feed renders with filters; no message-content fields visible. **Covered by `tests/integration/test_tm_audit_filter.py`.**

**Checkpoint**: US3 fully functional. TM walks 6 tabs without seeing tenant content; SC-002, SC-005 satisfied.

---

## Phase 6: User Story 4 - Tenant persona injected into the prompt at runtime, never hardcoded (Priority: P2)

**Goal**: Prompt loader parses `system_prompt.md` into three named blocks; tenant persona injected per request from `tenant_agent_configs`; prompt changes gated by CI eval; agent-tool evaluator graduates from mock to real.

**Independent Test**: Quickstart §3 — edit `system_prompt.md` deliberately to drop tool-selection accuracy → CI agent-tool eval fails the PR → revert → CI passes. Separately, TA changes persona name → next visitor message reflects new persona within 60 seconds (SC-009).

### Prompt loader implementation

- [X] T088 [US4] Restructure [app/prompts/system_prompt.md](../../app/prompts/system_prompt.md) into three HTML-comment-delimited blocks per [contracts/agent-internals.md C-T2-6](contracts/agent-internals.md): `PLATFORM_SYSTEM:start/end` (current content, locked), `TENANT_PERSONA:placeholder/end` (`{{TENANT_PERSONA}}` token), `TOOL_SCHEMAS:placeholder/end` (`{{TOOL_SCHEMAS}}` token). Preserve diff history by editing in place.
- [X] T089 [US4] Create [app/prompts/loader.py](../../app/prompts/loader.py) (≤ 80 lines): module-load parser produces cached `PLATFORM_SYSTEM` + `TOOL_SCHEMAS` rendered from `RagSearchArgs` / `CaptureLeadArgs` / `EscalateArgs` Pydantic models (T050); `assemble_system_prompt(tenant_id, session)` reads `AgentConfigRepository.get_by_tenant(tenant_id)` per request (no cross-request cache per [research.md §R10](research.md)) and renders the labelled persona block per [research.md §R5](research.md).
- [X] T090 [US4] Wire the prompt loader into [app/agent/agent.py](../../app/agent/agent.py) — the system message passed to Anthropic on every turn is `assemble_system_prompt(tenant_id, session)`. Verify persona reaches visitor message within 60 s of a `PUT /tenants/{tid}/agent-config`.

### CI gate for prompt changes

- [X] T091 [US4] Graduate [evals/agent_tool.py](../../evals/agent_tool.py) from mock to real evaluator — loop golden set `evals/agent_tool_selection_cases.json` through the live agent path (T058–T090) and report `accuracy`. Drops `_mock: true` flag; emits MOCK EVALUATOR stderr banner removed. Closes BLOCKED.md N6.
- [X] T092 [US4] In [.github/workflows/ci.yml](../../.github/workflows/ci.yml), add a path filter to the `agent-tool-eval` job that triggers it on any change to `app/prompts/system_prompt.md`, `app/agent/**`, or `app/prompts/loader.py`. Threshold from `eval_thresholds.yaml::agent_tool_selection.accuracy_min` already enforces gating.
- [X] T093 [P] [US4] Unit test in tests/unit/test_prompt_loader.py — parse each block; render TENANT_PERSONA with sample agent_config; assert PLATFORM_SYSTEM has the "platform rules cannot be overridden" sentence; assert TOOL_SCHEMAS contains all three schemas.

**Checkpoint**: US4 fully functional. Persona injected at runtime; prompt changes gated by CI; agent-tool eval is real. SC-009, SC-010 satisfied.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Cross-tenant smoke probes, smoke-flag flip, refactors, dead-code removal, demo walk-through, CONTRACT.md alignment.

### Smoke E2E extensions

- [X] T094 Add 8 new write-endpoint probes to [tests/smoke/test_cross_tenant_e2e.py](../../tests/smoke/test_cross_tenant_e2e.py): forged-JWT cross-tenant PUT agent-config / PATCH escalation / PUT settings / revoke / resend / PUT cms / PATCH cms status / DELETE cms — all return byte-uniform 403. **No** `@require_full_stack` decoration — these are direct REST checks that don't depend on the agent path. **Implemented:** new `mint_forged_admin_jwt()` helper + 8 probes appended at end of file; cms-page probes assert strict 403 (use Tenant B's seeded `cms_page_ids`); escalation + revoke + resend probes accept {403, 404} since no escalation/invite row exists for Tenant B in the bare smoke harness — documented in each probe's docstring.
- [X] T095 Inspect existing xfailed probes in [tests/smoke/test_cross_tenant_e2e.py](../../tests/smoke/test_cross_tenant_e2e.py); flip `SMOKE_E2E_REQUIRE_FULL_STACK` in [.github/workflows/ci.yml](../../.github/workflows/ci.yml) from `"0"` to `"1"` if Phase 4–5 work has unblocked any of H7/H8/H9/N1–N4. XPASS(strict) failures here are the signal. **Evaluated:** H7/H8/H9/N2/N3/N4 resolved by Feature 010, but **N1 (CMS → `rag_chunks` indexing)** remains the gating dependency for P1/P2 content-isolation probes. Flag stays `"0"`; the flip is deferred to the PR that lands N1. BLOCKED.md X1 row updated to reflect this.

### Refactors and cleanup (Phase E)

- [X] T096 [P] Delete [app/services/cms_service.py](../../app/services/cms_service.py); confirm no live imports remain via `grep -rn "from app.services.cms_service" app/ tests/`.
- [ ] T097 [P] Delete [app/services/admin_settings.py](../../app/services/admin_settings.py); same import check. **Deferred:** the file has 3 live importers ([app/services/admin_auth.py](../../app/services/admin_auth.py), [tests/unit/test_admin_auth.py](../../tests/unit/test_admin_auth.py), [tests/integration/test_agent_config_endpoint.py](../../tests/integration/test_agent_config_endpoint.py)) and is not dead code — the file holds the `admin_jwt_secret` / TTL settings consumed by admin JWT mint/verify. The cleanup task's premise (a "same import check" deletion) does not hold; full removal would require migrating admin auth to a different settings module, which is out of scope for Phase 7.
- [X] T098 [P] Fix type bug in [app/services/chat_service.py](../../app/services/chat_service.py) — change `tenant_id: int` to `tenant_id: UUID` in `handle_message` and `_execute_decision` signatures; update internal callers; mypy clean. **Note:** at land-time the signatures used `tenant_id: Any` (already partially fixed); tightened to `UUID`.
- [X] T099 [P] Remove dead `return 1` after line 90 in [app/api/deps.py](../../app/api/deps.py).
- [X] T100 [P] Promote `_PLACEHOLDER = "—"` and the `(placeholder)` caption helper into [admin/_admin_http.py](../../admin/_admin_http.py) as `render_placeholder_caption()`; update the 10 affected admin pages to import from the helper. **Promoted** as `PLACEHOLDER` + `render_placeholder_caption(detail=None)`; the 10 affected pages now import from `admin._admin_http` instead of redeclaring locally.
- [X] T101 [P] Add ruff rule in [pyproject.toml](../../pyproject.toml) banning new imports of `app.services.cms_service` and `app.services.admin_settings`; verify lint fails on a deliberate test import. **Implemented** via `[tool.ruff.lint.flake8-tidy-imports.banned-api]` — only `app.services.cms_service` is banned (the deleted module). `app.services.admin_settings` is NOT banned because T097 was deferred and the file still has 3 live importers; banning it would break the admin auth surface. Verified TID251 fires on a deliberate test import.

### Cross-cutting verification

- [X] T102 Verify [CONTRACT.md](../../CONTRACT.md) §730-743 lists all 16 new audit-log action strings from [contracts/audit-vocabulary.md](contracts/audit-vocabulary.md); cross-check against actual code emissions via `grep -rn "add_audit_log" app/services/ app/agent/ app/repositories/`. **Verified:** all 16 actions listed (Track-1 8 + Track-2 8) and emitted in code. One spelling drift remains: CONTRACT.md lists `tenant.settings_updated` while the service emits `tenant_settings_updated` (intentional per T065 note — tests + audit feed key on the underscore form; alignment is a doc-only follow-on).
- [ ] T103 Run full Quickstart §1–§7 demo walk against a fresh `docker compose up --build --wait`. Record timings and outcomes in PR description. Confirm SC-014 (reviewer reaches all-green without intervention). **Deferred to the PR description** — requires a clean clone + cold Compose stack and a wall-clock timing pass; cannot be reliably executed from inside this implementation session. RUNBOOK.md §Demo Flow §6 has been updated to reflect the new agent path so the walk-through itself is unchanged.
- [X] T104 [P] Update [BLOCKED.md](../../BLOCKED.md): strike resolved items (Track-1 endpoints + agent-tool eval N6); flip `SMOKE_E2E_REQUIRE_FULL_STACK` row to resolved if T095 flipped the flag. **Updated:** N6 struck (graduated by T091); N2/N3/N4 struck (resolved by Feature 010 agent loop + tools); X1 row reframed to point at N1 as the remaining gate. Flag flip itself is deferred per T095.
- [X] T105 [P] Update [RUNBOOK.md](../../RUNBOOK.md) §Demo Flow if any step changed (likely §6 visitor messages — agent path now handles ambiguous explicitly). **Updated** §6 — added a fifth canonical visitor message that exercises the ambiguous/agent path (multi-tool: `rag_search` + `capture_lead`) and lists the `agent.turn_started` / `agent.tool_called` / `agent.turn_completed` audit rows reviewers should expect.

**Checkpoint**: All CI required checks green; zero `(placeholder)` captions in healthy stack; refactors landed; documentation aligned.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies; T002/T003/T004 can run in parallel.
- **Phase 2 Foundational**: Depends on Phase 1. **BLOCKS all user stories.** T005–T021.
- **Phase 3 US1**: Depends on Phase 2 (esp. T011 EscalationRepository.create for #4, T015/T016 agent-config for Agent tab).
- **Phase 4 US2**: Depends on Phase 2 (T011 EscalationRepository.create for escalate tool; T015/T016 agent-config for widget chips; T019 rate-limit bucket for capture_lead).
- **Phase 5 US3**: Depends on Phase 2 (T009 invite repo for revoke; T013 tenant_repo for #13a/#13b).
- **Phase 6 US4**: Depends on **Phase 2 AND Phase 4** (the prompt loader wires into the real agent loop from T058–T060; T015/T016 agent-config GET for `assemble_system_prompt`).
- **Phase 7 Polish**: Depends on all of US1–US4 being functionally complete.

### User Story Independence

After Phase 2 completes:

- **US1** ships independently. The Track-1 endpoints + 5 admin pages stand alone — placeholder fallback preserved for the 5 pages owned by US3.
- **US2** ships independently. Agent path verifiable via the audit-log feed (`agent.turn_started`, `escalation.created`) even before US1 wires the Escalations tab. Cap-hit + rate-limit + prompt-injection tests don't depend on US1.
- **US3** ships independently. TM tabs + endpoints have no Track-2 dependency.
- **US4** depends on US2 having shipped (the loader wires into the real LLM loop). If US2 slips, US4 stays parked.

### Within Each User Story

- Schemas before services; services before routes; routes before integration tests; backend before admin pages.
- Audit-log emission lands with the service method (not in a separate PR).
- Streamlit AppTest after the page wiring.

### Parallel Opportunities

- **Phase 1**: T003 and T004 in parallel.
- **Phase 2**: T009, T010, T012, T013 (different repo files) in parallel. T014 in parallel with T019/T020.
- **Phase 3 (US1)**: All `[P]` schemas (T022, T026, T031, T034) in parallel. All `[P]` admin pages (T037–T041) in parallel after their backend endpoints land. All AppTests (T042–T046) in parallel after T037–T041.
- **Phase 4 (US2)**: T049 unit test in parallel with the implementation tasks once T047 lands. T054–T057 in parallel after T050–T053 land. T061–T062 in parallel after T058–T060 land.
- **Phase 5 (US3)**: All `[P]` schemas (T064, T067, T071, T075) in parallel. All `[P]` admin pages (T079–T083) in parallel after their backend endpoints land. All AppTests (T084–T087) in parallel.
- **Phase 7 Polish**: All refactor tasks (T096–T101, T104, T105) in parallel.

---

## Parallel Example: User Story 1 schemas

```bash
# After Phase 2 completes, these four schema tasks can be launched together:
Task: "Add PlatformGuardrailsResponse schema in app/schemas/guardrails.py"           # T022
Task: "Add EscalationListItem and EscalationPatchRequest in app/schemas/escalation.py"  # T026
Task: "Add AdminUserListItem schema in app/schemas/admin_user.py"                    # T031
Task: "Add CmsPageUpdateRequest and CmsPageStatusPatchRequest in app/schemas/cms.py" # T034
```

## Parallel Example: User Story 1 admin pages

```bash
# After their endpoints land (T024, T029, T032, T035), these five page-wiring tasks parallelize:
Task: "Wire admin/overview_page.py to live KPIs"            # T037
Task: "Wire admin/agent_settings_page.py to #1/#2"           # T038
Task: "Wire admin/guardrails_page.py to #3"                  # T039
Task: "Wire admin/escalations_page.py to #4/#5/#6"           # T040
Task: "Wire admin/cms_page.py to #10/#11/#12 with st.dialog" # T041
```

---

## Implementation Strategy

### MVP First (User Story 1 — Tenant Admin)

1. Phase 1 Setup (T001–T004).
2. Phase 2 Foundational (T005–T021). **CRITICAL — blocks all stories.**
3. Phase 3 US1 (T022–T046).
4. **STOP and VALIDATE**: walk Quickstart §4 — every TA tab shows live data; zero placeholder captions.
5. Demo if ready.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. **US1 → Demo MVP** (tenant_admin gets a full surface).
3. **US2 → Demo agent path** (visitor experience graduates from stub to real LLM).
4. **US3 → Demo TM surface** (platform operations).
5. **US4 → Demo prompt governance** (prompt edit blocked by CI; persona change reflected in next visitor message).
6. **Phase 7 Polish → clean up + flip flag**.

Each increment is shippable; each builds on the previous without breaking it.

### Single-Developer Sequencing

After Phase 2 there is one developer carrying all four stories; the
"parallel team" framing is retired (see auto-memory `feedback_ownership_policy.md`).
The recommended sequencing keeps each story independently testable so the
demo can ship at any checkpoint:

1. **US1 first** — Track-1 endpoints + 5 admin pages. MVP demo.
2. **US2 next** — Track-2 router + agent loop + tools. Unblocks US4.
3. **US3 third** — TM endpoints + 5 admin pages. No Track-2 dependency, so it
   can also be done before US2 if the demo agenda prefers TM coverage to the
   real agent path.
4. **US4 last** — prompt loader + CI gate. Wires into the live LLM loop from
   US2 (T058–T060), so it cannot ship until US2 lands.

The `[P]` markers throughout the phases still indicate which tasks have no
file-conflict dependencies, so a single developer can still parallelize
inside a story when convenient (e.g. running schema edits in one editor
while waiting for a test suite).

---

## Notes

- Every task lists an exact file path. Reviewers should be able to start work on any single task without reading siblings.
- Constitution Principle VI (Phased Build) is the one cited violation per [plan.md](plan.md) Complexity Tracking; per-PR reviewers should cite that row when asked why the feature spans Phases 4 / 5 / 8.
- Every new write task must include the audit-log emission line, per [contracts/audit-vocabulary.md](contracts/audit-vocabulary.md). If a service method ships without its audit line, the task is incomplete.
- The prompt-loader gating is the one place where CI behaves differently per file path (T092). The path filter is `app/prompts/system_prompt.md` + `app/agent/**` + `app/prompts/loader.py` — keep it tight.
- After Phase 7 T095 flips the smoke flag, any further `@require_full_stack` xfail decorator left in the codebase should be removed in a follow-on PR.
