---

description: "Tasks for the Secure Widget Token Exchange feature"
---

# Tasks: Secure Widget Token Exchange

**Input**: Design documents from `specs/001-widget-token-exchange/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Test tasks are INCLUDED because the spec explicitly requests them (FR-007 byte-identical refusal verification, FR-021 + SC-009 redaction verification, FR-011/FR-012 browser-storage-discipline verification).

**Organization**: Tasks are grouped by user story. The three stories from spec.md are: US1 (P1) Visitor reaches chat-ready, US2 (P1) Unauthorized origins refused indistinguishably, US3 (P2) Tokens short-lived and memory-only.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1, US2, or US3 (omitted for Setup, Foundational, and Polish phases)
- Every task description includes the exact file path

## Path Conventions

This repo is a multi-service monorepo (per [plan.md](plan.md) §Project Structure). Paths below are repository-root-relative:
- Backend: `app/`
- Frontend widget: `frontend/widget/`
- Tests: `tests/security/`, `tests/unit/` (Amer owns these directories)
- Config: `.env.example`

Amer-owned files only. No path below crosses into Hiba's, Nasser's, or Ayoub's slices — confirmed against the `# Owner: <Name>` headers and CONTRACT.md §3.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project-level configuration for the new feature. Touches `.env.example` and `frontend/widget/package.json` only.

- [ ] T001 Add widget-feature env vars to `.env.example` — `WIDGET_JWT_SECRET` (placeholder, 32+ bytes), `WIDGET_LOG_SALT` (placeholder, 32+ bytes base64), `WIDGET_TOKEN_TTL_SECONDS=900`, `WIDGET_RATE_PER_IP=10`, `WIDGET_RATE_PER_WIDGET=60`, `WIDGET_REPO_BACKEND=memory`. Include a comment line above each saying which FR it serves (FR-004, FR-020, FR-009, FR-015, FR-016, Complexity-Tracking row 2).
- [X] T002 [P] Add dev dependencies to `frontend/widget/package.json` — `vitest`, `@vitest/ui`, `jsdom`, `@types/node`. Add a `"test": "vitest"` script. Do not yet run `npm install`; the package.json change alone is the task.
- [X] T003 [P] Verify `pyjwt` and `structlog` are already in `pyproject.toml` (they are — confirmed in plan.md research). No edit needed unless the verification fails; if it does, add them under `[project.dependencies]`.

**Checkpoint**: env-var contract documented, frontend test runner declared, backend deps confirmed.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Domain models, repository interface + in-memory adapter, feature-scoped settings, rate-limiter primitive, and structured-logging helper. All user stories depend on these.

**⚠️ CRITICAL**: No user-story work can start until this phase completes.

- [X] T004 [P] Create `app/domain/widget.py` (NEW, `# Owner: Amer`) with Pydantic v2 models: `WidgetTokenRequest` (single field `widget_id: UUID`), `WidgetTokenResponse` (`token: str`, `expires_in: int`, `session_id: UUID`), `WidgetConfigDomain` (mirrors the joined row: `id`, `tenant_id`, `widget_id`, `allowed_origins: list[str]`, `enabled: bool`, `tenant_status: Literal["active","suspended","erasing","erased"]`), and `WidgetTokenRefusalReason` enum (`unknown_widget`, `origin_not_allowlisted`, `widget_disabled`, `tenant_not_active`, `rate_limited_per_ip`, `rate_limited_per_widget`).
- [X] T005 [P] Create `app/services/widget_settings.py` (NEW, `# Owner: Amer`) with `WidgetSettings(BaseSettings)` pulling the env vars from T001. Use `pydantic-settings`. Provide a module-level `widget_settings()` cached accessor (single source of truth per worker). DO NOT modify `app/config.py` (Hiba-owned).
- [X] T006 Create `app/repositories/widget_repo.py` (NEW, `# Owner: Amer`, schema-touching code flagged for Hiba review at PR time) with `WidgetRepository` Protocol: `async def get_by_widget_id(self, widget_id: UUID) -> WidgetConfigDomain | None`. Add docstring referencing CONTRACT.md §8.1 schema and noting this is the one read path where `tenant_id` flows OUT of the lookup (per data-model.md §1).
- [X] T007 In `app/repositories/widget_repo.py`, implement `InMemoryWidgetRepository` with a hard-coded test fixture matching [quickstart.md §Step 2](quickstart.md) (widget_id `9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d`, tenant `1111…`, allowed_origins `["https://customer-site.example","http://localhost:5500"]`, enabled, tenant_status active). Mark with a `# NOTE: temporary affordance per plan.md Complexity Tracking row 2` comment.
- [X] T008 In `app/repositories/widget_repo.py`, add a `get_widget_repository()` factory that returns `InMemoryWidgetRepository` when `WIDGET_REPO_BACKEND == "memory"`. SQL adapter slot is left as `raise NotImplementedError("Pending Hiba widget_configs migration")` for the `"sql"` branch — this lights up later without re-touching this file.
- [X] T009 [P] Create `app/services/rate_limiter.py` (NEW, `# Owner: Amer`) with `RateLimiter` Protocol (`async def check(self, scope_key: str) -> bool`) and `InMemoryTokenBucketRateLimiter` implementation. Token-bucket per scope_key; capacity and refill rate set per-instance at construction. Thread-safe via `asyncio.Lock`. Module-level factory returning two pre-configured instances (per-IP, per-widget) seeded from `WidgetSettings`.
- [X] T010 [P] Create `app/services/widget_logging.py` (NEW, `# Owner: Amer`) using `structlog`. Three exports:
  - `emit_refusal(reason, widget_id, source_ip, origin, latency_ms, tenant_id=None)` — emits `widget.token.refused`; hashes `widget_id` and `source_ip` via `HMAC-SHA256(WIDGET_LOG_SALT, value)` (hex digest); includes `tenant_id` only when provided (i.e., when the widget was resolved — per data-model.md §3).
  - `emit_issuance(tenant_id, widget_id, source_ip, origin, latency_ms)` — emits `widget.token.issued`.
  - `widget_trace_span(origin)` — context manager that opens a distributed trace span named `widget.token.exchange` per **FR-022**. Span attributes: `request.origin`, `widget_id_hash`, `outcome` (set on exit), `outcome.reason` (refusals only), `tenant_id` (issuance only), `latency_ms`. Uses stdlib `contextvars` for `trace_id` propagation so the span participates in whatever tracing backend Ayoub later wires up; the implementation is a thin in-process logger for this phase.

**Checkpoint**: Domain + repo + settings + limiter + logger all wired and importable. User-story implementations can now begin.

---

## Phase 3: User Story 1 — Visitor on an authorized host site can chat (P1) 🎯 MVP

**Goal**: A visitor loading a tenant's host site whose origin is allowlisted gets a JWT and the widget reaches the chat-ready state. Establishes the happy path only — validation rigor and refusal indistinguishability are US2's job.

**Independent Test**: From quickstart.md Step 3, the curl command with the valid `(widget_id, Origin)` pair returns a 200 with a JWT whose claims decode correctly. The browser test from quickstart.md Step 5 shows the chat input visible.

### Tests for User Story 1 (write first, must fail before implementation)

- [X] T011 [P] [US1] Create `tests/security/test_widget_token.py` (NEW, `# Owner: Amer`) with the happy-path test: POST `/widgets/token` with the fixture widget_id + an allowlisted origin returns 200; response body has `token`, `expires_in`, `session_id`; JWT verifies against `WIDGET_JWT_SECRET`; claims include the correct `tenant_id`, `widget_id`, `origin`, server-generated `session_id`, and `exp = iat + 900`. Use FastAPI's `httpx.AsyncClient` test client.
- [X] T012 [P] [US1] Create `frontend/widget/src/__tests__/api.test.ts` (NEW, `# Owner: Amer`) with a vitest test that calls a mocked `/widgets/token` endpoint and asserts the returned token is stored in a module-scope variable, NOT in `localStorage`, `sessionStorage`, or `document.cookie`. (Validates FR-011, FR-012 at the JS layer.)

### Implementation for User Story 1

- [X] T013 [US1] Implement `WidgetTokenService` in `app/services/widget_service.py` (NEW, `# Owner: Amer`) with `issue_token(widget_id, origin, source_ip) -> WidgetTokenResponse`. Happy path only at this stage: call repo, mint JWT (claims per data-model.md §2), call `emit_issuance` (T010), return response. No validation gates yet — that's T019–T022.
- [X] T014 [US1] In `app/services/widget_service.py`, add a private `_mint_jwt(tenant_id, widget_id, origin, session_id) -> str` helper using PyJWT HS256 with `WidgetSettings.widget_jwt_secret`. Set `iat` = `int(time.time())`, `exp` = `iat + WIDGET_TOKEN_TTL_SECONDS`. (Pure function — testable from T011.)
- [X] T015 [US1] Replace the placeholder `POST /widgets/token` in `app/api/routes/widgets.py` (existing, `# Owner: Amer`) with the real route: parse `WidgetTokenRequest`, read the `Origin` header (required; return 400 `{"error":"bad_request"}` if missing), resolve client IP from `request.client.host`, dispatch to `WidgetTokenService`. Add `Cache-Control: no-store` to every response (contracts/widget-token-endpoint.md). Use `Depends(get_widget_token_service)` for DI.
- [X] T016 [P] [US1] Create `frontend/widget/src/types.ts` (NEW, `# Owner: Amer`) with TypeScript types matching contracts/widget-token-endpoint.md (`WidgetTokenResponse`) and contracts/widget-loader-postmessage.md (`HostOriginMessage`, `ReadyMessage`).
- [X] T017 [P] [US1] Create `frontend/widget/src/api.ts` (NEW, `# Owner: Amer`) with `exchangeToken(backendUrl, widgetId)` that POSTs to `/widgets/token`. Store the returned token, session_id, expires_in in module-scope `let` variables — never reach for `localStorage`/`sessionStorage`/cookies. Export a `getToken()` accessor for other modules in the iframe.
- [X] T018 [US1] Modify `frontend/widget/src/main.tsx` (existing, `# Owner: Amer`) to: (a) listen for the `concierge.widget.host_origin` postMessage per [contracts/widget-loader-postmessage.md](contracts/widget-loader-postmessage.md); (b) once received, call `api.ts::exchangeToken`; (c) on success, render a minimal chat-ready shell (input + send button + empty message list); (d) on failure, render "Widget unavailable" and hide the input; (e) on success, postMessage `concierge.widget.ready` back to the parent. Do NOT implement chat send yet (that's Phase 2 in amer-works.md, out of scope here).
- [X] T019 [US1] Modify `frontend/widget/public/widget.js` (existing, `# Owner: Amer`) to: (a) read `data-widget-id` and `data-backend-url` from the script tag (`data-backend-url` defaults to the script tag's origin if absent); (b) create the iframe pointing at `<backendUrl>/widget?widget_id=<widgetId>`; (c) on iframe `load`, postMessage `{type:"concierge.widget.host_origin", origin: window.location.origin}` to the iframe restricted to `iframe.src`; (d) idempotency guard — if an iframe with `data-concierge-widget-id` matching the same widgetId already exists in the DOM, abort silently.

**Checkpoint**: Happy path complete. Run quickstart.md Step 3 happy-path curl — returns 200 with a valid JWT. T011 + T012 green. Storage check from quickstart.md Step 5 shows no token in browser storage. **Refusals are NOT secure yet — any widget_id from any origin will return a token.** US2 fixes that.

---

## Phase 4: User Story 2 — Token requests from unauthorized origins are refused (P1)

**Goal**: Every refusal cause (unknown widget, origin not allowlisted, widget disabled, tenant not active, rate-limited per-IP, rate-limited per-widget) returns a byte-identical `403 {"error":"widget_unavailable"}`. Refusals are logged internally with a reason bucket and hashed identifiers. The widget lookup always runs before any refusal returns (FR-008a timing-discipline).

**Independent Test**: From quickstart.md Step 3, run the four refusal curls (wrong origin, unknown widget, disabled widget, suspended tenant) plus two rate-limit-exhaustion runs. Diff the response bodies — all must be identical except `Date`. SC-002 passes.

### Tests for User Story 2 (write first, must fail before implementation)

- [X] T020 [P] [US2] Extend `tests/security/test_widget_token.py` with refusal tests: unknown widget (random UUID) returns 403 `{"error":"widget_unavailable"}`; origin not in allowlist returns the SAME 403; widget disabled returns the SAME 403; tenant suspended returns the SAME 403. Use `pytest.mark.parametrize` to drive the four cases. Add a meta-test: `assert response.content == reference_content` across all four (byte-equality).
- [X] T021 [P] [US2] Extend `tests/security/test_widget_token.py` with rate-limit tests: 11th request from same IP within 60s returns the same 403 with same body bytes; 61st request for same widget_id within 60s returns the same 403. The rate-limited response MUST be byte-identical to the validation refusals.
- [X] T022 [P] [US2] Extend `tests/security/test_widget_token.py` with the timing-discipline test (FR-008a): unknown-widget refusal latency is within ±20ms of origin-mismatch refusal latency (proxy for "widget lookup always ran"). Use `time.perf_counter` around `client.post`; run each path 20 times and compare medians.
- [X] T023 [P] [US2] Create `tests/security/test_widget_token_redaction.py` (NEW, `# Owner: Amer`) for SC-009: capture structlog output during 100 refusal runs; assert no raw widget_id (UUID strings), no raw IP (dotted-quad or IPv6), no JWT signing secret value, no raw JWT appears in any log line. Hashes are present and non-reversible (length 64 hex chars).
- [X] T024 [P] [US2] Create `tests/unit/test_widget_service.py` (NEW, `# Owner: Amer`) covering origin canonicalization: `https://Customer.Example` matches `https://customer.example` (case-insensitive host); `https://customer.example/some/path` matches `https://customer.example` (path ignored); `https://customer.example` does NOT match `https://www.customer.example` (no subdomain rollup); `https://customer.example:443` does NOT match `https://customer.example:8443` (port exact); `http://customer.example` does NOT match `https://customer.example` (scheme exact).

### Implementation for User Story 2

- [X] T025 [US2] In `app/services/widget_service.py`, add `_canonicalize_origin(origin: str) -> str | None` that parses with `urllib.parse.urlsplit`, returns `f"{scheme}://{host.lower()}[:port]"` (port included only if non-default), and returns `None` for malformed origins. Pure function — covered by T024.
- [X] T026 [US2] In `app/services/widget_service.py`, add origin-matching logic inside `issue_token`: canonicalize the request `Origin`, canonicalize each entry in `widget_config.allowed_origins`, compare set-membership. Return refusal `origin_not_allowlisted` on miss.
- [X] T027 [US2] In `app/services/widget_service.py`, add tenant-active gate (`tenant_status != "active" → tenant_not_active`) and enabled gate (`widget_config.enabled is False → widget_disabled`).
- [X] T028 [US2] In `app/services/widget_service.py`, enforce **FR-008a timing discipline**: every refusal path inside `issue_token` MUST execute the repository lookup before returning, even when `widget_id` lookup misses. Structure the function so the lookup is unconditional; refusal branches happen after. Use a helper `_run_validation_pipeline(widget_id, origin)` that returns `tuple[WidgetConfigDomain | None, WidgetTokenRefusalReason | None]` and pays the same DB cost on every path.
- [X] T029 [US2] In `app/services/widget_service.py`, integrate the two `RateLimiter` instances from T009: check the per-IP limiter before lookup (cheap reject path that still goes through `_run_validation_pipeline` to preserve timing uniformity), check the per-widget limiter after lookup. Emit `rate_limited_per_ip` / `rate_limited_per_widget` refusals via T010.
- [X] T030 [US2] In `app/services/widget_service.py`, wrap the entire `issue_token` body in the `widget_trace_span(origin)` context manager (T010) and wire `emit_refusal` / `emit_issuance` at every return point. Each refusal carries its `WidgetTokenRefusalReason`, hashed widget_id, hashed source_ip, raw origin, latency_ms, and `tenant_id` when the widget was resolved. The trace span auto-tags `outcome` (and `outcome.reason` on refusal) on exit — covers **FR-022**.
- [X] T031 [US2] In `app/api/routes/widgets.py`, add a centralized refusal-response helper `_refusal_response()` that returns FastAPI `JSONResponse(status_code=403, content={"error":"widget_unavailable"}, headers={"Cache-Control":"no-store","Content-Type":"application/json"})`. Used by every refusal path. ZERO variation in body bytes across causes.
- [X] T032 [US2] In `app/api/routes/widgets.py`, ensure malformed-request handling returns the `400 {"error":"bad_request"}` body documented in contracts/widget-token-endpoint.md — distinct from security refusals because malformed requests cannot be triggered by an enumeration probe.

**Checkpoint**: All US2 tests green. Manual curl walkthrough of the four refusal causes produces byte-identical 403s. Logs show hashed identifiers and reason buckets. Rate baselines fire on the 11th per-IP / 61st per-widget request.

---

## Phase 5: User Story 3 — Tokens are short-lived and visitor-bound (P2)

**Goal**: Issued tokens are unusable after their 15-minute window; each issuance gets a fresh `session_id`; browser storage is verified empty after a successful exchange. The downstream consumer's expiry-rejection contract is satisfied by the JWT's `exp` claim — the consumer-side test that asserts `/chat` rejects an expired token is blocked on Hiba (her `get_tenant_id_from_widget_token` dep is the consumer); that test is tracked under Polish but cannot run until her work lands.

**Independent Test**: From quickstart.md Step 4, decoding the JWT shows `exp - iat == 900`. Two consecutive POSTs to `/widgets/token` return tokens with different `session_id` values. The frontend vitest from T012 still passes after the full exchange flow runs end-to-end in jsdom.

### Tests for User Story 3 (write first, must fail before implementation)

- [X] T033 [P] [US3] Extend `tests/security/test_widget_token.py` with: two successive token requests for the same `(widget_id, origin)` return tokens whose `session_id` claims differ; both tokens decode to `exp == iat + WidgetSettings.widget_token_ttl_seconds`.
- [X] T034 [P] [US3] Extend `tests/unit/test_widget_service.py` with a TTL-config test: setting `WIDGET_TOKEN_TTL_SECONDS=120` via monkeypatch causes `_mint_jwt` to emit `exp = iat + 120`. Confirms FR-018 (runtime configurability).
- [X] T035 [P] [US3] Extend `frontend/widget/src/__tests__/api.test.ts` with an end-to-end mocked flow: mount the component, fire the postMessage handshake, mock-resolve `/widgets/token`, assert the in-memory token is present AND `localStorage`/`sessionStorage`/`document.cookie` remain empty.

### Implementation for User Story 3

- [X] T036 [US3] Confirm `_mint_jwt` in `app/services/widget_service.py` already sets `exp = iat + WidgetSettings.widget_token_ttl_seconds` (this was T014 — verify; if the TTL was hardcoded, refactor to read from settings).
- [X] T037 [US3] Confirm `issue_token` generates a fresh `session_id = uuid4()` on every call (was T013 — verify and add a regression test in T033 if not).
- [X] T038 [US3] In `frontend/widget/src/api.ts`, audit the token-store accessors: confirm `getToken()` returns the module-scope variable, that the variable is reset to `null` on a 401 response from any subsequent call, and that no code path writes to browser storage. Add a comment block at the top citing FR-011 and FR-012.
- [X] T039 [US3] In `frontend/widget/src/main.tsx`, confirm the chat-ready shell does not call `useState` or `localStorage` for the token — the token must flow through the api.ts module-scope variable only. UI components hold `session_id` only (for display/correlation).

**Checkpoint**: All US3 tests green. Two consecutive curls return different `session_id`s; JWT `exp - iat == 900`. Browser storage check from quickstart.md Step 5 passes after a full end-to-end flow.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Quickstart validation, demo polish, items deliberately deferred from the user-story phases, integration with cross-team contracts.

- [ ] T040 Run the full quickstart.md verification flow end-to-end against a fresh `docker compose up --build api`. Capture the output of all five steps in the PR description.
- [X] T041 [P] Add a one-line CI smoke check to `tests/smoke/` (Amer-owned) that issues one token against the in-memory backend and asserts it decodes — independent of any other team's work. (Stub for the bigger Phase 7 e2e in amer-works.md; ensures the token path doesn't regress.)
- [ ] T042 [P] Update [.env.example](.env.example) header comment to explain that `WIDGET_REPO_BACKEND=memory` is a temporary affordance; flip to `sql` once Hiba's `widget_configs` migration is merged.
- [X] T043 [P] Add **two** Decision entries to [DECISIONS.md](../../DECISIONS.md). DECISIONS.md is shared but both are appends, no other edits — per CONTRACT.md §16 changes to auth/CI behavior are tracked here.
  - "Decision N — Widget Token Endpoint Owns Rate Limit Baseline (per-IP + per-widget)" — citing spec.md FR-015–FR-019 and clarification Q1.
  - "Decision N+1 — Parallel-Track Build for Phase 7 (Widget) During Team Phase 0" — citing PROJECT_PLAN.md (Wednesday slot for widget token exchange), constitution §VI bullet 2 (cross-phase deps via CONTRACT.md), and plan.md Complexity Tracking row 1. This DECISIONS.md entry **is** the explicit team agreement required by constitution §Development Workflow.
- [ ] T044 PR prep: confirm `git diff --name-only` lists only Amer-owned paths; tag `@Hiba` for the `widget_configs` repo-query review and `@Ayoub` for the JWT-signing-secret-from-env decision (so he wires Vault later); link spec.md, plan.md, data-model.md, contracts/, quickstart.md in the PR description.
- [X] T045 **BLOCKED ON HIBA — track only**: tests/security expiry-rejection test that asserts `/chat` rejects an expired widget token (requires Hiba's real `get_tenant_id_from_widget_token` JWT verifier). Add as `pytest.mark.skip(reason="blocked on Hiba widget-token JWT verifier")` so the test scaffolding is in place when she ships.
- [X] T046 [P] Add a happy-path latency sanity assertion in `tests/security/test_widget_token.py`: run the happy-path POST 100 times against the in-memory backend, assert server-side p95 < 50 ms. This is the smallest covering task for spec.md **SC-003**; the full geographic-region p95 verification is left for Phase 7 e2e smoke in [amer-works.md](../../amer-works.md).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies. Start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1. **Blocks all user-story phases.**
- **Phase 3 (US1)**: Depends on Phase 2. Independent of US2 and US3.
- **Phase 4 (US2)**: Depends on Phase 2 AND on a *minimum* US1 (the service must exist before US2 extends it). In practice T013/T014 from US1 should land before T025–T031 from US2.
- **Phase 5 (US3)**: Depends on Phase 2 AND on US1 service skeleton. Largely a verification phase; can run in parallel with US2 completion.
- **Phase 6 (Polish)**: Depends on US1+US2+US3 being green.

### Task Dependencies Within Each Story

**US1**:
- T011, T012 (tests) before T013–T019 (implementation) — write tests first per template.
- T013 → T014 → T015 (backend chain).
- T016, T017 can run in parallel with backend (different files).
- T018 depends on T016 + T017.
- T019 depends on T018 conceptually (loader produces the message the iframe consumes), but they edit different files so they can be authored in either order; integration check happens at the checkpoint.

**US2**:
- T020–T024 (tests) before T025–T032 (implementation).
- T025 (canonicalize helper) before T026 (origin matching).
- T028 (timing discipline) constrains T025–T029 — must structure the lookup-then-branch flow.
- T031 (centralized refusal helper) before T032 (using the helper from the route).

**US3**:
- T033–T035 (tests) before T036–T039 (implementation, mostly verifications/confirmations).

### Parallel Opportunities

- **Phase 1**: T002 + T003 in parallel after T001.
- **Phase 2**: T004 + T005 + T009 + T010 in parallel; T006 → T007 → T008 sequential (same file).
- **Phase 3**:
  - Tests T011 + T012 in parallel.
  - Backend chain T013 → T014 → T015 sequential.
  - Frontend T016 + T017 in parallel with backend chain.
- **Phase 4**:
  - Tests T020 + T021 + T022 + T023 + T024 all in parallel.
  - Implementation T025 → T026 → T027 → T028 → T029 → T030 → T031 → T032 mostly sequential (all in `widget_service.py` or `widgets.py`).
- **Phase 5**: T033 + T034 + T035 in parallel; T036/T037 are confirmations, T038/T039 in parallel.
- **Phase 6**: T041, T042, T043 in parallel.

---

## Parallel Example: User Story 1

```text
# After Phase 2 is green, fire these in parallel:

Task: T011 [P] [US1] Happy-path test in tests/security/test_widget_token.py
Task: T012 [P] [US1] Storage-discipline vitest in frontend/widget/src/__tests__/api.test.ts

# Then the backend implementation chain (sequential):
Task: T013 [US1] WidgetTokenService.issue_token in app/services/widget_service.py
Task: T014 [US1] _mint_jwt helper in app/services/widget_service.py  (same file as T013, so sequential)
Task: T015 [US1] Replace placeholder route in app/api/routes/widgets.py

# And the frontend chain in parallel with the backend:
Task: T016 [P] [US1] Types in frontend/widget/src/types.ts
Task: T017 [P] [US1] api.ts in frontend/widget/src/api.ts
Task: T018 [US1] main.tsx wiring  (depends on T016 + T017)
Task: T019 [US1] widget.js loader  (different file from T018, can run in parallel after T016)
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Phase 1: Setup.
2. Phase 2: Foundational.
3. Phase 3: User Story 1 — happy path lights up.
4. **STOP and VALIDATE**: Run T011, T012, and the curl from quickstart.md Step 3 happy path. Confirm the widget renders chat-ready in a browser.
5. **DO NOT DEPLOY THE MVP STOP POINT** — at this stage, *any* widget_id from *any* origin issues a valid token. The MVP is testable but not yet shippable. US2 must follow before merging.

### Incremental Delivery (recommended)

1. Setup + Foundational → foundation ready.
2. US1 → demo-able happy path (testable, NOT yet shippable for the reason above).
3. US2 → security correctness. **First shippable point.** PR can be opened here.
4. US3 → verification of lifetime + memory-only discipline. Layers on top of US2.
5. Polish → quickstart validation, DECISIONS.md, PR review prep.

### Solo Developer Strategy (Amer)

This feature is one developer's slice. Stories can't be parallelized across people. Recommended task-level parallelism:
- Phase 2: open four parallel terminals/editors on T004, T005, T009, T010 (different files).
- Phase 3: backend chain in one terminal, frontend chain in another.
- Phase 4: write all five test tasks first (parallel), then walk the implementation sequentially in `widget_service.py`.

---

## Format Validation

Every task above conforms to: `- [ ] TXXX [P?] [Story?] description with file path`.
- Setup phase (T001–T003): no `[Story]` label ✓
- Foundational phase (T004–T010): no `[Story]` label ✓
- User-story phases (T011–T039): every task carries `[US1]`, `[US2]`, or `[US3]` ✓
- Polish phase (T040–T045): no `[Story]` label ✓
- Every task includes either a file path or a clear no-file action (T040 quickstart run, T044 PR prep, T045 blocked-tracking).

## Task Count Summary

| Phase | Count | Story |
|---|---|---|
| Setup | 3 | — |
| Foundational | 7 | — |
| US1 — Visitor reaches chat-ready | 9 | US1 |
| US2 — Refusals indistinguishable | 13 | US2 |
| US3 — Tokens short-lived | 7 | US3 |
| Polish | 7 | — |
| **Total** | **46** | |

Parallelizable tasks (marked `[P]`): 18.
Tasks blocked on teammates: 1 (T045 — Hiba).
