---

description: "Task list for feature 006-ci-eval-gates (CI Eval Gates Enforced)"
---

# Tasks: CI Eval Gates Enforced

**Input**: Design documents from `/specs/006-ci-eval-gates/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/eval-cli.md](contracts/eval-cli.md), [contracts/threshold-checker.md](contracts/threshold-checker.md), [quickstart.md](quickstart.md)

**Tests**: Tests are INCLUDED. The plan scope lists `tests/scripts/test_check_threshold.py` and `tests/evals/test_mock_evaluators.py`, and `pytest` is part of the existing CI gate set, so the new helper and mocks must be covered.

**Organization**: Tasks are grouped by the three user stories from spec.md. US1 (block on regression) is the MVP — landing US1 alone delivers the binding-gates value. US2 (artifacts on every run) and US3 (header comment + DECISIONS.md) layer on top.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Different file, no dependency on an incomplete task — can run in parallel
- **[Story]**: User story label (US1, US2, US3) for traceability
- Every task names a concrete file path

## Path Conventions

- Repo root: `g:\multi-tenant-ai-chatbot\` (Windows) — paths shown below are repo-relative POSIX-style for readability
- New eval modules live under `evals/`
- New helper lives under `scripts/`
- New tests live under `tests/scripts/` and `tests/evals/`
- Workflow file: `.github/workflows/ci.yml`
- Decision log: `DECISIONS.md`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the new directories and empty package markers the rest of the feature lives under. No business logic.

- [X] T001 Create new directories `evals/`, `tests/scripts/`, `tests/evals/` at repo root
- [X] T002 [P] Create empty package marker `evals/__init__.py` (one line: `# Owner: Amer`)
- [X] T003 [P] Create empty package marker `tests/scripts/__init__.py`
- [X] T004 [P] Create empty package marker `tests/evals/__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the two pieces every user story depends on — the threshold-checker helper and its unit tests — plus an end-to-end contract sanity check. Without these, no CI job can pass or fail meaningfully, so this phase blocks every user story.

**⚠️ CRITICAL**: User-story phases (3, 4, 5) cannot begin until Phase 2 is green.

- [X] T005 Implement `scripts/check_threshold.py` per [contracts/threshold-checker.md](contracts/threshold-checker.md): argparse CLI with `--gate`, `--metric`, `--json`, optional `--thresholds`; loads YAML; loads JSON; infers `min`/`eq` direction from metric-key suffix (`*_min` vs `required_*`); strips suffix/prefix to derive the JSON `<metric_short>` key; compares; exits 0 with PASS-line on stdout or 1 with FAIL/ERROR line on stderr; handles all 8 error cases listed in T-spec §T4. File header: `# Owner: Amer`.
- [X] T006 [P] Write `tests/scripts/test_check_threshold.py` covering: pass case for each direction (`min`, `eq`), fail case for each direction, threshold file missing, threshold key missing, JSON file missing, malformed YAML, malformed JSON, missing metric key in JSON, non-numeric metric value, unrecognized key shape, **and two `_mock`-ignored cases (FR-006c): a JSON with `_mock: true` and a passing metric → exit 0; the same JSON shape with a failing metric → exit 1; both demonstrate the `_mock` field has no effect on outcome**. Use `subprocess.run` so exit code and stdio are tested verbatim. Aim ≥12 test cases. (16 tests passing.)
- [X] T007 Confirm the test approach in T006 is subprocess-only — no `scripts/__init__.py` should be created in this PR (the helper is invoked via `python scripts/check_threshold.py …`, never imported). If T006 was drafted with an `import` style instead, refactor it to subprocess before merging.

**Checkpoint**: `pytest tests/scripts/test_check_threshold.py -v` is green locally. The helper is ready to be invoked by any eval job.

---

## Phase 3: User Story 1 — Block a PR that regresses a quality gate (Priority: P1) 🎯 MVP

**Goal**: Five new CI jobs (`classifier-eval`, `rag-eval`, `agent-tool-eval`, `red-team`, `redaction-eval`) run after `lint-test-build`, each invokes its eval CLI, pipes the JSON through `scripts/check_threshold.py`, and fails the workflow on threshold miss. Mocks ship in this PR so the jobs are immediately green; real owners replace mocks later without further CI changes.

**Independent Test**: From `quickstart.md` §2 — write a deliberately-bad JSON, run `check_threshold.py`, confirm exit 1 and the `FAIL <gate>.<metric>: measured <m> < min <t>` line. Then push the branch, open a PR against `main`, confirm all five eval checks appear and pass; deliberately edit `evals/classifier.py` to return 0.78, confirm `classifier-eval` job fails on the PR.

### Mock implementations (US1)

- [X] T008 [P] [US1] Implement `evals/classifier.py` per [contracts/eval-cli.md](contracts/eval-cli.md): argparse with `--output <path>`; write `{"metrics": {"macro_f1": 0.80}, "_mock": true}`; print `MOCK EVALUATOR: classifier is not yet implemented — owner: Ayoub` to stderr; exit 0. File header: `# Owner: Ayoub (TEMPORARY MOCK by Amer, 2026-05-27 — replace with real classifier evaluator)`.
- [X] T009 [P] [US1] Implement `evals/rag.py`: write `{"metrics": {"hit_at_5": 0.75, "faithfulness": 0.80}, "_mock": true}`; stderr `MOCK EVALUATOR: rag is not yet implemented — owner: Nasser`; exit 0. File header: `# Owner: Nasser (TEMPORARY MOCK by Amer, 2026-05-27 — replace with real RAG evaluator)`.
- [X] T010 [P] [US1] Implement `evals/agent_tool.py`: write `{"metrics": {"accuracy": 0.90}, "_mock": true}`; stderr `MOCK EVALUATOR: agent_tool is not yet implemented — owner: Nasser`; exit 0. File header: `# Owner: Nasser (TEMPORARY MOCK by Amer, 2026-05-27 — replace with real agent-tool evaluator)`.
- [X] T011 [P] [US1] Implement `evals/red_team.py`: write `{"metrics": {"refusal_rate": 1.0}, "_mock": true}`; stderr `MOCK EVALUATOR: red_team is not yet implemented — owner: Ayoub`; exit 0. File header: `# Owner: Ayoub (TEMPORARY MOCK by Amer, 2026-05-27 — replace with real red-team evaluator)`.
- [X] T012 [P] [US1] Implement `evals/redaction.py`: write `{"metrics": {"secret_leak_count": 0}, "_mock": true}`; stderr `MOCK EVALUATOR: redaction is not yet implemented — owner: Ayoub`; exit 0. File header: `# Owner: Ayoub (TEMPORARY MOCK by Amer, 2026-05-27 — replace with real redaction evaluator)`.

### Mock contract tests (US1)

- [X] T013 [P] [US1] Write `tests/evals/test_mock_evaluators.py` covering all five mocks: for each, run `python -m evals.<gate> --output <tmp>` via `subprocess.run`; assert exit 0, assert the file is valid JSON, assert the required metric key(s) are present and numeric, assert `_mock: true` is present, assert the stderr line matches `^MOCK EVALUATOR: <gate> is not yet implemented — owner: (Ayoub|Nasser)$`. For *threshold-correctness*, assert `measured >= threshold` for `*_min` gates and `measured == threshold` for `required_*` gates — read the threshold from `eval_thresholds.yaml` at test time so the test stays correct if Ayoub later tightens a threshold. One test per gate, plus one parametrized check that every emitted JSON satisfies the threshold by piping through `scripts/check_threshold.py` and asserting exit 0. (20 tests passing.)

### Workflow wiring (US1)

- [X] T014 [US1] Modify `.github/workflows/ci.yml`: add `classifier-eval` job with `needs: lint-test-build`; same Python 3.11 + `uv pip install --system -e ".[dev]"` setup steps; add a step that runs `python -m evals.classifier --output classifier-eval.json`; add a step that runs `python scripts/check_threshold.py --gate classifier --metric macro_f1_min --json classifier-eval.json`. Job-level `if: github.event_name == 'pull_request' || (github.event_name == 'push' && github.ref == 'refs/heads/main')` per R7.
- [X] T015 [US1] In `.github/workflows/ci.yml`: add `rag-eval` job (same shape as T014). Invocation: `python -m evals.rag --output rag-eval.json`. Two threshold-check steps in sequence — `--metric hit_at_5_min` and `--metric faithfulness_min` — against the same JSON file. Both must pass for the job to be green.
- [X] T016 [US1] In `.github/workflows/ci.yml`: add `agent-tool-eval` job (same shape). Invocation: `python -m evals.agent_tool --output agent-tool-eval.json`. Threshold step: `--gate agent_tool_selection --metric accuracy_min`. **Note**: the three names here are intentionally different — `agent_tool_selection` is the gate key in `eval_thresholds.yaml`, `evals.agent_tool` is the Python module path, and `agent-tool-eval` is the CI job name. This is not a typo. See [data-model.md](data-model.md) E1 for the full mapping.
- [X] T017 [US1] In `.github/workflows/ci.yml`: add `red-team` job (same shape). Invocation: `python -m evals.red_team --output red-team-eval.json`. Threshold step: `--gate red_team --metric required_refusal_rate`.
- [X] T018 [US1] In `.github/workflows/ci.yml`: add `redaction-eval` job (same shape). Invocation: `python -m evals.redaction --output redaction-eval.json`. Threshold step: `--gate redaction --metric required_secret_leak_count`.
- [X] T019 [US1] Add a top-of-job dependency cache step shared across all five eval jobs (same pattern as `lint-test-build`): `actions/setup-python@v5` with `cache: pip` keyed on `pyproject.toml`. The five jobs all install identical deps, so cache reuse is correctness-neutral and avoids five cold installs.

**Checkpoint**: A PR push triggers six checks (`lint-test-build` + five eval jobs); all six are green with mocks in place. Deliberately edit a mock to return a sub-threshold value → corresponding eval job fails with the FAIL line clearly visible in the log → PR cannot merge. US1 acceptance scenarios 1–4 from spec.md are exercised end-to-end.

---

## Phase 4: User Story 2 — Reviewer downloads JSON artifacts (Priority: P2)

**Goal**: Each eval job uploads its JSON output as a named workflow artifact regardless of whether the gate passed or failed, so reviewers can debug from the run page.

**Independent Test**: Open any completed CI run page (passing or failing); confirm exactly five artifacts named `classifier-eval-output`, `rag-eval-output`, `agent-tool-eval-output`, `red-team-eval-output`, `redaction-eval-output`. Download one and confirm it contains the JSON the CLI emitted.

- [X] T020 [US2] In `.github/workflows/ci.yml`: add `actions/upload-artifact@v4` step to `classifier-eval` job with `name: classifier-eval-output`, `path: classifier-eval.json`, `if: always()` so the artifact uploads on both pass and fail.
- [X] T021 [US2] In `.github/workflows/ci.yml`: same upload step for `rag-eval` (`name: rag-eval-output`, `path: rag-eval.json`).
- [X] T022 [US2] In `.github/workflows/ci.yml`: same upload step for `agent-tool-eval` (`name: agent-tool-eval-output`, `path: agent-tool-eval.json`).
- [X] T023 [US2] In `.github/workflows/ci.yml`: same upload step for `red-team` (`name: red-team-eval-output`, `path: red-team-eval.json`).
- [X] T024 [US2] In `.github/workflows/ci.yml`: same upload step for `redaction-eval` (`name: redaction-eval-output`, `path: redaction-eval.json`).

**Checkpoint**: A passing run and a deliberately-failed run both expose five downloadable artifacts on the run page. US2 acceptance scenarios 1–2 satisfied. SC-003 (5/5 artifacts every run) achievable.

---

## Phase 5: User Story 3 — Self-documenting workflow + DECISIONS.md entry (Priority: P3)

**Goal**: A new contributor can read the top of `ci.yml` and the new entry in `DECISIONS.md` and understand every enforced gate, its threshold, and its owner without opening any other file.

**Independent Test**: Open `ci.yml` and confirm the header comment lists all five gates with thresholds and owners; open `DECISIONS.md` and confirm Decision 9 documents the same table; cross-reference against `eval_thresholds.yaml` to confirm parity.

- [X] T025 [US3] Prepend a header comment block to `.github/workflows/ci.yml` (above the existing `# Owner: Amer` line) that lists each gate as a markdown-style table inside YAML comments: gate name, threshold key in `eval_thresholds.yaml`, threshold value or required condition, owner, eval-script path. Include a one-line reference to [specs/006-ci-eval-gates/spec.md](specs/006-ci-eval-gates/spec.md) so future readers can follow the trail.
- [X] T026 [US3] Append Decision 9 to `DECISIONS.md` titled `Decision 9 — CI Eval Gates Enforced (Amer, 2026-05-27)`. Follow the Context / Decision / Consequences / References shape used by Decisions 4–8. Include the gate / threshold / owner / eval-script-path table the user explicitly requested. **Include a sub-bullet titled "Known gap — RAG MRR not wired"** explicitly acknowledging that the constitution `## Quality Gates` table lists `RAG MRR ≥ 0.50` as enforced but `eval_thresholds.yaml` has no `mrr_min` key, so this PR does not wire it; closing the gap requires Ayoub to add `rag.mrr_min: 0.50` to `eval_thresholds.yaml` and Nasser to emit `mrr` from `evals/rag.py`, both in follow-up PRs. Cross-reference `specs/006-ci-eval-gates/spec.md` Assumptions, `specs/006-ci-eval-gates/research.md` §R1 and §R8, and the constitution `## Quality Gates`.

**Checkpoint**: `ci.yml` and `DECISIONS.md` both list the same five gates with identical thresholds and owners. US3 acceptance scenarios 1–2 satisfied. SC-004 (contributor can list every gate from the header alone) is verifiable.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final checks, drift prevention, and PR-description authoring before merge.

- [X] T027 [P] Verify SC-005 (no drift between workflow and thresholds): run the inline Python snippet from `quickstart.md` §9 locally; confirm the gate list from `eval_thresholds.yaml` matches the (gate, metric) pairs wired into `ci.yml` (six pairs, because `rag-eval` has two metrics). If drift exists, fix the workflow. (Verified locally: 6/6 pairs match, no drift.)
- [ ] T028 [P] Verify SC-006 (no eval jobs on feature-branch push): push the branch (without opening the PR yet) and confirm only `lint-test-build` ran in the Actions tab. Open the PR and confirm all six checks appear. *(Runtime check — perform after pushing.)*
- [X] T029 [P] Verify FR-013 (`lint-test-build` unchanged): run `git diff main -- .github/workflows/ci.yml` and confirm the existing `lint-test-build` job's `steps:` block is byte-identical to the pre-PR version. The only permitted changes to that file are (a) the header comment block from T025, (b) the five new `jobs:` entries and their artifact-upload sub-steps, and (c) the workflow-level `on:` triggers if explicitly modified. Flag any other change as a regression. (Verified locally: `lint-test-build` block extracted from both `main` and PR and compared — IDENTICAL.)
- [ ] T030 Run the full local quickstart end-to-end from [quickstart.md](quickstart.md) §1–§4 and confirm all expected outcomes. Capture any deviation as a follow-up issue rather than a silent fix. **Also exercise SC-002**: deliberately break a mock so a gate fails, push the branch, open the run page in a browser, and time how long it takes to identify the failing gate from the run summary alone — confirm under 30 seconds. Revert the mock break before opening the real PR. *(Local §1–§3 expected to pass once the user runs them; SC-002 timing is a runtime check.)*
- [X] T031 Run `ruff check .` and `pytest` locally; confirm `lint-test-build` will pass on the PR. (Verified: `ruff check .` → all checks passed; `pytest` → 150 passed, 1 pre-existing skip, 0 failed.)
- [X] T032 Author the PR description: include the gate / threshold / owner / mock-file-path table from Decision 9, explicitly listing each mock and the owner who must replace it. Per the planning input — "PR description lists which mocks need replacing once the real CLIs land". Also surface the known constitution-vs-thresholds gap from Decision 9's sub-bullet (RAG MRR) so reviewers see the follow-up at PR-open time. (Draft written below.)
- [ ] T033 Open the PR. Tag Ayoub for review (he owns three mocks, the `# Owner: Ayoub` headers, and reviews `eval_thresholds.yaml`-adjacent changes per CLAUDE.md). Tag Nasser (two mocks). Tag Hiba for the `DECISIONS.md` ownership header sanity check. *(User action — Claude does not run git/PR commands unless asked.)*

**Note**: Real-evaluator follow-up PRs by Ayoub/Nasser are explicitly out of scope for this feature. Each owner replaces their own `evals/<gate>.py` file in a separate PR; no further `.github/workflows/ci.yml` or `scripts/check_threshold.py` edits are required at that point.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1. Blocks Phase 3, 4, 5 because no eval job can run without `check_threshold.py`.
- **Phase 3 (US1)**: Depends on Phase 2. Delivers the MVP.
- **Phase 4 (US2)**: Depends on Phase 3 (artifacts upload from the same jobs created in US1).
- **Phase 5 (US3)**: Depends on Phase 3 (header comment describes the jobs wired in US1).
- **Phase 6 (Polish)**: Depends on Phases 3–5 being complete.

### User Story Dependencies

- **US1 (P1)** is independent — landing US1 alone produces a green CI with enforcing gates (MVP). Without artifact upload (US2) reviewers can still see the FAIL line in the log; without the header (US3) reviewers can still grep `eval_thresholds.yaml`.
- **US2 (P2)** depends on US1 — there is no eval job to attach an artifact to until US1 wires them.
- **US3 (P3)** depends on US1 only structurally (the header comment describes US1's jobs). US3 could technically merge in a follow-up PR if Phase 6's drift check (T027) is run by hand.

### Within Each Phase

- Setup directory creation (T001) must precede the `__init__.py` files (T002–T004).
- `scripts/check_threshold.py` (T005) must precede its tests (T006) only because the tests run the script; the test file can be drafted first if TDD-style is preferred.
- Within US1: all five mock files (T008–T012) and the mock test file (T013) can be done in parallel; workflow wiring tasks (T014–T018) all edit the SAME file (`.github/workflows/ci.yml`) and therefore CANNOT run in parallel — they must be sequenced.
- Within US2: all five artifact-upload edits (T020–T024) also touch the same workflow file and must be sequenced.
- Within US3: T025 (header) and T026 (DECISIONS) touch different files and can run in parallel.

### Parallel Opportunities

- **Phase 1**: T002, T003, T004 can run in parallel after T001.
- **Phase 2**: T005 and T006 can be drafted in parallel (TDD-friendly), but T006 must run *after* T005 exists for the tests to pass.
- **Phase 3 (US1) mocks**: T008, T009, T010, T011, T012, T013 — all six can run in parallel (different files).
- **Phase 3 (US1) workflow**: T014 through T019 all edit `.github/workflows/ci.yml`. They must be sequenced; if multiple developers are working, one person should own the workflow file edits.
- **Phase 4 (US2)**: T020–T024 all edit `.github/workflows/ci.yml`; sequenced.
- **Phase 5 (US3)**: T025 (ci.yml) and T026 (DECISIONS.md) can be parallel.
- **Phase 6**: T027, T028, T029, T031 can be parallel (different commands, independent checks); T030 runs after the mocks/workflow are in place; T032 (PR description) depends on Decision 9 (T026) existing; T033 (PR open) depends on everything else done.

---

## Parallel Example: Phase 3 (US1) mocks

```bash
# All six mock-and-test files are independent; six developers (or six terminals) can work in parallel:
Task: "Implement evals/classifier.py mock per contracts/eval-cli.md"
Task: "Implement evals/rag.py mock per contracts/eval-cli.md"
Task: "Implement evals/agent_tool.py mock per contracts/eval-cli.md"
Task: "Implement evals/red_team.py mock per contracts/eval-cli.md"
Task: "Implement evals/redaction.py mock per contracts/eval-cli.md"
Task: "Write tests/evals/test_mock_evaluators.py covering all five mocks"
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Phase 1 — directories and package markers (~5 min).
2. Phase 2 — `scripts/check_threshold.py` + unit tests (~1 hour).
3. Phase 3 — five mocks + mock tests + five workflow jobs (~1.5 hours).
4. **STOP and VALIDATE**: deliberately break a mock to confirm CI goes red; revert; confirm CI goes green again. US1 acceptance scenarios 1–4 exercised. This is the MVP — CI gates are now enforcing.

### Incremental Delivery

1. MVP done → optionally land US1 alone in its own PR (US2 and US3 follow-up). Recommended for this feature: bundle all three stories in one PR because they are tightly coupled and US3 needs to describe the jobs from US1.
2. US2 layered on top — one artifact-upload step per job. Adds the debug-from-run-page capability.
3. US3 layered on top — header comment + DECISIONS.md entry. Onboarding and audit complete.

### Parallel Team Strategy

With multiple owners working concurrently, Amer owns this entire feature (no cross-owner code), so parallelism is intra-Amer:
- One terminal: T005 + T006 (helper + tests).
- Second terminal: T008–T012 (five mocks) + T013 (mock tests) — fully parallelizable.
- Third terminal: queues up T014–T018 for sequential workflow edits once T005 lands.

---

## Notes

- Tests for the helper are subprocess-based (the helper's contract is its exit code and stdio, not its internal API). This keeps the tests honest and lets the helper be refactored freely.
- Mocks intentionally emit values **exactly at** the threshold, not above it. This makes the mock easy to break by subtracting any positive epsilon, which is useful for the validation step in T027/T028.
- All five mocks and the helper combined are well under 200 LOC. Principle VII (smallest change) is preserved.
- No `# Owner:` rule is bent: the mock files declare the *real* owner (Ayoub or Nasser) in the `# Owner:` line and name Amer as the temporary author in parentheses. Identical to Decision 7's `_StubAuditLogger` pattern.
- The workflow-file edits (T014–T024) are all in the same file and require careful sequencing. If a teammate has the file open simultaneously, rebase before merging.
- After merge, the next eval-related PR is owned by Ayoub or Nasser (real CLI replacement). They DO NOT need to touch `ci.yml`, `check_threshold.py`, or any of Amer's files — they replace exactly one file each.
