---

description: "Task list for 005-admin-read-only-pages"
---

# Tasks: Admin Read-Only Pages

**Input**: Design documents from `/specs/005-admin-read-only-pages/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included. The feature spec mandates per-page Streamlit AppTest coverage (FR-015, SC-005); test tasks below are first-class deliverables, not optional polish.

**Organization**: Tasks are grouped by user story (US1–US4) so each story can be implemented, tested, and demoed independently. The Setup phase is intentionally tiny because Streamlit, httpx, and pytest are already installed; the Foundational phase wires the sidebar and creates four empty page stubs so each US phase only has to fill in one `render()` plus its test file.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

This is an extension to the existing `admin/` Streamlit package. Page modules live in [admin/](../../admin/) and integration tests in [tests/integration/](../../tests/integration/), per the Project Structure block in [plan.md](plan.md).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Make sure the project can host the new admin pages and their tests. No new dependencies; everything required (Streamlit ≥ 1.32, httpx, pytest) is already installed.

- [X] T001 Verify [tests/integration/](../../tests/integration/) directory exists and create [tests/integration/__init__.py](../../tests/integration/__init__.py) if missing (empty file) so pytest can discover the new test modules.
- [X] T002 [P] Confirm the existing `pyproject.toml` already pins `streamlit>=1.32`, `httpx`, and `pytest`; if `streamlit` is below 1.32 (AppTest API requirement — see [research.md](research.md) Decision 7), bump it in `pyproject.toml` and note the bump in [DECISIONS.md](../../DECISIONS.md). Do **not** add new dependencies.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Wire the sidebar and create four empty page-module stubs so each user story phase can be picked up by a different developer in parallel without stepping on `admin/streamlit_app.py` again.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete. After this phase the app is runnable (sidebar shows 5 tabs) but the four new pages render `st.info("Not implemented yet")` placeholders — that is by design.

- [X] T003 Modify [admin/streamlit_app.py](../../admin/streamlit_app.py): extend the sidebar `st.sidebar.radio` to list the tabs in the order `["Tenant", "CMS", "Leads", "Usage", "Widget", "Guardrails"]`; route each new tab to the matching `<module>.render()` call (`tenant_page.render()`, `cms_page.render()`, `leads_page.render()`, `usage_page.render()`); leave the existing `Widget` branch calling `widget_page.render()` exactly as it was; leave the existing `Guardrails` placeholder branch untouched (it is not yet wired and is out of scope for this slice — spec FR-001 only authorizes *adding* the four new tabs, not removing existing ones). Default selection should be `Tenant`. Keep the file under ~50 LOC.
- [X] T004 [P] Create [admin/tenant_page.py](../../admin/tenant_page.py) as a stub: `# Owner: Amer` header, module docstring referencing spec 005 US1, and a single `def render() -> None:` body that calls `st.info("US1 not implemented yet — see specs/005-admin-read-only-pages/")`. ≤ 20 LOC. **Do not** import httpx here yet.
- [X] T005 [P] Create [admin/cms_page.py](../../admin/cms_page.py) as a stub: same pattern as T004 but for US2; body calls `st.info("US2 not implemented yet …")`. ≤ 20 LOC.
- [X] T006 [P] Create [admin/leads_page.py](../../admin/leads_page.py) as a stub: same pattern as T004 but for US3; body calls `st.info("US3 not implemented yet …")`. ≤ 20 LOC.
- [X] T007 [P] Create [admin/usage_page.py](../../admin/usage_page.py) as a stub: same pattern as T004 but for US4; body calls `st.info("US4 not implemented yet …")`. ≤ 20 LOC.
- [X] T008 Manually verify (`streamlit run admin/streamlit_app.py`) that the sidebar shows the five tabs, that selecting Tenant/CMS/Leads/Usage shows the "not implemented yet" `st.info`, and that the Widget tab is unchanged from Phase 4. No new test file required for this checkpoint — visual confirmation only.

**Checkpoint**: Foundation ready. Each user story below can now be picked up in parallel because each story owns exactly one new page file and one new test file.

---

## Phase 3: User Story 1 — Tenant overview (Priority: P1) 🎯 MVP

**Goal**: A tenant admin opens the Tenant tab and sees a header card (name, slug, status, plan, created_at) plus a table of the 20 most recent audit log entries. When either backend endpoint is missing or returns the placeholder shape, sample data renders with a visible `(placeholder)` badge.

**Independent Test**: Run `pytest tests/integration/test_tenant_page.py -v`. Two scenarios must pass: (1) mocked `GET /tenants/{tenant_id}` returns the documented JSON shape and mocked `GET /tenants/{tenant_id}/audit-logs` returns three rows → page renders the header card and a three-row dataframe with no `(placeholder)` text anywhere; (2) the audit-log mock returns 404 → page renders the header card from real tenant data AND a sample audit table AND a visible `(placeholder)` badge near the audit section.

### Tests for User Story 1 (write FIRST, ensure they FAIL before implementation)

- [X] T009 [P] [US1] Create [tests/integration/test_tenant_page.py](../../tests/integration/test_tenant_page.py) with three `AppTest`-based tests: `test_happy_path_renders_real_audit_log`, `test_placeholder_fallback_renders_sample_audit_log` (mock returns 404), and `test_server_error_falls_back_to_placeholder` (mock returns 500 — and an additional parametrized case raising `httpx.ConnectError`). Inject the page's `httpx.Client` via `httpx.MockTransport`; assert on (a) the header card fields per [contracts/tenant-overview.md](contracts/tenant-overview.md), (b) the dataframe keyed `tenant_audit_log_table`, (c) presence/absence of the literal `(placeholder)` caption text. The 5xx/network test must confirm no raw stack trace or response body is rendered on the page. Mark this file as covering FR-004, FR-005, FR-006, FR-013.

### Implementation for User Story 1

- [X] T010 [US1] Fill in [admin/tenant_page.py](../../admin/tenant_page.py)'s `render()` body per [contracts/tenant-overview.md](contracts/tenant-overview.md) and [data-model.md §Entity 1–2](data-model.md): construct one `httpx.Client(base_url=..., headers=_DEV_HEADERS, timeout=10.0)`; GET `/tenants/{tenant_id}` and render the header card (display `slug` and `plan` as `"—"` if absent per research Decision 4); GET `/tenants/{tenant_id}/audit-logs`. Wrap each GET in a `try/except httpx.HTTPError` and treat the exception **and** any non-2xx status **and** any missing-required-field body as the single placeholder fallback (research Decision 5): switch to the canned sample list (3 rows covering `tenant.provisioned`, `widget.origin_added`, `cms.page_updated`) and render `st.caption("(placeholder)")` near the affected section. Render the audit table via `st.dataframe(..., key="tenant_audit_log_table")` with `metadata_json` truncated to 80 chars (use `json.dumps(meta)[:80]`). Never `st.write` the raw exception or response body (FR-013). Target ≤ ~120 LOC. **No** Save/Edit/Suspend/Erase controls anywhere (FR-006).
- [X] T011 [US1] In [admin/tenant_page.py](../../admin/tenant_page.py), add the `TODO(hiba-handoff)` comment block above `_DEV_HEADERS` mirroring [admin/widget_page.py](../../admin/widget_page.py)'s line-style, so the auth handoff is a single grep target.
- [X] T012 [US1] Run `pytest tests/integration/test_tenant_page.py -v` — both tests must now pass.

**Checkpoint**: User Story 1 is fully functional and independently demonstrable. The MVP of this slice ships here if needed.

---

## Phase 4: User Story 2 — CMS list (Priority: P2)

**Goal**: A tenant admin opens the CMS tab and sees a table of CMS pages (title, slug, status, updated_at). They can filter by status. Clicking/selecting a row opens a read-only detail viewer showing title, slug, body, source_url. Placeholder fallback if `GET /cms/pages` is unreachable.

**Independent Test**: Run `pytest tests/integration/test_cms_page.py -v`. Three scenarios: happy path renders all three documented statuses; switching the status selectbox to `published` narrows the dataframe to only published rows; a 404 mock renders sample data with a visible `(placeholder)` badge.

### Tests for User Story 2 (write FIRST, ensure they FAIL before implementation)

- [X] T013 [P] [US2] Create [tests/integration/test_cms_page.py](../../tests/integration/test_cms_page.py) with `AppTest` tests: `test_happy_path_renders_all_pages`, `test_status_filter_narrows_rows`, `test_placeholder_fallback_on_404`, and `test_server_error_falls_back_to_placeholder` (mock returns 500 and a `httpx.ConnectError` variant). Assert on the `cms_status_filter` selectbox, the `cms_page_table` dataframe, the detail viewer's rendered markdown, and the presence/absence of `(placeholder)`. The 5xx/network test must confirm no raw exception or response body leaks to the page. Mark covering FR-007, FR-008, FR-013.

### Implementation for User Story 2

- [X] T014 [US2] Fill in [admin/cms_page.py](../../admin/cms_page.py)'s `render()` body per [contracts/cms-list.md](contracts/cms-list.md) and [data-model.md §Entity 3–4](data-model.md): one `httpx.Client` with the dev headers; GET `/cms/pages` wrapped in `try/except httpx.HTTPError`; on **any** non-2xx response or on a transport exception, use the canned sample (one row per allowed status) and render `st.caption("(placeholder)")`. A 2xx empty list `[]` is **not** a fallback — render "No CMS pages yet." Render an `st.selectbox` keyed `cms_status_filter` with options `["all","draft","published","archived"]`; client-side filter the list by the selected status; render `st.dataframe(..., key="cms_page_table")` showing only `title, slug, status, updated_at`; render an `st.selectbox` keyed `cms_detail_select` listing `(title — slug)` per filtered row; below that render the selected page's `title`, `slug`, `st.markdown(body)`, and `source_url` as a link when present. Never `st.write` the raw exception or response body (FR-013). **No** create/edit/delete affordances (FR-008). Target ≤ ~120 LOC.
- [X] T015 [US2] Run `pytest tests/integration/test_cms_page.py -v` — all three tests must pass.

**Checkpoint**: User Stories 1 and 2 both work independently. Sidebar navigation between them does not affect rendering.

---

## Phase 5: User Story 3 — Leads viewer (Priority: P2)

**Goal**: A tenant admin opens the Leads tab and sees captured leads with the `contact` column redacted to first-3-chars + `***`. Status filter narrows rows. Placeholder fallback when the leads endpoint is missing.

**Independent Test**: Run `pytest tests/integration/test_leads_page.py -v`. Four scenarios: happy path renders all three filterable statuses (each row contact redacted); status filter narrows to `qualified` only; 404 mock renders sample data with a visible `(placeholder)` badge; redaction test covers `""`, `"a"`, `"abc"`, and `"avery@example.com"` inputs.

### Tests for User Story 3 (write FIRST, ensure they FAIL before implementation)

- [X] T016 [P] [US3] Create [tests/integration/test_leads_page.py](../../tests/integration/test_leads_page.py) with `AppTest` tests: `test_happy_path_renders_redacted_contacts`, `test_status_filter_narrows_rows`, `test_placeholder_fallback_on_404`, `test_server_error_falls_back_to_placeholder` (mock returns 500 and a `httpx.ConnectError` variant — and asserts no unredacted contact leaks even on the error path), and `test_redact_contact_edge_cases` (unit-style test of the redaction function imported from `admin.leads_page`). Mark covering FR-009, FR-010, FR-013, SC-004.

### Implementation for User Story 3

- [X] T017 [US3] Fill in [admin/leads_page.py](../../admin/leads_page.py)'s `render()` body per [contracts/leads-viewer.md](contracts/leads-viewer.md) and [data-model.md §Entity 5](data-model.md): module-level `def redact_contact(value: str) -> str: return f"{(value or '')[:3]}***"`; GET `/leads` wrapped in `try/except httpx.HTTPError`; on **any** non-2xx, missing-required-field 2xx body, or transport exception, use the canned sample (one row per filterable status, including one with `name=null` and one with `quality_score=null`) and render `st.caption("(placeholder)")`. Render `st.selectbox` keyed `leads_status_filter` with options `["all","captured","qualified","spam"]`; before rendering the dataframe, apply `redact_contact` to every `contact` value; render `st.dataframe(..., key="leads_table")` with columns `created_at, name, contact, intent, status, quality_score`; render `name` as `"—"` when null and `quality_score` as `"—"` when null. **Never** log, `st.write`, or include in an error message the unredacted contact (Principle V, FR-013). **No** qualify/spam/export/edit controls (FR-010). Target ≤ ~120 LOC.
- [X] T018 [US3] Run `pytest tests/integration/test_leads_page.py -v` — all four tests must pass.

**Checkpoint**: User Stories 1–3 all work independently. The Leads page leaks no unredacted contact to logs or UI.

---

## Phase 6: User Story 4 — Usage dashboard (Priority: P3)

**Goal**: A tenant admin opens the Usage tab and sees month-to-date total tokens, total cost USD, a per-feature breakdown across all six features, and a daily-cost line chart. Placeholder fallback when the usage rollup endpoint is missing.

**Independent Test**: Run `pytest tests/integration/test_usage_page.py -v`. Three scenarios: happy path renders both metrics, a six-row breakdown table, and a line chart with the expected per-day series; 404 mock renders sample data with the `(placeholder)` badge AND ≥ 2 datapoints in the line chart (so the chart doesn't degrade); missing-feature defaults verified (feature key absent from response → row renders `0` and `$0.00`).

### Tests for User Story 4 (write FIRST, ensure they FAIL before implementation)

- [X] T019 [P] [US4] Create [tests/integration/test_usage_page.py](../../tests/integration/test_usage_page.py) with `AppTest` tests: `test_happy_path_renders_totals_breakdown_and_chart`, `test_placeholder_fallback_on_404`, `test_server_error_falls_back_to_placeholder` (mock returns 500 and a `httpx.ConnectError` variant), and `test_missing_feature_defaults_to_zero`. Assert on the two `st.metric` widgets, the `usage_by_feature_table` dataframe row count (== 6), the `st.line_chart` datapoint count, and presence/absence of `(placeholder)`. The 5xx/network test must confirm no raw exception or response body leaks to the page. Mark covering FR-011, FR-012, FR-013.

### Implementation for User Story 4

- [X] T020 [US4] Fill in [admin/usage_page.py](../../admin/usage_page.py)'s `render()` body per [contracts/usage-dashboard.md](contracts/usage-dashboard.md) and [data-model.md §Entity 6](data-model.md): GET `/tenants/{tenant_id}/usage` wrapped in `try/except httpx.HTTPError`; on **any** non-2xx response, missing-required-field 2xx body, or transport exception, use the canned sample (realistic totals + 14 daily datapoints) and render `st.caption("(placeholder)")`. Render `st.metric("Tokens (month-to-date)", total_tokens)` and `st.metric("Cost USD (month-to-date)", f"${total_cost_usd:.2f}")`; build the by-feature table by iterating the fixed feature vocabulary `["chat","embedding","classifier","rag","agent","guardrails"]` (default missing keys to `{"tokens": 0, "cost_usd": 0.0}` per research Decision 4) and render via `st.dataframe(..., key="usage_by_feature_table")`; build the daily series into a pandas DataFrame indexed by date and render via `st.line_chart`. If the period block is present, render `st.caption(f"{period.start} → {period.end}")` under the metrics. Never `st.write` the raw exception or response body (FR-013). **No** rate-limit or billing controls (FR-012). Target ≤ ~120 LOC.
- [X] T021 [US4] Run `pytest tests/integration/test_usage_page.py -v` — all three tests must pass.

**Checkpoint**: All four user stories work independently. The full sidebar (Tenant, CMS, Leads, Usage, Widget) is demo-ready.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Verify the read-only invariant, check the helper-extraction threshold, and run the quickstart end to end.

- [X] T022 [P] Run the read-only grep from [quickstart.md](quickstart.md#verify-the-read-only-invariant) — must return zero matches across the four new page files: `grep -nE "client\.(put|post|delete|patch)\(|st\.button.*Save|st\.button.*Delete|st\.form_submit_button" admin/tenant_page.py admin/cms_page.py admin/leads_page.py admin/usage_page.py`. If anything matches, remove it (FR-002, FR-006, FR-008, FR-010, FR-012).
- [X] T023 Audit duplicated logic across [admin/tenant_page.py](../../admin/tenant_page.py), [admin/cms_page.py](../../admin/cms_page.py), [admin/leads_page.py](../../admin/leads_page.py), [admin/usage_page.py](../../admin/usage_page.py). If **the same** header-construction / base-URL / placeholder-detection code appears in **more than two** files, extract it into [admin/_admin_http.py](../../admin/_admin_http.py) and refactor the duplicating files to import it. Otherwise **do not** create the helper (Principle VII, research Decision 8). Document the outcome in one line in the PR description.
- [X] T024 [P] Confirm each new page file is ≤ ~120 LOC (`wc -l admin/tenant_page.py admin/cms_page.py admin/leads_page.py admin/usage_page.py`). If any file is materially over, refactor by inlining duplicated formatting helpers or, if duplication has already crossed the > 2 threshold above, move shared code into `_admin_http.py`.
- [X] T025 Run the full new test suite together: `pytest tests/integration/test_tenant_page.py tests/integration/test_cms_page.py tests/integration/test_leads_page.py tests/integration/test_usage_page.py -v`. Total runtime must be under 30 s locally (SC-005).
- [X] T026 [P] Run [quickstart.md](quickstart.md) manually end-to-end: `streamlit run admin/streamlit_app.py`, click each of the five sidebar tabs with no backend running, confirm each new page shows the `(placeholder)` badge, the Widget tab is unchanged, and the Leads page renders only redacted contacts (SC-002, SC-003, SC-004).
- [X] T027 Update [DECISIONS.md](../../DECISIONS.md) with a one-paragraph entry summarizing this feature: read-only Phase 8 admin pages, placeholder fallback contract for unpublished endpoints, dev-header auth pending Hiba handoff, helper-extraction outcome from T023. Reference this spec by branch name.

**Checkpoint**: Slice is shippable. Read-only invariant verified, file-size targets verified, tests green, demo path green with and without a live backend.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion. **Blocks all user stories**.
- **User Stories (Phases 3–6)**: All depend on Foundational. Each story is independent of the others — they may proceed in parallel by different developers, or sequentially in priority order (P1 → P2 → P2 → P3).
- **Polish (Phase 7)**: Depends on all four user stories being complete (the grep audit and LOC check both need all four page files filled in).

### User Story Dependencies

- **US1 (P1)**: Independent. Only depends on Foundational.
- **US2 (P2)**: Independent. Only depends on Foundational.
- **US3 (P2)**: Independent. Only depends on Foundational.
- **US4 (P3)**: Independent. Only depends on Foundational.

There are **no** cross-story integrations in this slice — each page owns exactly one new module and one new test file. That is by design (Principle VII smallest-change, and so the four stories can be staffed in parallel during a demo crunch).

### Within Each User Story

- The test file (T009 / T013 / T016 / T019) is written **first** and is expected to fail until the page's `render()` body is filled in.
- The `render()` implementation task (T010 / T014 / T017 / T020) follows.
- The test-pass verification task (T012 / T015 / T018 / T021) closes the story.

### Parallel Opportunities

- **Inside Foundational**: T004, T005, T006, T007 (the four page stubs) are all `[P]` — they touch four different new files. T003 (sidebar wiring) is **not** parallel with these because it imports the four modules; in practice T003 can be done first or last, but the four stubs can land in any order.
- **Across user stories**: once Phase 2 is done, US1 / US2 / US3 / US4 can each be picked up by a different developer in parallel. There are no shared mutating files until Phase 7's helper-extraction audit.
- **Inside a story**: only one implementation file per story, so no inner-story parallelism beyond test-vs-impl ordering.
- **Inside Polish**: T022, T024, T026 are independent of one another and can run in parallel.

---

## Parallel Example: Foundational Phase

```bash
# After T001/T002 finish, the four page stubs can land in any order:
Task: "Create admin/tenant_page.py stub (T004)"
Task: "Create admin/cms_page.py   stub (T005)"
Task: "Create admin/leads_page.py stub (T006)"
Task: "Create admin/usage_page.py stub (T007)"

# Then a single developer wires the sidebar:
Task: "Modify admin/streamlit_app.py sidebar routing (T003)"
```

## Parallel Example: User Stories (after Foundational)

```bash
# Four developers can take one story each:
Developer A: T009 → T010 → T011 → T012   (US1 Tenant)
Developer B: T013 → T014 → T015           (US2 CMS)
Developer C: T016 → T017 → T018           (US3 Leads)
Developer D: T019 → T020 → T021           (US4 Usage)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T002).
2. Complete Phase 2: Foundational (T003–T008) — sidebar wired, four stubs in place, Widget tab unchanged.
3. Complete Phase 3: User Story 1 (T009–T012) — Tenant overview live + tested.
4. **STOP and VALIDATE**: `pytest tests/integration/test_tenant_page.py` green; manual `streamlit run` shows Tenant tab working.
5. Demo-ready. The remaining three pages still show "not implemented yet" stubs, which is acceptable for an MVP slice but should not be merged to `main` in that state — finish Phase 4–7 first.

### Incremental Delivery (recommended for a single developer)

1. Setup + Foundational → foundation ready, app runnable.
2. Add US1 → tests green → demo Tenant overview.
3. Add US2 → tests green → demo CMS list.
4. Add US3 → tests green → demo Leads viewer with redaction.
5. Add US4 → tests green → demo Usage dashboard.
6. Run Phase 7 polish → open PR.

### Parallel Team Strategy (recommended for a demo crunch)

1. Whole team lands Phase 1 + Phase 2 together (one PR or one sitting).
2. Once Foundational is done, four developers each take one US phase.
3. Each PR adds one new page module + one new test file — no merge conflicts because each story touches disjoint files.
4. Whoever finishes last runs Phase 7 polish (grep audit, helper-extraction audit, LOC check, full test run, DECISIONS.md entry).

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks.
- [Story] label maps task to US1/US2/US3/US4 for traceability.
- Every user story is independently completable and testable — no story imports another story's code in this slice.
- Verify tests fail before filling in the corresponding `render()` body.
- Commit after each task or logical group; the assistant does not run git actions unless explicitly asked (project rule).
- Stop at any checkpoint to demo a story independently.
- Avoid: vague tasks, introducing the `_admin_http.py` helper before T023's audit shows duplication > 2 (research Decision 8), or adding any mutating control on the four new pages (FR-002 + FR-006 + FR-008 + FR-010 + FR-012).
