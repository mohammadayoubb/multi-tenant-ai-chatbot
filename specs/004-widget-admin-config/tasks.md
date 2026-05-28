---
description: "Task list for Tenant Admin Widget Configuration Page (004)"
---

# Tasks: Tenant Admin Widget Configuration Page

**Input**: Design documents from `/specs/004-widget-admin-config/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/widget-config-endpoint.md](./contracts/widget-config-endpoint.md), [contracts/audit-log-consumption.md](./contracts/audit-log-consumption.md)

**Tests**: REQUIRED. The spec's user input explicitly lists the test surface (happy path, role gate, validation, audit-call counting, frontend round-trip), and the contracts map clauses to test names. Tests come before the implementation edits they cover.

**Organization**: Tasks are grouped by user story. Most US tests are `[P]` (different `it`/`def test_*` cases in the same test file — coordinate via separate commits if working in parallel).

**Owner**: All tasks are Amer-owned. Two items require **Hiba review** at merge time:
- `app/repositories/widget_repo.py` changes (schema-touching, even though no SQL yet — see `data-model.md`)
- The two new audit-action strings (`widget.origin_added`, `widget.origin_removed`) added to `CONTRACT.md` vocabulary in T042

## Format: `[ID] [P?] [Story] Description with file path`

- **[P]**: Can run in parallel (different files, OR independent test cases in the same test file with no merge collision)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- File paths are exact

## Path Conventions (per plan.md §Project Structure)

- Backend: `app/api/deps.py`, `app/api/routes/widgets.py`, `app/domain/widget.py`, `app/services/widget_service.py`, `app/repositories/widget_repo.py`
- Frontend: `admin/streamlit_app.py`, `admin/widget_page.py`
- Tests: `tests/security/test_widget_admin_config.py`, `tests/unit/test_widget_config_service.py`, `tests/integration/test_admin_widget_page.py`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: One-time additions that every user story depends on.

- [X] T001 [P] Create mock `require_tenant_admin` dependency in [app/api/deps.py](../../app/api/deps.py). **First**: verify that `app.config.Settings` exposes an `environment` (or equivalent) attribute. If absent, do NOT modify `app/config.py` (Hiba-owned, protected per CLAUDE.md §Protected Files) — instead, use `os.getenv("CONCIERGE_ENV", "dev")` directly inside the dep, and note this in the task PR description. Then: reads `X-Concierge-Role` and `X-Concierge-Tenant-Id` headers; returns a `TenantAdminContext` dataclass `{tenant_id: UUID, actor_id: str | None}`; raises `HTTPException(403)` if role header missing or != `"tenant_admin"`; raises `HTTPException(500, "role-dep mock disabled in non-dev environments")` when the chosen env check indicates non-dev. Include the comment `# TODO(hiba-handoff): replace with Hiba's authenticated role dep when it lands.`
- [X] T002 [P] Extend domain Pydantic models in [app/domain/widget.py](../../app/domain/widget.py): add `theme_json: dict | None = None` and `greeting: str | None = None` to `WidgetConfigDomain` (additive); add new `WidgetConfigResponse` and `WidgetConfigUpdateRequest` models per [data-model.md](./data-model.md). `WidgetConfigUpdateRequest` MUST set `model_config = ConfigDict(extra="forbid")` so an inbound `tenant_id` produces 422. `greeting` field uses `Field(default=None, max_length=280)`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Repository, service skeleton, route plumbing, and admin page scaffolding shared by all three user stories.

**⚠️ CRITICAL**: No user-story task can start until Phase 2 is complete.

- [X] T003 Extend `WidgetRepository` Protocol + `InMemoryWidgetRepository` in [app/repositories/widget_repo.py](../../app/repositories/widget_repo.py): add `async def get_by_tenant_id(self, tenant_id: UUID) -> WidgetConfigDomain | None` and `async def update_by_tenant_id(self, tenant_id: UUID, *, allowed_origins: list[str], enabled: bool, theme_json: dict | None, greeting: str | None) -> WidgetConfigDomain | None`. InMemory impl persists `theme_json`/`greeting` in its existing dict. Keep the module header note about Hiba review.
- [X] T004 Add `WidgetConfigService` skeleton in [app/services/widget_service.py](../../app/services/widget_service.py) alongside the existing `WidgetTokenService`. Constructor takes `repo: WidgetRepository` and `audit_logger: AuditLogger` — where `AuditLogger` is a new single-method `Protocol` defined in the same file: `async def add_audit_log(self, tenant_id: UUID, actor_role: str, action: str, actor_id: str | None = None, metadata: dict | None = None) -> None`. The real `TenantRepository` (Hiba's, CONTRACT.md §190) implements this Protocol incidentally; this naming keeps the dependency surface explicit. Methods: `async def get_for_tenant(self, tenant_id: UUID) -> WidgetConfigDomain | None`, `async def update_widget_config(self, tenant_id: UUID, request: WidgetConfigUpdateRequest, actor_id: str | None) -> WidgetConfigDomain` — leave `update_widget_config` as a thin pass-through that just calls `repo.update_by_tenant_id` for now (origin diff + audit logic lands in US1).
- [X] T005 Add `GET /widgets/config` route handler in [app/api/routes/widgets.py](../../app/api/routes/widgets.py). Uses `Depends(require_tenant_admin)` and a new `Depends(get_widget_config_service)` (write the factory inline next to the existing `get_widget_token_service`). Returns `WidgetConfigResponse` on 200; returns the standard refusal body on 403 (caller's tenant has no row) — match the existing `_byte_response`/`_refusal_response` pattern in the file for indistinguishability.
- [X] T006 Add `PUT /widgets/config` route handler in [app/api/routes/widgets.py](../../app/api/routes/widgets.py). Body validated via `WidgetConfigUpdateRequest` (FastAPI handles 422 automatically for type/`extra="forbid"`/`max_length` failures). Calls `service.update_widget_config(...)` and returns the updated `WidgetConfigResponse`. Service-layer raises produce 422 (validation), 403 (cross-tenant — match GET pattern), or 500 (audit rollback).
- [X] T007 Wire admin Widget tab to a new module in [admin/streamlit_app.py](../../admin/streamlit_app.py): when `page == "Widget"`, import and call `from admin.widget_page import render` then `render()`. Create [admin/widget_page.py](../../admin/widget_page.py) with a minimal skeleton: imports streamlit, defines `def render() -> None:` that fetches `GET /widgets/config` via httpx with the dev headers, stores the response in `st.session_state["widget_config_draft"]`, and displays the raw values (UI editors arrive in US1–US3). Use the dev fixture tenant `11111111-1111-1111-1111-111111111111`.

**Checkpoint**: Foundation ready — GET works end-to-end, PUT accepts a body but doesn't yet do origin diff/audit. US1, US2, US3 can be started in parallel.

---

## Phase 3: User Story 1 — Origin editor with audit logging (Priority: P1) 🎯 MVP

**Goal**: A tenant admin can add/remove origins through the admin page. Each net add/remove emits exactly one `widget.origin_added` / `widget.origin_removed` audit log call. Invalid URLs and empty-while-enabled are rejected at 422.

**Independent Test**: Two seeded tenants. Admin of tenant A logs in, adds an origin, removes an existing one, saves. The widget_config row reflects the change, two audit calls fire (one add, one remove), and admin of A cannot read or write tenant B's row.

### Tests for US1 (write first, before implementation T028)

- [X] T008 [P] [US1] In [tests/security/test_widget_admin_config.py](../../tests/security/test_widget_admin_config.py), add fixture setup: `httpx.AsyncClient` against the FastAPI app, `app.dependency_overrides` swapping the InMemory repo with a seeded fake holding two tenants, and an `AsyncMock` for the audit-log call site. Reusable across US1/US2/US3 tests in this file.
- [X] T009 [P] [US1] Test `test_get_widget_config_returns_current_row` — admin of tenant A gets 200 with the seeded row (origins, enabled, theme=null, greeting=null).
- [X] T010 [P] [US1] Test `test_get_widget_config_without_admin_returns_403` — missing or wrong `X-Concierge-Role` header → 403 with body `{"error":"forbidden"}`.
- [X] T011 [P] [US1] Test `test_admin_config_cross_tenant_returns_403` — admin of tenant A sends `X-Concierge-Tenant-Id` for tenant B → 403 (indistinguishable from "no row"). Also assert the response body bytes are byte-equal to the role-missing case.
- [X] T012 [P] [US1] Test `test_put_widget_config_invalid_origin_returns_422` — body includes `"javascript:alert(1)"` or `"acme.com"` (no scheme) or `"ftp://acme.com"` → 422. No audit call made (assert `audit_mock.call_count == 0`).
- [X] T013 [P] [US1] Test `test_put_widget_config_enabled_without_origins_returns_422` — body with `allowed_origins: []` and `enabled: true` → 422. Row unchanged. Zero audit calls.
- [X] T014 [P] [US1] Test `test_put_widget_config_adds_origin_calls_audit_once` — seeded list `["https://acme.com"]`; PUT with `["https://acme.com", "https://blog.acme.com"]`; assert `audit_mock.call_count == 1`, call arg `action == "widget.origin_added"`, `metadata["origin"] == "https://blog.acme.com"`.
- [X] T015 [P] [US1] Test `test_put_widget_config_removes_origin_calls_audit_once` — seeded list `["https://acme.com", "https://blog.acme.com"]`; PUT with `["https://acme.com"]`; assert one call with `action == "widget.origin_removed"` and the removed origin in metadata.
- [X] T016 [P] [US1] Test `test_put_widget_config_mixed_change_audits_each_delta` — add 2 origins, remove 1; assert `audit_mock.call_count == 3` and the call_args_list contains the expected actions (sorted by origin string for deterministic assertion).
- [X] T017 [P] [US1] Test `test_put_widget_config_no_change_no_audit` — PUT with body byte-identical to current state → 200 OK, `audit_mock.call_count == 0`.
- [X] T018 [P] [US1] Test `test_put_widget_config_audit_failure_rolls_back` — `audit_mock.side_effect = RuntimeError("fake DB")` on the 1st origin_added call → response 500, row unchanged when re-fetched via GET.
- [X] T019 [P] [US1] Test `test_put_widget_config_normalizes_origins` — body `["HTTPS://Acme.com/", "https://acme.com:443/page"]` → persisted as one entry `["https://acme.com"]` (case-folded host, default port stripped, path stripped, deduped). One `widget.origin_added` call only for `https://acme.com`.
- [X] T020 [P] [US1] In [tests/unit/test_widget_config_service.py](../../tests/unit/test_widget_config_service.py), add unit tests for the normalization helper (`normalize_origin` returns canonical form for valid inputs, raises for invalid) — independent of HTTP layer.

### Implementation for US1

- [X] T021 [US1] Implement `normalize_origin(raw: str) -> str` helper in [app/services/widget_service.py](../../app/services/widget_service.py). Uses `urlsplit`; lowercases scheme + host; IDN-encodes host via `idna.encode` when non-ASCII (fallback to host as-is); strips default ports (80/http, 443/https); strips path/query/fragment/userinfo. Raises `ValueError` for non-`http`/`https` schemes, empty host, or malformed URLs. Reuses the existing `_DEFAULT_PORTS` constant.
- [X] T022 [US1] In [app/domain/widget.py](../../app/domain/widget.py), add a Pydantic `field_validator("allowed_origins", mode="after")` on `WidgetConfigUpdateRequest` that normalizes each origin via `normalize_origin` and raises `ValueError` (Pydantic surfaces as 422) on any failure. De-duplicates the result preserving first-seen order.
- [X] T023 [US1] In [app/domain/widget.py](../../app/domain/widget.py), add a `model_validator(mode="after")` that raises `ValueError` if `enabled is True and len(allowed_origins) == 0` (after normalization). 422 at the route boundary.
- [X] T024 [US1] Implement origin diff + audit-call sequencing in `WidgetConfigService.update_widget_config` in [app/services/widget_service.py](../../app/services/widget_service.py): fetch previous row; compute `added = sorted(new - previous)` and `removed = sorted(previous - new)` as sets; for each added/removed call `self._audit_logger.add_audit_log(...)` with the action and metadata shape from [contracts/audit-log-consumption.md §A2](./contracts/audit-log-consumption.md). No-op diff = zero calls.
- [X] T025 [US1] Wrap the update + audit calls in a single transaction context. For the InMemoryWidgetRepository path, use a Python try/except: stage the update in memory; on any audit-log exception, restore the pre-update snapshot and re-raise. (For the future SQL backend, this becomes `async with session.begin()`.)
- [X] T026 [US1] In [admin/widget_page.py](../../admin/widget_page.py), add the **origins editor** section and the page-wide Save controls:
  - List rendering of current origins (from `st.session_state["widget_config_draft"]["allowed_origins"]`), each with a "Remove" button; one text input + "Add origin" button.
  - URL-shape pre-validation in Python (`urllib.parse.urlsplit` + scheme/host check) so the user sees an error before Save.
  - **Unsaved-changes indicator** (FR-016): show "● Unsaved changes" prominently whenever `st.session_state["widget_config_draft"] != st.session_state["widget_config_saved"]`; show "✓ All changes saved" otherwise. Also add a "Discard changes" button that resets the draft to the saved snapshot.
  - **Save button** issues `PUT /widgets/config` with the full draft and on success replaces both `_draft` and `_saved` state with the server's response.
  - **Save-disabled rule** (FR-017): the Save button MUST be disabled whenever ANY of the following holds — origins list contains a value failing the URL pre-validation; greeting > 280 chars (US2); theme textarea fails `json.loads()` (US3); or `enabled` is true with empty origins. Compute `is_valid` once per render and pass `disabled=not is_valid` to `st.button(...)`.
  - **Save outcome display** (FR-018): on 200, show a green "Saved." banner. On 422, render the per-field error list from `response.json()["detail"]`. On 500, show a neutral "Save failed; please retry." banner (do NOT echo server error details).

**Checkpoint**: US1 fully functional and testable. MVP can ship after this story alone — origin allowlist is the highest-value tenant-admin capability and is auditable.

---

## Phase 4: User Story 2 — Greeting and enabled flag (Priority: P1)

**Goal**: A tenant admin can edit the greeting text (≤ 280 chars) and toggle the enabled flag. No audit log entries are emitted for these changes.

**Independent Test**: Admin sets greeting to `"Hello"`, saves, re-fetches via GET → greeting persists. Sets enabled to false, saves, GET returns enabled=false. Setting greeting > 280 chars → 422. Setting enabled=true with empty origins → 422 (shared rule from US1).

### Tests for US2

- [X] T027 [P] [US2] Test `test_put_widget_config_greeting_persists` — PUT with `greeting: "Hi from Acme"` → 200; GET → greeting matches; zero audit calls.
- [X] T028 [P] [US2] Test `test_put_widget_config_greeting_too_long_returns_422` — `greeting` of 281 characters → 422.
- [X] T029 [P] [US2] Test `test_put_widget_config_disable_with_empty_origins_allowed` — seeded with origins; PUT with `enabled: false` AND `allowed_origins: []` → 200 (toggle-off path is allowed per FR-008).
- [X] T030 [P] [US2] Test `test_put_widget_config_enable_with_empty_origins_rejected` — seeded with `enabled: false, allowed_origins: []`; PUT with `enabled: true, allowed_origins: []` → 422 (same rule as US1 T013 but exercised through the toggle path).

### Implementation for US2

- [X] T031 [US2] Verify `greeting: str | None = Field(default=None, max_length=280)` on `WidgetConfigUpdateRequest` (from T002) makes T028 pass without additional code. If FastAPI's error envelope shape is unwanted, no change needed — Pydantic's default is acceptable here.
- [X] T032 [US2] Verify the `enabled + empty origins` validator from T023 covers T030. No additional code expected.
- [X] T033 [US2] In [admin/widget_page.py](../../admin/widget_page.py), add the **greeting input** section: `st.text_input("Greeting", value=draft.get("greeting") or "", max_chars=280)` and a character counter beneath it.
- [X] T034 [US2] In [admin/widget_page.py](../../admin/widget_page.py), add the **enabled toggle** section: `st.toggle("Widget enabled", value=draft.get("enabled", True))`. If the toggle is `True` and the current origins list is empty, display a warning indicator and disable the Save button.

**Checkpoint**: US1 + US2 work independently.

---

## Phase 5: User Story 3 — Theme JSON editor with preview (Priority: P2)

**Goal**: A tenant admin can edit a free-form JSON theme blob, sees live JSON parse-error feedback, sees a preview (or a clear placeholder), and saves.

**Independent Test**: Admin pastes `{"primary": "#ff0066"}` into the theme textarea, sees the preview reflect the value (or a placeholder banner), clicks Save → 200; GET → theme_json matches. Pasting invalid JSON disables Save and shows an inline parse-error message.

### Tests for US3

- [X] T035 [P] [US3] Test `test_put_widget_config_theme_json_persists` — PUT with `theme_json: {"primary": "#ff0066"}` → 200; GET → matches.
- [X] T036 [P] [US3] Test `test_put_widget_config_theme_json_null_clears` — PUT with `theme_json: null` → 200; GET → null.
- [X] T037 [P] [US3] Test `test_put_widget_config_theme_non_object_returns_422` — PUT with `theme_json: "a string"` or `theme_json: 42` → 422 (Pydantic's `dict | None` rejects non-dict). PUT with `theme_json: {}` (empty object) → 200.

### Implementation for US3

- [X] T038 [US3] Verify `theme_json: dict | None = None` on `WidgetConfigUpdateRequest` (from T002) is sufficient. Pydantic v2 rejects non-dict JSON with 422 automatically.
- [X] T039 [US3] In [admin/widget_page.py](../../admin/widget_page.py), add the **theme editor** section: `st.text_area("Theme (JSON)", value=json.dumps(draft.get("theme_json") or {}, indent=2))`; on each rerun, attempt `json.loads(...)` and display either a green "Valid JSON" indicator or a red inline parse-error message. The Save button is disabled when JSON is invalid.
- [X] T040 [US3] In [admin/widget_page.py](../../admin/widget_page.py), add the **theme preview pane**: a placeholder iframe (`st.components.v1.iframe("/widget.js?preview=...", height=540)` or a simple `st.info("Theme preview: the saved theme will apply on next visitor mount. Live preview will land with the widget runtime's theme support.")`). Live-preview is a stretch goal; the placeholder satisfies US3 acceptance scenario 1's "or a placeholder iframe" clause.

**Checkpoint**: US1 + US2 + US3 all functional.

---

## Phase 6: Streamlit integration tests (cross-cuts US1–US3)

**Purpose**: Single integration test file exercising the admin page round-trip via `streamlit.testing.v1.AppTest` with a fake HTTP client.

- [X] T041 [US1] In [tests/integration/test_admin_widget_page.py](../../tests/integration/test_admin_widget_page.py), add fixture setup: `streamlit.testing.v1.AppTest.from_file("admin/widget_page.py")`, monkey-patch the page's httpx client to return a seeded fake `GET` response and accept the `PUT`. Reusable across US1/US2/US3 tests in this file.
- [X] T042 [US1] Test `test_admin_page_add_origin_round_trip` — `AppTest` runs; simulate typing a new origin into the Add input; simulate clicking Save; assert the fake `PUT` was called with `allowed_origins` containing the new entry; assert the success banner appears.
- [X] T043 [US2] Test `test_admin_page_greeting_save` — change greeting via `at.text_input(...).input("Hello")`; click Save; assert PUT body has the new greeting.
- [X] T044 [US3] Test `test_admin_page_theme_invalid_disables_save` — type invalid JSON into the theme textarea; assert Save button is disabled and the inline parse error is visible.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T045 [P] Add the two new audit-action strings (`widget.origin_added`, `widget.origin_removed`) to the audit-action vocabulary documentation in [CONTRACT.md](../../CONTRACT.md) in the audit section. **Tag Hiba for review** in the PR.
- [X] T046 [P] Add a Decision entry to [DECISIONS.md](../../DECISIONS.md): "004 widget admin config — mock `require_tenant_admin` is a temporary stand-in until Hiba's authenticated role dep lands; widget_configs theme_json/greeting columns persisted only in InMemory until Hiba's migration; audit-action vocabulary extended with `widget.origin_added` and `widget.origin_removed`." Reference research.md §R1, §R2 and contracts/audit-log-consumption.md §A5.
- [X] T047 Run [quickstart.md](./quickstart.md) sections 1–6 end-to-end locally; confirm tests green, curl flows behave, Streamlit page works. Document any deviation in the PR description.
- [X] T048 Walk the [CLAUDE.md](../../CLAUDE.md) §Pre-Merge Checklist for this feature. Confirm: no new tenant-owned table (extending existing one), repository scoped by `tenant_id`, no hardcoded secrets, role gate on every new route, `tenant_id` derived from trusted context only, **Hiba review requested** for the audit vocabulary addition and the widget_configs column adds, `DECISIONS.md` updated.

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 Setup (T001, T002)**: No dependencies — both files are new or additive, can start immediately.
- **Phase 2 Foundational (T003–T007)**: Depends on T001 (deps.py used by routes) and T002 (domain models used by service/repo). **Blocks all US tasks.**
- **Phase 3 US1 (T008–T026)**: Depends on Phase 2. Some intra-phase ordering — see below.
- **Phase 4 US2 (T027–T034)**: Depends on Phase 2. Largely independent of US1; safe to parallelize.
- **Phase 5 US3 (T035–T040)**: Depends on Phase 2. Independent of US1 and US2.
- **Phase 6 Integration tests (T041–T044)**: Depends on Phase 2 (skeleton page must exist) and on the per-US implementations (T026, T033/T034, T039/T040) being done.
- **Phase 7 Polish (T045–T048)**: Depends on US1–US3 complete.

### Within-phase dependencies

- **Within Phase 2**: T003 (repo) and T004 (service) depend on T002 (domain). T005 + T006 (routes) depend on T004. T007 (admin scaffold) is independent.
- **Within US1**: T008 (fixture setup) blocks T009–T020. T021 (normalize helper) blocks T022 (Pydantic validator using it). T022, T023 (Pydantic validators) block tests that exercise 422 paths (T012, T013, T019). T024 (diff/audit) and T025 (transaction wrap) block T014–T018. T026 (Streamlit origins editor) is independent of backend tests once T002–T007 are in.
- **Within US2**: T031, T032 are verification-only against T002/T023 — they should pass without new code. T033, T034 (Streamlit additions) edit the same file as T026 — run sequentially.
- **Within US3**: T038 is verification-only against T002. T039, T040 edit the same file as T026/T033/T034 — sequential.
- **Within Phase 6**: T041 (fixture) blocks T042–T044.

### Same-file constraints

- [app/services/widget_service.py](../../app/services/widget_service.py): T004, T021, T024, T025 all edit. Order: T004 → T021 → T024 → T025.
- [app/domain/widget.py](../../app/domain/widget.py): T002, T022, T023 all edit. Order: T002 → T022 → T023.
- [app/api/routes/widgets.py](../../app/api/routes/widgets.py): T005, T006. Order: T005 → T006.
- [admin/widget_page.py](../../admin/widget_page.py): T007, T026, T033, T034, T039, T040 all edit. Order matches task numbering.
- [tests/security/test_widget_admin_config.py](../../tests/security/test_widget_admin_config.py): T008 must be first (fixture); T009–T019, T027–T030, T035–T037 are `[P]` separate `def test_*` cases but coordinate via commits if working in parallel.

### Parallel opportunities

- T001 ∥ T002 (different files).
- After T007: US1 tests T009–T019 ∥ US2 tests T027–T030 ∥ US3 tests T035–T037 (all add separate test functions; coordinate commits).
- After T007: US1 implementation T021–T025 ∥ US2 verification T031–T032 ∥ US3 verification T038 (different files or no-op).
- Streamlit UI tasks T026, T033, T034, T039, T040 all edit `widget_page.py` — **NOT** parallelizable.
- Polish T045 ∥ T046 (different files); T047 and T048 are sequential walkthroughs.

---

## Parallel Example: US1 backend tests after T008 fixture is in

```text
# All [P]: each adds a separate `def test_*` function to the same test file.
# Coordinate by committing each test in its own commit so the file diff stays clean.
T009 — test_get_widget_config_returns_current_row
T010 — test_get_widget_config_without_admin_returns_403
T011 — test_admin_config_cross_tenant_returns_403
T012 — test_put_widget_config_invalid_origin_returns_422
T013 — test_put_widget_config_enabled_without_origins_returns_422
T014 — test_put_widget_config_adds_origin_calls_audit_once
T015 — test_put_widget_config_removes_origin_calls_audit_once
T016 — test_put_widget_config_mixed_change_audits_each_delta
T017 — test_put_widget_config_no_change_no_audit
T018 — test_put_widget_config_audit_failure_rolls_back
T019 — test_put_widget_config_normalizes_origins
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1 (T001, T002) and Phase 2 (T003–T007).
2. Complete US1 (T008–T026).
3. **STOP and VALIDATE**: a tenant admin can add/remove origins via the admin page, and every origin change is audited. The widget token endpoint already honors the live `allowed_origins` (per /clarify Q2), so the new origin works for visitor token exchanges immediately.
4. This is shippable as MVP for the feature. US2 and US3 add value but US1 alone unblocks the "tenant self-serve onto new domains" use case that the spec identifies as the highest-priority outcome.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 → tenant admins manage origins → ship.
3. US2 → greeting + enabled toggle → ship.
4. US3 → theme editor → ship (still no live-render impact until the widget runtime's theme support lands).
5. Polish (T045–T048) lands with US1 at the earliest (it's the first time audit-action vocabulary is extended).

### Parallel Team Strategy (Amer only — single-developer slice)

This feature is Amer-owned end to end (per Decision 5 in DECISIONS.md). Sequential execution is fine; the [P] markers above primarily document review-grouping, not staffing parallelism. Two cross-owner touchpoints require **Hiba** at merge time:

- **CONTRACT.md audit vocabulary** (T045) — Hiba reviews the new action strings.
- **widget_configs columns** (T002/T003 indirectly — implementation deferred to Hiba's migration) — Hiba reviews the column-add request whenever it gets scheduled.

Estimated effort: 1–2 days of focused work for the backend; a half-day for the Streamlit page; a half-day for tests and polish. Total ~3 days.

---

## Notes

- `[P]` tasks = different files OR independent test cases.
- Per the constitution, this feature is **risky** — `/speckit-analyze` MUST run after this `tasks.md` lands and before `/speckit-implement`.
- The mock `require_tenant_admin` dep and the InMemory-only theme/greeting persistence are flagged in plan.md Complexity Tracking; both are removed in follow-up PRs that consume Hiba's real deps.
- Audit-log assertions in tests mock the call site (`add_audit_log` on a fake `TenantRepository`), NOT the database. Real Hiba-owned audit-log writes are out of this feature's test scope (see [contracts/audit-log-consumption.md §A6](./contracts/audit-log-consumption.md)).
- Verify each implementation test fails before its code lands (TDD per CLAUDE.md §Team Rules): tests T009–T020 should fail when T021–T025 are unstarted; T027–T030 against T031–T032 are usually verification-only since T002/T023 likely already satisfy them.
- Commit after each user-story checkpoint to keep PRs reviewable.
