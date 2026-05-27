---
description: "Task list for Widget Loader Production Hardening (003)"
---

# Tasks: Widget Loader Production Hardening

**Input**: Design documents from `/specs/003-widget-loader-hardening/`
**Prerequisites**: [plan.md](./plan.md) (required), [spec.md](./spec.md) (required for user stories), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/widget-loader.md](./contracts/widget-loader.md)

**Tests**: REQUIRED. The contract document explicitly maps clauses C1–C8 to vitest test names; SC-004 requires verifiable enforcement of the syntax baseline; FR-008/FR-009 require behavior testable in jsdom. Tests come before the implementation edits they cover.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

**Owner**: All tasks are Amer-owned (Phase 7 — Widget). No tenant-isolation, RLS, guardrail, or modelserver changes — no cross-owner review required by the constitution for this feature.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)
- Include exact file paths in descriptions

## Path Conventions

- Loader source: `frontend/widget/public/widget.js`
- Host test page: `frontend/widget/public/host-test.html`
- Build config: `frontend/widget/vite.config.ts`
- Tests: `frontend/widget/src/__tests__/loader.test.ts`
- Test helper (new): `frontend/widget/src/__tests__/loader-harness.ts`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: One-time scaffolding shared by every user story.

- [X] T001 [P] Create [frontend/widget/vite.config.ts](../../frontend/widget/vite.config.ts) with `build.target: 'es2019'`, no app-level changes beyond locking the build target. Add the file header `// Owner: Amer` per project convention.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Test harness all user-story tests depend on.

**⚠️ CRITICAL**: No US test task can begin until T003 is complete.

- [X] T003 Create test harness [frontend/widget/src/__tests__/loader-harness.ts](../../frontend/widget/src/__tests__/loader-harness.ts) that exports `evaluateLoader({ widgetId, backendUrl, scriptSrc, mountBody = true })`. The harness (a) reads `frontend/widget/public/widget.js` from disk via `fs.readFileSync` so tests exercise the shipping file, (b) builds a `<script>` element in jsdom with the requested `src` and `data-*` attributes, (c) sets `document.currentScript` via `Object.defineProperty`, (d) optionally removes `document.body` to simulate the late-mount case, and (e) executes the loader source by `new Function(src)()`. Returns the jsdom `document` and a `consoleErrorSpy`.

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 — Tenant embeds loader on production website (Priority: P1) 🎯 MVP

**Goal**: A tenant can paste the embed snippet on any site, configure the backend via `data-backend-url` (defaulting to the script's own origin), and see exactly one hardened iframe mount.

**Independent Test**: Open a host page that loads the loader with `data-widget-id` and explicit `data-backend-url`. Confirm one iframe is mounted, the iframe `src` uses the configured backend, and the iframe carries the required `sandbox`/`referrerpolicy`/`title` attributes.

### Tests for User Story 1 (write first, must fail before T009 edits)

- [X] T004 [P] [US1] In [frontend/widget/src/__tests__/loader.test.ts](../../frontend/widget/src/__tests__/loader.test.ts), add test `reads data-backend-url from the script tag` — asserts the mounted iframe `src` starts with the value of `data-backend-url` (contract C1, FR-001).
- [X] T005 [P] [US1] Add test `defaults backend to script tag origin when data-backend-url is absent` — sets `scriptSrc = 'https://platform.example/widget.js'`, omits `data-backend-url`, asserts iframe `src` starts with `https://platform.example` (C1, FR-002).
- [X] T006 [P] [US1] Add test `loader source contains no hardcoded localhost or :5173` — reads `public/widget.js` and asserts the source does not match `/localhost|:5173|127\.0\.0\.1/` (FR-003, SC-006).
- [X] T007 [P] [US1] Add test `applies hardened iframe attributes` — asserts iframe has `title="Concierge chat widget"`, `referrerpolicy="no-referrer-when-downgrade"`, and a `sandbox` attribute whose tokens (split by whitespace) are exactly the set `{allow-scripts, allow-same-origin, allow-forms}` — no more, no fewer (C3, FR-004/005/006).
- [X] T008 [P] [US1] Add test `iframe src encodes widget_id` — asserts iframe `src` ends with `?widget_id=<encodeURIComponent(widgetId)>` for a widget id containing special characters (contract C2).

### Implementation for User Story 1

- [X] T009 [US1] Inspect [frontend/widget/public/widget.js](../../frontend/widget/public/widget.js) against tests T004–T008. The existing loader (from feature 001) already satisfies these — confirm no edit is needed and the tests pass against the current source. If any test fails, fix the minimal piece in `widget.js` to match. Do not introduce abstractions.

**Checkpoint**: US1 fully functional and testable. MVP can ship after this story alone.

---

## Phase 4: User Story 2 — Loader safe to include twice (Priority: P2)

**Goal**: Two `<script>` tags with the same `data-widget-id` mount exactly one iframe; two tags with different ids mount two iframes.

**Independent Test**: Inject the loader twice with `widgetId="w_demo"`. The DOM contains exactly one iframe with `data-concierge-widget-id="w_demo"`. Inject again with `widgetId="w_other"`. The DOM now contains two iframes, one per id.

### Tests for User Story 2

- [X] T010 [P] [US2] In `loader.test.ts`, add test `is idempotent for the same widget id` — calls `evaluateLoader` twice with identical `widgetId`, asserts the document contains exactly one `iframe[data-concierge-widget-id="w_demo"]` and no errors logged (C2, FR-007).
- [X] T011 [P] [US2] Add test `mounts two iframes for two different widget ids` — calls `evaluateLoader` with `widgetId="w_a"` then `widgetId="w_b"` against the same jsdom document, asserts two distinct iframes exist with the correct `data-concierge-widget-id` values (FR-013).

### Implementation for User Story 2

- [X] T012 [US2] Verify the existing idempotency guard in [frontend/widget/public/widget.js](../../frontend/widget/public/widget.js) (the `document.querySelector('iframe[data-concierge-widget-id="…"]')` check) makes T010 and T011 pass without modification. If T011 fails because the harness reuses the document and the second invocation hits a stale `currentScript`, update the harness in T003 to support repeated invocations on one document — do not change the loader.

**Checkpoint**: US1 + US2 work independently.

---

## Phase 5: User Story 3 — Loader fails soft when misconfigured (Priority: P2)

**Goal**: Missing/empty `data-widget-id`, missing `currentScript`, or any unexpected DOM error produces exactly one `console.error` and zero iframes — and zero exceptions propagated to the host page.

**Independent Test**: Run the loader with no `data-widget-id` attribute. Inspect: zero iframes, exactly one `console.error`, no unhandled error on the jsdom window.

### Tests for User Story 3

- [X] T013 [P] [US3] In `loader.test.ts`, add test `logs one console.error and does not throw when data-widget-id is missing` — omits the attribute entirely, asserts `consoleErrorSpy.mock.calls.length === 1`, zero iframes, and the `evaluateLoader` call did not throw (FR-008, FR-009).
- [X] T014 [P] [US3] Add test `logs one console.error and does not throw when data-widget-id is empty` — sets `data-widget-id=""`, then a separate case `data-widget-id="   "` (whitespace), asserts the same outcome as T013 (FR-008, edge: empty-after-trim).
- [X] T015 [P] [US3] Add test `does not throw when currentScript is null` — has the harness skip the `defineProperty` step so `document.currentScript` is null, asserts the loader returns without throwing and without mounting an iframe (contract C4, FR-009).
- [X] T016 [P] [US3] Add test `defers mount when document.body is not yet present` — calls `evaluateLoader` with `mountBody: false`, asserts no iframe yet, then **adds `document.body` to the document**, then dispatches `DOMContentLoaded` on the document, then asserts exactly one iframe exists. Asserts no exception was thrown across both phases (contract C5, edge case from spec). The explicit body-add step is required so the test exercises the **late-mount path**, not the fail-soft `appendChild` failure.

### Implementation for User Story 3

- [X] T017 [US3] Edit [frontend/widget/public/widget.js](../../frontend/widget/public/widget.js) to wrap the IIFE body in a single top-level `try/catch`. On any caught exception, call `console.error("[concierge] widget loader aborted:", err)` exactly once and return. Keep the existing in-line `console.error` for the missing-widget-id case; do not double-log. Per Principle VII, do not add per-step defensive checks.
- [X] T018 [US3] In the same file, add a body-not-ready guard at the top of the mount logic: `if (!document.body) { document.addEventListener("DOMContentLoaded", mount, { once: true }); return; }` — where `mount` is the existing iframe-creation code factored into a local function. The factoring is the minimum needed; do not generalize further.
- [X] T019 [US3] In the same file, trim the `widgetId` read with `.trim()` and treat an empty string as missing, so `data-widget-id=""` and `data-widget-id="   "` both fail soft via the existing console.error path (FR-008, T014).
- [X] T029 [P] [US3] In [frontend/widget/src/__tests__/loader.test.ts](../../frontend/widget/src/__tests__/loader.test.ts), add test `loader does not touch localStorage, sessionStorage, or document.cookie` — spies on `localStorage.setItem`, `localStorage.getItem`, `sessionStorage.setItem`, `sessionStorage.getItem`, and the `document.cookie` setter; runs `evaluateLoader` with valid inputs **and** with the missing-widget-id fail-soft path; asserts zero calls to any spy across both runs. Additionally, read `frontend/widget/public/widget.js` from disk and assert the source does not match `/localStorage|sessionStorage|document\.cookie/` — guards against future code that *would* touch storage even if a runtime test happened to miss the branch. Closes contract C7, FR-014, and constitution Principle IV (Defense-in-Depth Auth — widget tokens stay in iframe memory, the loader never sees the host page's storage).

**Checkpoint**: US1 + US2 + US3 work independently. The loader is now safe under all spec-defined misconfiguration cases and verifiably abstains from host-page storage.

---

## Phase 6: User Story 4 — Developer one-click local sanity-check (Priority: P3)

**Goal**: A checked-in host test page lets any developer pull the branch, run `npm run dev`, open one URL, and see the widget mounted.

**Independent Test**: After `npm run dev` from `frontend/widget/`, open `http://localhost:5173/host-test.html`. A widget iframe appears in the bottom-right; DevTools shows zero loader-emitted errors; the iframe `src` includes `widget_id=w_demo`.

### Implementation for User Story 4

- [X] T020 [US4] Create [frontend/widget/public/host-test.html](../../frontend/widget/public/host-test.html). Minimal HTML5 doc with `<title>Concierge widget host test</title>`, a short `<h1>` and `<p>` explaining the page's purpose, and the loader embed: `<script src="/widget.js" data-widget-id="w_demo" data-backend-url="http://localhost:5173" async></script>`. No CSS framework, no JS framework. File starts with an HTML comment `<!-- Owner: Amer -->`.
- [X] T021 [US4] Add a vitest assertion `host-test.html embeds the loader with a known widget id` in `loader.test.ts` that reads `public/host-test.html` from disk and asserts it contains a `<script>` tag with `data-widget-id="w_demo"` and `src="/widget.js"`. This prevents the file from silently drifting out of sync with the embed snippet documented in [quickstart.md](./quickstart.md).

**Checkpoint**: US4 deliverable shipped and locked against regression.

---

## Phase 7: User Story 5 — ES2019 language baseline locked in (Priority: P3)

**Goal**: The production build target is committed in `vite.config.ts`, and the loader source contains no post-ES2019 syntax tokens that a developer might add by reflex.

**Independent Test**: Inspect `vite.config.ts` for `build.target: 'es2019'`. Inspect `dist/widget.js` after `npm run build` and confirm it is byte-identical to `public/widget.js`. Run the syntax-token vitest case and confirm it passes.

### Tests for User Story 5

- [X] T022 [P] [US5] In `loader.test.ts`, add test `loader source contains no post-ES2019 syntax tokens` — reads `public/widget.js`, asserts the source does not match `/(\?\?|\?\.|\bawait\s+|^\s*#[a-zA-Z_])/m` (contract C8, R3, SC-004). Quote a comment line in the test that lists the forbidden tokens so the regex stays auditable.
- [X] T023 [P] [US5] Add test `loader contains no import statements` — asserts `public/widget.js` does not match `/^\s*import\s|^\s*from\s+['"]/m` (contract C8 — single-file requirement, FR-012).

### Implementation for User Story 5

- [X] T024 [US5] Verify [frontend/widget/vite.config.ts](../../frontend/widget/vite.config.ts) (created in T001) sets `build.target: 'es2019'`. Add a one-line comment above the option: `// ES2019 baseline locked per specs/003-widget-loader-hardening (FR-011, SC-004).`
- [X] T025 [US5] Run `npm run build` from `frontend/widget/` and verify `dist/widget.js` is byte-identical to `public/widget.js`. If Vite has inserted any modification (it should not — `public/` is a passthrough), document the discrepancy in `DECISIONS.md` and adjust the build accordingly.

**Checkpoint**: All five user stories independently functional.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, manual validation, decision logging.

- [X] T026 [P] Run the quickstart end-to-end per [quickstart.md](./quickstart.md) sections 1–4. Confirm `npm test` passes, the host-test page mounts the widget against `http://localhost:5173`, `npm run build` produces a byte-identical `dist/widget.js`, and the post-ES2019 grep returns nothing.
- [X] T027 [P] Add a one-line entry to [DECISIONS.md](../../DECISIONS.md): "003 widget loader hardening — chose to keep `public/widget.js` hand-authored at ES2019 syntax rather than bundle it through Vite. Rationale in `specs/003-widget-loader-hardening/research.md` R1." Date the entry 2026-05-27.
- [X] T028 Walk the pre-merge checklist in [CLAUDE.md](../../CLAUDE.md) §Pre-Merge Checklist for this feature: zero new tables, zero hardcoded secrets, no `torch`/`transformers`, no PII in logs, tests cover happy + fail-soft paths, no platform guardrail weakened. Note in the PR description which items are N/A and why (this feature is frontend-only).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001)**: No dependencies — can start immediately.
- **Foundational (T003)**: Depends on Setup. **Blocks all US test tasks.**
- **US1 (T004–T009)**: Depends on T003.
- **US2 (T010–T012)**: Depends on T003. Independent of US1.
- **US3 (T013–T019, T029)**: Depends on T003. Independent of US1 and US2 (different test cases, but T017–T019 edit the same file as T009 — see below).
- **US4 (T020–T021)**: Depends on T003 only for the test (T021). T020 itself depends on nothing.
- **US5 (T022–T025)**: Depends on T001 (`vite.config.ts`) and T003.
- **Polish (T026–T028)**: Depends on US1–US5 complete.

### Within-Phase Dependencies

- **Within US1**: T004–T008 are all `[P]` (different tests in the same file but writeable in isolation). T009 runs after them.
- **Within US3**: T017, T018, T019 all edit `public/widget.js` — they are **NOT** `[P]` with each other; run them sequentially in the listed order. T013–T016 and T029 are `[P]` (test-only).
- **US1's T009 and US3's T017–T019** both touch `public/widget.js`. Run US1's T009 first (it's a no-op verification), then US3's edits. If you parallelize US1 and US3 across two developers, agree on a merge order — recommended: finish US1 (T009 is verify-only) before US3 implementation starts.
- **US2's T012** is verify-only against the same file; safe to run anywhere after T010–T011 pass.

### Parallel Opportunities

- T004 ∥ T005 ∥ T006 ∥ T007 ∥ T008 (all add separate `it(...)` cases to the same test file — coordinate via separate commits per test if doing in parallel).
- T010 ∥ T011 (test-only).
- T013 ∥ T014 ∥ T015 ∥ T016 ∥ T029 (test-only).
- T020 ∥ T021 (different files).
- T022 ∥ T023 (different test cases).
- T026 ∥ T027 (different files).
- After T003 completes, US1 ∥ US2 ∥ US3 ∥ US4 ∥ US5 can be staffed in parallel across developers, with the same-file caveat above.

---

## Parallel Example: User Story 3 tests

```text
# Launch all four US3 fail-soft tests in parallel — they all add new `it(...)` blocks
# to loader.test.ts but cover independent scenarios:
Task: T013 — Test: missing data-widget-id logs one error, no throw
Task: T014 — Test: empty / whitespace data-widget-id logs one error, no throw
Task: T015 — Test: null currentScript does not throw
Task: T016 — Test: late-body case waits for DOMContentLoaded
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1 (T001–T002) and Phase 2 (T003).
2. Complete US1 (T004–T009).
3. **STOP and VALIDATE**: the loader passes contract clauses C1–C3 and C8's "no hardcoded host" assertion. A tenant can paste the snippet on any site and the widget mounts hardened.
4. This is shippable as MVP for the feature.

### Incremental Delivery

1. Setup + Foundational ready.
2. US1 → demo to team → ship.
3. US2 → demo idempotency on a tag-managed test page → ship.
4. US3 → demo fail-soft in DevTools (delete the `data-widget-id` attribute live) → ship.
5. US4 → host-test.html lands; team adopts it in their dev loop → ship.
6. US5 → build target locked + syntax check passes → ship.

### Single-Developer Strategy (likely for this slice — Amer-owned only)

Sequential is fine: T001 → T003 → US1 → US2 → US3 → US4 → US5 → Polish. The whole feature is small enough that the parallelism above is more useful as a review-grouping tool than as a coordination strategy. Estimated total effort: half a day to a full day of focused work.

---

## Notes

- `[P]` tasks = different files OR independent test cases that can be written without merge conflicts.
- Every implementation task in US3 cites the contract clause and FR it satisfies; reviewers can cross-reference [contracts/widget-loader.md](./contracts/widget-loader.md) directly.
- Per the constitution (§Development Workflow), this feature is in the "risky" category because it touches widget auth surface; **run `/speckit-analyze` before `/speckit-implement`**.
- Verify each test fails before its implementation task lands (T009, T017–T019, T024). T009 is a verification-only step — if the existing widget.js already passes, the test was already satisfied (which is the expected outcome for US1 given feature 001's prior work).
- Commit after each user-story checkpoint to keep PRs reviewable.
- No backend code, no DB migrations, no agent tool changes — keep the scope tight per the spec's explicit out-of-scope clause.
