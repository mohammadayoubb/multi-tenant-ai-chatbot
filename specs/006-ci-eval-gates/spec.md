# Feature Specification: CI Eval Gates Enforced

**Feature Branch**: `006-ci-eval-gates`
**Created**: 2026-05-27
**Status**: Draft
**Input**: User description: "Expand `.github/workflows/ci.yml` with one CI job per eval gate from `eval_thresholds.yaml`. Add classifier-eval, rag-eval, agent-tool-eval, red-team, redaction-eval jobs. Each runs after `lint-test-build` succeeds, uses Python 3.11 + uv, invokes a CLI provided by the eval owner, parses JSON via `scripts/check_threshold.py`, uploads JSON as a workflow artifact, and fails the build when the threshold is not met. Document each gate in a header comment block at the top of `ci.yml` and add a Decision entry in `DECISIONS.md`."

## Clarifications

### Session 2026-05-27

- Q: Eval CLI bootstrap policy — what happens if an owner's CLI is not yet shipped when this PR merges? → A: **Refined during planning (2026-05-27):** ship mock eval modules in this PR that emit passing JSON conforming to the CLI contract. The mocks live at `evals/<gate>.py` and print a clear `"_mock": true` field in their JSON plus a stderr "MOCK EVALUATOR — replace before relying on this gate" line. The PR description lists every mock and the owner who must replace it with a real evaluator. This supersedes the earlier `enabled: true|false` flag proposal, which is dropped: real CLI artifacts (even mock ones) satisfy the contract more simply than a YAML flag, and the dedicated `_mock` field plus the per-gate stderr warning makes the temporary state visible on every CI run. `eval_thresholds.yaml` remains untouched — no new fields.
- Q: Eval CLI invocation contract — how does Amer call each eval CLI and what shape is its JSON output? → A: Each eval CLI is a Python module invoked as `python -m evals.<gate_name>` accepting `--output <path>`; on success it writes `{"metrics": {"<metric_key>": <value>, ...}}` to that path. The CLI's own exit code reflects internal CLI success/failure only; pass/fail against the threshold is decided exclusively by `scripts/check_threshold.py`.
- Q: When should eval jobs run? → A: `pull_request` events plus `push` to `main` only. Eval jobs do not run on pushes to feature branches; developers get fast lint/test/build feedback while iterating, gate enforcement happens at PR time, and `main` is re-verified post-merge so a green `main` always carries a passing eval set.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Block a PR that regresses a quality gate (Priority: P1)

A team member opens a pull request that unintentionally lowers classifier accuracy, breaks RAG retrieval quality, weakens agent tool selection, lets a guardrail through, or causes a redaction leak. CI runs every gate as a separate job; any gate whose measured metric is worse than the threshold committed in `eval_thresholds.yaml` reports a red check, and the PR cannot be merged until the regression is fixed.

**Why this priority**: Without enforcement, the eval thresholds in the repository are aspirational. Phase 10 of the project build order exists specifically to make those thresholds binding on every merge to `main`. This is the entire purpose of the feature.

**Independent Test**: Push a branch that deliberately makes an eval CLI return a JSON metric below the threshold; verify the relevant CI job exits non-zero, the overall workflow reports failure, and the produced JSON output is attached as a workflow artifact for the reviewer.

**Acceptance Scenarios**:

1. **Given** an open pull request whose code change drops measured classifier macro-F1 to 0.78, **When** CI runs, **Then** the `classifier-eval` job fails with a clear message naming the threshold (0.80), the measured value (0.78), and the gate key (`classifier.macro_f1_min`); the overall workflow is red; the JSON output is uploaded as an artifact.
2. **Given** a pull request that causes one red-team prompt to receive an unsafe answer (refusal rate < 1.0), **When** CI runs, **Then** the `red-team` job fails and blocks merge.
3. **Given** a pull request that causes the redaction CLI to report `secret_leak_count = 1`, **When** CI runs, **Then** the `redaction-eval` job fails and blocks merge.
4. **Given** a green pull request whose eval metrics all meet or exceed thresholds, **When** CI runs, **Then** every eval job is green, all five JSON artifacts are available, and merge is unblocked.

---

### User Story 2 - Reviewer downloads JSON artifacts to debug a failure (Priority: P2)

When an eval job fails, the reviewer needs the full JSON output of the underlying CLI to understand which examples regressed, not just the threshold error message. The workflow uploads each eval's JSON output as a named artifact regardless of pass or fail, so reviewers can download it from the run page.

**Why this priority**: A red check without context forces the reviewer to re-run the eval locally. Attaching the JSON is cheap and shortens triage substantially. It is not strictly required to enforce gates, hence P2.

**Independent Test**: Open any completed CI run page; verify five artifacts (one per eval job) are present and contain the JSON the CLI emitted.

**Acceptance Scenarios**:

1. **Given** a workflow run with a failing `rag-eval` job, **When** the reviewer opens the run page, **Then** the JSON artifact named `rag-eval-output` is available for download and contains the metrics block the CLI emitted.
2. **Given** a workflow run with all eval jobs green, **When** the reviewer opens the run page, **Then** all five artifacts are still uploaded so they can be compared across runs.

---

### User Story 3 - New contributor reads the workflow and understands every gate (Priority: P3)

A contributor opening `.github/workflows/ci.yml` for the first time can read a header comment block that lists each eval gate, its threshold key in `eval_thresholds.yaml`, and the team member who owns the underlying eval script, without having to grep across the repo.

**Why this priority**: Improves onboarding and review quality but does not change CI behavior. P3.

**Independent Test**: Open `ci.yml`; verify the header comment names every gate, its threshold, and the owner; cross-reference against `eval_thresholds.yaml` to confirm parity.

**Acceptance Scenarios**:

1. **Given** a new contributor opens `ci.yml`, **When** they read the header comment, **Then** they can list every gate, its threshold key, and the responsible owner without opening any other file.
2. **Given** a `DECISIONS.md` reader, **When** they reach the new "CI Eval Gates Enforced" decision entry, **Then** the same gate-by-gate ownership table is recorded for posterity.

---

### Edge Cases

- An eval CLI module (`evals/<gate>.py`) is missing entirely: the job MUST fail loudly with a clear message identifying the missing module and the responsible owner, not silently succeed.
- An eval CLI exists but is a mock (`_mock: true` in its JSON): the job MUST pass when the mock emits passing values, but MUST print a clearly visible stderr line on every run reminding reviewers that this gate is not yet enforcing on real measurements; reviewers can grep the workflow log for `MOCK EVALUATOR` to find all unfulfilled gates.
- An eval CLI emits a metric below the threshold (mock or real): the job MUST fail. Mocks shipped in this PR therefore must emit values strictly at or above the threshold; a mock emitting a failing value indicates a defect in the mock.
- An eval CLI emits malformed JSON (or non-JSON): the threshold checker MUST exit non-zero with a message naming the offending file and gate.
- An eval CLI emits valid JSON but is missing the expected metric key: the threshold checker MUST exit non-zero, name the missing key, and reference the gate it belongs to.
- The `eval_thresholds.yaml` file is missing a gate key the workflow expects: the threshold checker MUST exit non-zero with a clear message, never default silently to zero.
- The eval CLI takes longer than the workflow timeout: the job MUST fail with a timeout, not be skipped.
- `lint-test-build` fails: every eval job MUST be skipped (not run), so the developer fixes basic issues first.
- A PR modifies `eval_thresholds.yaml`: the change is permitted only with Ayoub's review (per existing CLAUDE.md ownership), and this feature does NOT enforce or change that ownership.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The CI workflow MUST define five eval jobs in `.github/workflows/ci.yml`: `classifier-eval`, `rag-eval`, `agent-tool-eval`, `red-team`, `redaction-eval`.
- **FR-002**: Each eval job MUST declare `needs: lint-test-build` so it runs only after the existing lint/test/build job succeeds and is skipped otherwise.
- **FR-002a**: Eval jobs MUST run only on (a) `pull_request` events and (b) `push` events to the `main` branch. They MUST NOT run on pushes to feature branches. The `lint-test-build` job retains its current broader trigger set unchanged.
- **FR-003**: Each eval job MUST use the same Python 3.11 + `uv` installation pattern as `lint-test-build` and MUST cache dependencies to keep runtimes consistent across jobs.
- **FR-004**: Each eval job MUST invoke a CLI provided by the gate's owner. This feature MUST NOT implement, mock, or stub the eval logic itself; it only wires the CLI into CI.
  - `classifier-eval` → `python -m evals.classifier` → owner: Ayoub
  - `rag-eval` → `python -m evals.rag` → owner: Nasser
  - `agent-tool-eval` → `python -m evals.agent_tool` → owner: Nasser
  - `red-team` → `python -m evals.red_team` → owner: Ayoub
  - `redaction-eval` → `python -m evals.redaction` → owner: Ayoub
- **FR-005**: Each eval CLI MUST be invoked with `--output <path>` so its JSON output is written to a known file path, which the job then passes to `scripts/check_threshold.py` for assertion against `eval_thresholds.yaml`.
- **FR-005a**: Each eval CLI's JSON output MUST conform to the shape `{"metrics": {"<metric_key>": <numeric_value>, ...}}`. The `<metric_key>` for each gate MUST be the unqualified metric name from `eval_thresholds.yaml` (e.g., `macro_f1`, `hit_at_5`, `faithfulness`, `accuracy`, `refusal_rate`, `secret_leak_count`). Additional sibling keys at the top level (e.g., `meta`, `dataset_hash`) are permitted but ignored by the threshold checker. Additional keys *inside* `metrics` (e.g., per-class F1, per-example diagnostics) are also permitted and ignored — the checker only reads the single `<metric_key>` it was invoked for.
- **FR-005b**: The eval CLI's own exit code reflects internal CLI success or failure only (e.g., dataset missing, model load error). Pass/fail against the threshold is decided exclusively by `scripts/check_threshold.py` reading the JSON output. A successful CLI run that emits a below-threshold metric MUST exit zero; the threshold checker is the sole arbiter of gate pass/fail.
- **FR-006**: A new helper `scripts/check_threshold.py` MUST exist. It MUST read the gate key from `eval_thresholds.yaml`, read the measured metric from the eval JSON output, and exit non-zero with a clear message when the measured value violates the threshold direction (`*_min` means measured must be ≥ threshold; `required_refusal_rate` must equal `1.0`; `required_secret_leak_count` must equal `0`).
- **FR-006a**: This PR MUST ship a mock implementation of every eval CLI at `evals/<gate>.py` (one per gate). Each mock MUST accept the standard contract (`python -m evals.<gate> --output <path>`) and write JSON of the shape `{"metrics": {"<metric_key>": <passing-value>}, "_mock": true}` where `<passing-value>` is strictly at or above the threshold (or exactly equal for `==` gates). Each mock MUST also print a single stderr line: `MOCK EVALUATOR: <gate> is not yet implemented — owner: <name>` so reviewers can grep workflow logs for `MOCK EVALUATOR` to find every unfulfilled gate.
- **FR-006b**: Each mock module MUST carry a file-header banner comment naming the real owner (Ayoub or Nasser) and instructing them to replace the file when their real evaluator is ready. The PR description MUST list each mock and the owner responsible for replacing it.
- **FR-006c**: The threshold checker MUST NOT treat the `_mock: true` field specially — a mock that emits a below-threshold value still fails the gate. The `_mock` field is informational only.
- **FR-007**: The threshold checker MUST treat a missing gate key, missing metric, malformed JSON, or unreadable threshold file as a failure, not a pass.
- **FR-008**: Each eval job MUST upload the eval JSON output as a workflow artifact with a stable name (one artifact per gate, e.g., `classifier-eval-output`), uploaded on both success and failure, so reviewers can download it from the run page.
- **FR-009**: `.github/workflows/ci.yml` MUST begin with a header comment block listing each gate, its threshold key in `eval_thresholds.yaml`, the threshold value (or required condition), and the owner of the underlying eval script.
- **FR-010**: `DECISIONS.md` MUST contain a new decision entry titled "CI Eval Gates Enforced" that documents the same gate / threshold / owner table and explains that this PR only wires the gates and does not author the eval logic.
- **FR-011**: The threshold checker and the CI wiring MUST treat `eval_thresholds.yaml` as read-only in this PR. This feature MUST NOT change any threshold number, comparison direction, required-condition value, or add any new field. (The earlier-proposed `enabled` field is dropped in favor of the mock approach in FR-006a.)
- **FR-012**: Each eval job MUST surface a human-readable failure message that names the gate key, the threshold, and the measured value, so reviewers do not need to download the artifact to know which gate broke.
- **FR-013**: The workflow MUST keep the existing `lint-test-build` job and its current steps unchanged in scope; eval jobs are additive.
- **FR-014**: The set of eval jobs in CI MUST match the set of gates in `eval_thresholds.yaml` exactly — no extra gates wired without a threshold, no gates in `eval_thresholds.yaml` left unwired.

### Key Entities

- **Eval Gate**: A named quality threshold owned by a specific team member, with a key in `eval_thresholds.yaml` (e.g., `classifier.macro_f1_min`), a measured metric emitted by an owner-provided CLI, and a pass/fail rule (≥ minimum, == required exact value).
- **Eval JSON Output**: The JSON document an eval CLI writes to disk for a single run, containing at minimum the measured metric the threshold checker reads. Uploaded as a workflow artifact for every job.
- **Threshold Checker (`scripts/check_threshold.py`)**: A small helper this feature adds. Given a gate key and a JSON output file, it asserts the measured metric satisfies the threshold and exits zero on pass / non-zero with a descriptive message on fail.
- **Decision Record**: An entry appended to `DECISIONS.md` documenting which gates are enforced in CI, their thresholds, and which team member owns each underlying eval script.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A pull request that drops a measured eval metric below its threshold in `eval_thresholds.yaml` is blocked from merging by a failing CI check 100% of the time.
- **SC-002**: A reviewer can determine which gate failed and by how much in under 30 seconds, using only the CI run page (job log line + artifact name), without cloning the branch.
- **SC-003**: 100% of eval jobs upload their JSON output as a workflow artifact, on both pass and fail runs, so the artifact set on the run page always equals five.
- **SC-004**: A new contributor reading the top of `ci.yml` can list every enforced gate, its threshold, and its owner without opening any other file.
- **SC-005**: The set of gate keys referenced by the CI workflow equals the set of gate keys in `eval_thresholds.yaml`: zero drift between the workflow and the source-of-truth thresholds.
- **SC-006**: A push to a feature branch does NOT trigger any eval job (verified by inspecting the workflow run page for a feature-branch push: only `lint-test-build` appears). Pushes to `main` and any `pull_request` event DO trigger all five eval jobs.

## Assumptions

- Each eval owner (Ayoub for classifier / red-team / redaction; Nasser for RAG and agent tool-selection) will deliver a real CLI that emits JSON containing the metric the relevant gate measures. This PR ships mock CLIs at `evals/<gate>.py` that emit passing JSON conforming to the contract; each owner replaces their own mock in a follow-up PR. The mock approach keeps CI green and contractually correct from day one while marking the unfinished work clearly on every run.
- The owner-provided CLIs read their inputs (datasets, model artifacts, prompts) from existing locations in the repo or from environment variables already documented in their respective phases. No new secrets are introduced by this feature.
- The runners are GitHub-hosted `ubuntu-latest`, the same as the existing `lint-test-build` job.
- Eval datasets and model artifacts required by the CLIs are available in the repository or downloadable via existing project mechanisms; this feature does not provision new data.
- `DECISIONS.md` already exists in the repository (per the team rule in CLAUDE.md). The new decision is appended with the next sequential number.
- Modifying `eval_thresholds.yaml` is out of scope and remains Ayoub-owned. This feature reads the file but does not change it.
- Eval CLIs are deterministic enough that a green run on `main` stays green on a re-run; non-deterministic flake handling (retries, seeds) is out of scope for this PR.
- Long-running evals are acceptable within the GitHub Actions default job timeout; introducing distributed execution, caching of eval outputs across runs, or running evals only on certain paths is out of scope.
- **Known constitution-vs-thresholds gap (acknowledged, not closed by this PR)**: the project constitution `## Quality Gates` table lists `RAG MRR ≥ 0.50` as an enforced gate, but `eval_thresholds.yaml` does not contain a corresponding `mrr_min` key. This feature wires exactly the gates present in `eval_thresholds.yaml` (per FR-014), so the MRR gate remains un-wired after this PR. Closing the gap is Ayoub's call (he owns `eval_thresholds.yaml`) and Nasser's to implement (he owns `evals/rag.py` and would emit the third metric). This PR's `DECISIONS.md` Decision 9 sub-bullet records the gap and names the follow-up owners.
