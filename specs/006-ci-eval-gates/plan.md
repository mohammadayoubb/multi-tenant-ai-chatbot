# Implementation Plan: CI Eval Gates Enforced

**Branch**: `006-ci-eval-gates` | **Date**: 2026-05-27 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/006-ci-eval-gates/spec.md`

## Summary

Wire the five quality gates declared in `eval_thresholds.yaml` (classifier macro-F1, RAG hit@5 + faithfulness, agent tool-selection accuracy, red-team refusal rate, redaction secret-leak count) into `.github/workflows/ci.yml` as five new jobs that each depend on `lint-test-build`. Each job invokes a Python-module eval CLI (`python -m evals.<gate> --output <path>`), pipes the resulting JSON through a new `scripts/check_threshold.py` helper for assertion against `eval_thresholds.yaml`, uploads the JSON as a workflow artifact, and exits non-zero on threshold miss. Real eval logic is owned by Ayoub and Nasser; this PR ships mock modules at `evals/<gate>.py` that print passing JSON plus a `MOCK EVALUATOR` stderr warning, so the gates can light up immediately and each owner replaces their own mock in a follow-up. A new `Decision 9 — CI Eval Gates Enforced` row is appended to `DECISIONS.md`.

## Technical Context

**Language/Version**: Python 3.11 (matches the existing `lint-test-build` job and the project's stated baseline)
**Primary Dependencies**: `PyYAML` (already a transitive dependency; reads `eval_thresholds.yaml`); Python stdlib `argparse`, `json`, `sys` for the helper and mocks. No new third-party deps.
**Storage**: N/A — this feature has no database state. Eval JSON outputs are ephemeral artifacts on the GitHub Actions runner, uploaded as workflow artifacts.
**Testing**: `pytest` for `scripts/check_threshold.py` and for the mock modules (pure stdout/exit-code testing); the CI workflow itself is exercised by every push/PR that triggers it. No new test framework introduced.
**Target Platform**: GitHub Actions `ubuntu-latest` runners (same as the existing job). Local-developer runs are supported via the same `python -m evals.<gate>` invocation pattern.
**Project Type**: CLI tool + GitHub Actions workflow (no app code, no service, no widget changes). Owner: Amer (Phase 10).
**Performance Goals**: `scripts/check_threshold.py` is O(file read) — must complete in under one second. Each mock CLI must complete in under one second. The runtime budget for the real CLIs is owned by Ayoub/Nasser and is out of scope here.
**Constraints**:
- MUST NOT change any threshold *value* in `eval_thresholds.yaml` (Ayoub-owned).
- MUST NOT introduce `torch` or `transformers` into any container or into the test environment (Principle V).
- MUST NOT implement real eval logic — only the wiring and the contractually-passing mocks.
- MUST keep the existing `lint-test-build` job and its current triggers unchanged in scope.
- MUST run new eval jobs only on `pull_request` events and `push` to `main` (per Q3 clarification).
- Mock modules MUST emit `_mock: true` and a stderr `MOCK EVALUATOR` line so reviewers cannot accidentally assume a real measurement was taken.
**Scale/Scope**: 5 new CI jobs · 1 new helper script (`scripts/check_threshold.py`, ~80 LOC) · 5 mock modules (`evals/<gate>.py`, ~15 LOC each) · 1 new test file (`tests/scripts/test_check_threshold.py`, ~120 LOC) · ~10 mock-output unit tests in `tests/evals/test_mock_evaluators.py` · 1 modified `.github/workflows/ci.yml` · 1 modified `DECISIONS.md`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **Principle I (Tenant Isolation):** No new database tables, no new repository queries, no pgvector usage, no `tenant_id` flowing anywhere in this feature. The eval JSON outputs are global (not tenant-scoped) by design — they measure model quality across the test corpus, not per-tenant traffic. PASS — out of scope.
- [x] **Principle II (Layered Architecture):** This feature lives entirely under `.github/workflows/`, `scripts/`, and `evals/`. No new code in `app/api/routes/`, `app/services/`, or `app/repositories/`. The layered architecture is untouched.
- [x] **Principle III (Bounded Agent):** No new agent tool is introduced; the existing `rag_search` / `capture_lead` / `escalate` set is unchanged. The agent tool-selection eval job consumes a CLI that *measures* tool selection but does not modify the tool surface.
- [x] **Principle IV (Defense-in-Depth Auth):** No new secrets, no new credentials, no new auth surface. Eval CLIs read from the repo's existing test fixtures (provided by their owners) and from the public `eval_thresholds.yaml`.
- [x] **Principle V (Lean Serving & Redaction):** No `torch` or `transformers` in any container (the mocks are stdlib-only Python; real CLIs run on the runner outside the serving image). Eval JSON outputs do not contain raw PII or raw prompts — owners must ensure their CLIs comply, and this is enforced in their respective PRs, not this one.
- [x] **Principle VI (Phased Build):** This is the Phase 10 deliverable for Amer (CI/CD and eval gates). No work is done outside Phase 10. Mock files in `evals/` are stubs owned temporarily by Amer per the established Decision 7/8 pattern (cross-phase scaffolding via documented swap points); each owner replaces their own mock in their own follow-up PR.
- [x] **Principle VII (Clean & Simple Code):** The helper is one ~80-LOC script with a single responsibility (compare measured ≥ / == threshold, exit 1 with a clear message otherwise). The mocks are ~15 lines each, with no abstractions. No speculative design — the earlier-proposed `enabled` flag was dropped during planning precisely to avoid over-engineering.

No unchecked boxes. No Complexity Tracking entries needed.

## Project Structure

### Documentation (this feature)

```text
specs/006-ci-eval-gates/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── eval-cli.md          # Owner-supplied CLI contract
│   └── threshold-checker.md # scripts/check_threshold.py contract
├── checklists/
│   └── requirements.md  # From /speckit-specify
├── spec.md
└── tasks.md             # Phase 2 output (NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
└── workflows/
    └── ci.yml                        # MODIFIED: header comment + 5 new jobs + trigger refinement

scripts/
└── check_threshold.py                # NEW: ~80 LOC helper, owner Amer

evals/                                # NEW directory
├── __init__.py                       # empty
├── classifier.py                     # NEW mock — to be replaced by Ayoub
├── rag.py                            # NEW mock — to be replaced by Nasser
├── agent_tool.py                     # NEW mock — to be replaced by Nasser
├── red_team.py                       # NEW mock — to be replaced by Ayoub
└── redaction.py                      # NEW mock — to be replaced by Ayoub

tests/
├── scripts/
│   └── test_check_threshold.py       # NEW: unit tests for the helper
└── evals/
    └── test_mock_evaluators.py       # NEW: assert every mock emits passing JSON + _mock:true + stderr warning

DECISIONS.md                          # MODIFIED: append Decision 9
```

**Structure Decision**: This is a CI-and-tooling feature, not an app feature. It adds two top-level directories (`evals/` and `tests/scripts/`, `tests/evals/`) and one helper script under the existing `scripts/` directory. No `src/`, `backend/`, or `frontend/` layout applies. The project root already contains `scripts/`, `app/`, `frontend/`, etc.; this PR adds `evals/` as a new sibling because eval modules are conceptually owned by the eval team (Ayoub/Nasser), are invoked as `python -m evals.<gate>`, and should not be co-located with the serving stack (Principle V — keep training-and-evaluation artifacts out of serving image paths).

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified.

None. All seven principles passed without waivers.
