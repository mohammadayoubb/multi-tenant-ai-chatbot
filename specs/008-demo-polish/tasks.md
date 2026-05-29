---

description: "Task list for feature 008-demo-polish"
---

# Tasks: Demo Polish

**Input**: Design documents from `/specs/008-demo-polish/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/lean-image-audit-cli.md](contracts/lean-image-audit-cli.md), [quickstart.md](quickstart.md)

**Tests**: This feature is documentation + CI hardening. The "tests" for each story are manual verification steps already documented in [quickstart.md](quickstart.md) and the lean-check contract's §8 Test Plan. No new pytest suites are added under this spec.

**Organization**: Tasks are grouped by user story per spec.md priorities. P1 stories (US1 README, US2 runbook, US3 lean-check) form the MVP. US4 (compose race) is P2. US5 (screenshots) is P3 and lives entirely outside the repo.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4, US5)
- Include exact file paths in descriptions

## Path Conventions

Repo root: `G:\multi-tenant-ai-chatbot`. All paths below are repo-root-relative.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm prerequisites and feature-directory state.

- [X] T001 Confirm working tree is on branch `008-demo-polish` and the spec/plan artifacts in `specs/008-demo-polish/` are committed-or-staged before edits begin (no code yet — verification only).
- [X] T002 [P] Confirm Docker, `docker compose`, `make`, and `python` 3.11 are on PATH for the contributor running the work (prerequisite check for the lean-check and the runbook walk-through).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: A single shared artifact (the Makefile) and a single shared sanity check that every story below relies on.

**⚠️ CRITICAL**: T003 must complete before T011/T012 (US3 needs the Makefile target). T004 may run any time before US2 verification (T009).

- [X] T003 Create `Makefile` at repo root with a single target `lean-image-audit:` whose recipe invokes `bash scripts/check_lean_images.sh`. Add a `.PHONY: lean-image-audit` declaration. Owner header `# Owner: Amer` on line 1.
- [X] T004 [P] Cold-start sanity: run `docker compose down -v && docker compose up --build --wait` once on the current `main` to confirm the stack is healthy before any compose edit. Record current `docker compose ps` output in scratch notes (not committed); this is the baseline for US4's race-fix verification.

**Checkpoint**: Makefile exists; baseline stack-up is known to work. US1, US2, US3, US4 may now proceed in parallel by file.

---

## Phase 3: User Story 1 - README "Embed the widget" section (Priority: P1) 🎯 MVP part 1

**Goal**: A reader of `README.md` can find a copy-pasteable widget embed snippet showing `data-widget-id` and `data-backend-url`.

**Independent Test**: Open `README.md`; find a section titled `## Embed the widget`; copy the snippet into a blank HTML page on `http://localhost:5173/host-test.html`-equivalent allowlisted origin; widget mounts and chat works (FR-001, FR-002, SC-001).

### Implementation for User Story 1

- [X] T005 [US1] Edit [README.md](../../README.md): insert a new `## Embed the widget` section immediately after the existing `## Run Locally` section (before `## Required Docs`). The section contains: one preface sentence about the allowlist requirement, a fenced ```html``` block with exactly one `<script>` tag carrying `src="https://YOUR-CONCIERGE-HOST/widget.js"`, `data-widget-id="YOUR_WIDGET_ID"`, `data-backend-url="https://YOUR-CONCIERGE-HOST"`, and a two-sentence paragraph explaining where `YOUR_WIDGET_ID` is obtained (admin UI) and that the loading page's origin must be on the tenant allowlist. Wording follows [research.md](research.md) §R7.
- [X] T006 [US1] Manually verify the snippet works by pasting it into `frontend/widget/dist/host-test.html`-style page (or by editing the existing host-test page in a scratch copy) and loading `http://localhost:5173/<that-page>` against a running stack. Confirm widget mounts and a chat reply comes back. No file change here — this is the FR-002 verification.

**Checkpoint**: README has an embed section that a non-contributor can use without reading any other file.

---

## Phase 4: User Story 2 - RUNBOOK Demo Flow + smoke test line (Priority: P1) 🎯 MVP part 2

**Goal**: A reviewer following `RUNBOOK.md` top-to-bottom on a clean clone reaches a healthy local stack and runs `pytest tests/smoke/` successfully, with zero undocumented manual edits.

**Independent Test**: `git clone` to a fresh directory; follow `RUNBOOK.md` from step 1 through step 9; run `pytest tests/smoke/`. All commands succeed without edits. Wall-clock under 15 minutes (FR-003, FR-004, FR-005, SC-002).

### Implementation for User Story 2

- [X] T007 [US2] Edit [RUNBOOK.md](../../RUNBOOK.md): replace the existing `## Demo Flow` section (lines 35–45 in the current file — the nine bare bullets) with nine numbered steps, each carrying the concrete command/UI action and the observable success signal per [research.md](research.md) §R4. Owner header `# Owner: Amer` on line 1 is preserved.
- [X] T008 [US2] In the same edit to [RUNBOOK.md](../../RUNBOOK.md), append a new `## Run smoke test` subsection immediately after the Demo Flow containing the single line `pytest tests/smoke/` (and one explanatory sentence: "Exits 0 against a running local stack."). Reference [scripts/smoke_check.py](../../scripts/smoke_check.py) as the CI-equivalent wrapper in a parenthetical note.
- [X] T009 [US2] Walk the runbook on a clean clone end-to-end: `git clone` to a new directory, follow steps 1–9, then run `pytest tests/smoke/`. Any step that fails or required an undocumented manual fix-up is updated in [RUNBOOK.md](../../RUNBOOK.md) immediately. Repeat until a clean walk-through passes with zero edits during the walk. Time the walk; record the elapsed minutes in scratch notes for SC-002 confirmation.

**Checkpoint**: Runbook is the source of truth for the demo; smoke test line works.

---

## Phase 5: User Story 3 - Lean-image audit (Priority: P1) 🎯 MVP part 3

**Goal**: A documented, machine-verifiable check that `modelserver` and `guardrails` images contain neither `torch` nor `transformers`. The check is wired into CI so a violating PR is blocked (FR-006, FR-007, FR-008, SC-004).

**Independent Test**: Run `docker compose build modelserver guardrails && make lean-image-audit` locally; exit 0 with `lean-image-audit: clean (2 images, 2 regexes)`. Temporarily add `RUN pip install torch` to the modelserver stage in Dockerfile; re-run; exit 1 with stderr naming image and package. Revert Dockerfile. (Test plan from [contracts/lean-image-audit-cli.md](contracts/lean-image-audit-cli.md) §8.)

### Implementation for User Story 3

- [X] T010 [P] [US3] Create [scripts/check_lean_images.sh](../../scripts/check_lean_images.sh) implementing the full contract in [contracts/lean-image-audit-cli.md](contracts/lean-image-audit-cli.md). The script: parses `--image` and `--package` flags (repeatable), defaults to images `multi-tenant-ai-chatbot-modelserver` / `multi-tenant-ai-chatbot-guardrails` and regexes `^torch([=\s]\|$)` / `^transformers([=\s]\|$)` (case-insensitive), runs `docker run --rm --entrypoint pip <image> list --format=freeze` per image, scans output for matches, prints success/failure per §6 output format, exits per §5 exit-code table. Owner header `# Owner: Amer` on line 1. Make executable (`chmod +x`).
- [X] T011 [US3] (Depends on T003 and T010.) Verify locally: `docker compose build modelserver guardrails && make lean-image-audit`. Confirm exit 0 and `lean-image-audit: clean (2 images, 2 regexes)` on stdout. If exit non-zero on current `main`, investigate — the current Dockerfile is supposed to be clean per Constitution Principle V, so any failure here is a pre-existing constitutional violation that must be surfaced before this PR can merge.
- [X] T012 [US3] (Depends on T011.) Edit [.github/workflows/ci.yml](../../.github/workflows/ci.yml): insert a new job named `lean-image-audit` between `lint-test-build` and the eval jobs. The job declares `needs: lint-test-build`, runs on `ubuntu-latest`, on all events (no `if:` gate), with three steps: `actions/checkout@v4`, `docker compose build modelserver guardrails`, and `make lean-image-audit`. Do **not** add `needs: lean-image-audit` to the existing eval or smoke-e2e jobs (per [research.md](research.md) §R3 — eval jobs surface their own status checks independently).
- [X] T013 [US3] (Depends on T012.) Failure-path verification (NOT committed): add `RUN pip install torch` temporarily to the `modelserver` stage of [Dockerfile](../../Dockerfile), run `docker compose build modelserver && make lean-image-audit`, confirm exit 1 with stderr containing `multi-tenant-ai-chatbot-modelserver: forbidden package torch`. Revert the Dockerfile change immediately. Record verification result in the PR description (e.g., "Failure path verified locally on 2026-05-28: exit 1, stderr names image and package.").

**Checkpoint**: Constitutional gate is automated. A future PR that introduces `torch` or `transformers` into a serving image is blocked by CI.

---

## Phase 6: User Story 4 - Compose healthcheck pass (Priority: P2)

**Goal**: The stack reaches healthy state three consecutive cold starts; no `depends_on` chain races (FR-009, FR-010, FR-011, SC-003).

**Independent Test**: Run the three-cycle audit from [quickstart.md](quickstart.md) §4 — `1..3 | ForEach-Object { docker compose down -v; docker compose up --build --wait; docker compose ps }`. All three cycles show `api`, `modelserver`, `guardrails` as `healthy`. Admin service starts only after `api` is healthy (visible in `docker compose ps` ordering / event log).

### Implementation for User Story 4

- [X] T014 [US4] Edit [docker-compose.yml](../../docker-compose.yml): convert the `admin` service's `depends_on` from short-form (`- api`) to the long-form map with `api: condition: service_healthy`. This is the only compose change identified by the audit in [research.md](research.md) §R5; do not add speculative healthchecks to `admin`, `widget`, or `minio` (nothing depends on them being healthy).
- [X] T015 [US4] Re-run the three-cycle cold-start audit from [quickstart.md](quickstart.md) §4. Capture `docker compose ps` output after each `up --wait` and confirm `api`, `modelserver`, `guardrails` are `healthy` in 3/3 runs. If any cycle fails, do NOT broaden the fix — diagnose the specific failure and address it (a real race), then re-run. Record run outcomes in scratch notes for SC-003 confirmation.

**Checkpoint**: Cold-start race eliminated; demo stack starts cleanly every time.

---

## Phase 7: User Story 5 - Demo screenshots (Priority: P3, out-of-repo)

**Goal**: Three screenshots exist in the presenter's local space (admin audit-log rejection, widget mid-chat, CI gates green). They are NOT committed (FR-012, SC-005).

**Independent Test**: Each screenshot can be produced on demand from a running local stack and the latest green CI run; total capture time under 5 minutes (SC-005).

### Implementation for User Story 5

- [ ] T016 [US5] With the stack running and tenants seeded (RUNBOOK steps 1–2), trigger a cross-tenant attempt from a Tenant A widget session, open the admin UI's tenant audit-log page (`http://localhost:8501`), and capture a screenshot of the rejection entry. Save outside the repo (e.g., the team writeup folder). Before saving, confirm the captured frame shows seeded demo data only — no real tenant data, no live tokens, no secrets visible (data-model.md E5). **Do not `git add`.**
- [ ] T017 [P] [US5] With the stack running, open `http://localhost:5173/host-test.html`, exchange at least two turns with the agent, and capture a screenshot of the mid-chat state. Before saving, confirm the captured frame shows seeded demo content only — no real tenant data, no JWT or session token visible in DevTools/URL, no secrets (data-model.md E5). Save outside the repo. **Do not `git add`.**
- [ ] T018 [P] [US5] After the CI run on this branch completes, open the GitHub Actions run page for the latest green push, and capture a screenshot of all gate status checks green (`lint-test-build`, `lean-image-audit`, `classifier-eval`, `rag-eval`, `agent-tool-eval`, `red-team`, `redaction-eval`, `smoke-e2e`). Before saving, confirm the captured frame shows no private repo metadata, no environment secrets, and no PR contents beyond the public check list (data-model.md E5). Save outside the repo. **Do not `git add`.**

**Checkpoint**: Presenter has three demo aids ready, none of them touching the repo.

---

## Phase 8: Polish & Cross-Cutting

**Purpose**: Tie loose ends and confirm scope discipline.

- [X] T019 Append an entry to [DECISIONS.md](../../DECISIONS.md) recording the lean-image-audit addition. Adding a CI job is "changing Docker/CI behavior" per constitution §Development Workflow, which lists it as a major decision that MUST be recorded. Capture at minimum: (a) the job is added between `lint-test-build` and the eval jobs per [research.md](research.md) §R3, (b) the audit uses `docker run --rm --entrypoint pip <image> list --format=freeze` per [research.md](research.md) §R1, and (c) the contract lives at [contracts/lean-image-audit-cli.md](contracts/lean-image-audit-cli.md). Also note the `admin → api` compose `depends_on` long-form change (T014) since that is a behavior change in `docker-compose.yml` (Amer's protected file).
- [X] T020 Verify scope discipline (FR-013, FR-014, SC-006): run `git diff --name-only origin/main...HEAD` from the branch and confirm the changed file set matches the expected list in [quickstart.md](quickstart.md) §6 — `README.md`, `RUNBOOK.md`, `docker-compose.yml`, `Makefile`, `scripts/check_lean_images.sh`, `.github/workflows/ci.yml`, optional `DECISIONS.md`, and the new files under `specs/008-demo-polish/`. Any extra file is a scope leak and must be removed before opening the PR.
- [X] T021 Pre-merge checklist walk (per [CLAUDE.md](../../CLAUDE.md) §Pre-Merge Checklist): tick the boxes that apply to this PR (no new tables, no hardcoded secrets, no `torch`/`transformers` in serving code, no PII in logs, CI green, no protected-file changes beyond `docker-compose.yml` + `.github/workflows/ci.yml` which are scoped to this feature). The tenant-isolation, RLS, auth, and migration boxes are N/A and should be marked as such in the PR description rather than mechanically ticked.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies; start immediately. T002 is purely a prerequisite check.
- **Phase 2 (Foundational)**: T003 (Makefile) blocks T011 in US3. T004 (baseline cold-start) blocks T015 in US4. No other story blocks on Phase 2.
- **Phase 3 (US1)**, **Phase 4 (US2)**, **Phase 5 (US3)**, **Phase 6 (US4)**: independent of each other; can proceed in parallel by file.
- **Phase 7 (US5)**: depends on Phases 4 and 6 being complete (need a running stack and CI green to capture).
- **Phase 8 (Polish)**: depends on all preceding phases.

### User Story Dependencies

- **US1 (README)** — touches only `README.md`. No story dependencies.
- **US2 (RUNBOOK)** — touches only `RUNBOOK.md`. No story dependencies. T009's clean-clone walk benefits if US4 (T014) is already done (admin race is gone), but is not blocked by it.
- **US3 (Lean audit)** — touches `scripts/check_lean_images.sh`, `Makefile` (T003 in Foundational), and `.github/workflows/ci.yml`. Depends only on T003 from Phase 2.
- **US4 (Compose race)** — touches only `docker-compose.yml`. No story dependencies. Benefits from T004 baseline.
- **US5 (Screenshots)** — out-of-repo. Needs US4 healthy stack (T015) and US3 CI job green (T012, T013) to capture screenshot #3.

### Within Each User Story

- US1: T005 (edit) → T006 (manual verify).
- US2: T007 (Demo Flow rewrite) and T008 (smoke line) can be one atomic edit; T009 (clean-clone walk) follows.
- US3: T010 (script) and T003 (Makefile, Phase 2) can be parallel; T011 (local verify) follows both; T012 (CI wiring) follows T011; T013 (failure-path verify) follows T012.
- US4: T014 (edit) → T015 (verify).
- US5: T016, T017, T018 independent.

### Parallel Opportunities

- T002 || T001 in Phase 1.
- T003 || T004 in Phase 2 (different files, independent).
- T010 || T005 || T007/T008 || T014 once Phase 2 is done — four developers (or one developer working file-by-file) can knock out US1, US2, US3-script, and US4-edit in parallel.
- T017 || T018 in Phase 7 (independent capture targets).

---

## Parallel Example: MVP P1 stories after Phase 2

```text
# After T003 (Makefile) and T004 (baseline cold-start) land:
Task: T005 [US1] Edit README.md — add "Embed the widget" section
Task: T007 [US2] Edit RUNBOOK.md — rewrite Demo Flow as 9 numbered steps
Task: T010 [US3] Create scripts/check_lean_images.sh per contract
Task: T014 [US4] Edit docker-compose.yml — admin->api long-form depends_on
```

Four file-disjoint edits. They can land as one PR or as four sequential commits on this branch.

---

## Implementation Strategy

### MVP First (P1 stories: US1 + US2 + US3)

1. Phase 1 (T001–T002) — 5 minutes of prerequisite checks.
2. Phase 2 (T003–T004) — Makefile + baseline cold-start, 10 minutes.
3. Phase 3 (US1, T005–T006) — README edit + browser verify, 15 minutes.
4. Phase 4 (US2, T007–T009) — runbook rewrite + clean-clone walk, 30–45 minutes (the walk is wall-clock-bound by the stack cold-start).
5. Phase 5 (US3, T010–T013) — lean-check script + CI wiring + both verifications, 45–60 minutes.
6. **STOP and VALIDATE**: open a draft PR; confirm the new `lean-image-audit` CI job runs green; confirm lint/test/build still green.
7. P1 stories are now demo-shippable.

### Incremental Delivery

1. P1 MVP (US1 + US2 + US3) → draft PR → CI green → demo team can already use README, RUNBOOK, and the constitutional gate is live.
2. Add P2 (US4, T014–T015) → re-run the three-cycle cold-start → push to same PR.
3. Capture P3 screenshots (US5, T016–T018) out-of-repo at any time after P2 lands.
4. Phase 8 polish (T019–T021) → scope discipline check → mark PR ready-for-review.

### Parallel Team Strategy

This feature has one owner (Amer) per ownership rules. Parallelism is intra-developer file-by-file rather than across people. Still, the four MVP edits are file-disjoint and can be staged in parallel branches if a reviewer wants to evaluate them as separate commits in the same PR.

---

## Notes

- This feature adds **zero application code**. Every task is doc, shell, Makefile, compose, or CI YAML.
- No new pytest tests are added under this spec. The "tests" are: (a) the manual verifications described per task, (b) the existing `pytest tests/smoke/` suite invoked from the runbook, (c) the CI `lean-image-audit` job itself.
- [P] tasks = different files, no dependencies on incomplete tasks.
- [Story] label maps task to user story for traceability.
- Each story is independently testable per its `Independent Test` line above.
- Commit after each story phase, or after the four MVP file-edits as one commit — both are acceptable for this PR's size.
- Avoid: adding healthchecks to services nothing depends on; adding pytest suites for the lean-check (the contract's §8 is a manual one-shot verification, not a permanent suite); committing any screenshot file.
