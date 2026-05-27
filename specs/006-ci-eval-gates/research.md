# Phase 0 Research: CI Eval Gates Enforced

**Feature**: 006-ci-eval-gates · **Date**: 2026-05-27 · **Owner**: Amer

This document resolves the open design questions for wiring the five eval gates from `eval_thresholds.yaml` into `.github/workflows/ci.yml`. The clarifications captured under `## Clarifications` in `spec.md` already pinned the highest-impact decisions; this research records the remaining implementation-level decisions and rejects the alternatives so reviewers do not need to re-litigate them.

## R1 — Mock CLIs vs. `enabled` flag for bootstrap

**Decision**: Ship mock eval modules at `evals/<gate>.py` that emit passing JSON conforming to the standard CLI contract. Each mock writes `{"metrics": {"<metric>": <passing>}, "_mock": true}` and prints `MOCK EVALUATOR: <gate> is not yet implemented — owner: <name>` to stderr.

**Rationale**:
- A real, contract-conforming CLI (even if its measurement is hardcoded) is operationally simpler than a YAML flag plus a special "missing CLI" branch in `check_threshold.py`. One execution path, not two.
- Reviewers see the `MOCK EVALUATOR` line on every CI run; the temporary state is loud, not silent.
- Each owner replaces a single file (`evals/<their_gate>.py`) — no coordination with Amer needed for the flag flip.
- Matches the established Decision 7 / Decision 8 stub pattern (Amer ships placeholder while real owner is upstream).
- The `_mock: true` field gives any downstream tooling (e.g. dashboard, badge) a single key to detect un-fulfilled gates.

**Alternatives considered**:
- *Per-gate `enabled: true|false` in `eval_thresholds.yaml`* (the original clarify Q1 answer). Rejected: requires Ayoub-owned file edits, requires the threshold checker to branch on a flag, and silent-passes the gate when disabled in a way that's less visible than a stderr warning on every run.
- *`continue-on-error: true` on every job until real CLI lands*. Rejected: a failing job with `continue-on-error: true` shows as a green check on the PR page in GitHub's default view; reviewers can be misled.
- *Ship only jobs whose CLI exists today, add others as they land*. Rejected: the CI header comment and `DECISIONS.md` entry already describe the full set; partial delivery would mean two more workflow-churn PRs as owners land their CLIs.

## R2 — `python -m evals.<gate>` vs. console-script entry vs. Makefile target

**Decision**: Invoke each CLI as `python -m evals.<gate> --output <path>` (clarify Q2 answer A).

**Rationale**:
- Matches how `pytest`, `ruff`, and other project tools are already invoked from CI.
- No `pyproject.toml` edit required — the module path *is* the contract.
- Works identically on a developer's machine and in CI.
- The `evals/` package can grow per-gate dependencies (test fixtures, helper modules) without polluting the top-level `scripts/` namespace, which Amer owns and which is used for one-off CLIs.

**Alternatives considered**:
- *Console scripts in `pyproject.toml`*. Rejected: adds a `pyproject.toml` edit on every new gate, requires re-`uv pip install` in CI for each gate, and obscures the entry point.
- *Makefile target per gate*. Rejected: the project does not currently use a `Makefile`; introducing one for this feature is scope creep.
- *Per-gate `command:` string in `eval_thresholds.yaml`*. Rejected: leaks invocation details into a file Ayoub owns for thresholds, and gives owners too much freedom to invent inconsistent invocation styles.

## R3 — JSON output schema

**Decision**: `{"metrics": {"<metric_key>": <numeric_value>, ...}, "_mock"?: true, "<any sibling>": ...}`. The `<metric_key>` is the unqualified metric name from `eval_thresholds.yaml` (`macro_f1`, `hit_at_5`, `faithfulness`, `accuracy`, `refusal_rate`, `secret_leak_count`). Additional sibling keys (`meta`, `dataset_hash`, `_mock`, etc.) are allowed and ignored by the threshold checker.

**Rationale**:
- A nested `metrics` object lets owners ship extra context (per-class F1, per-example diagnostics) at the top level without confusing the threshold checker.
- The `<metric_key>` matches the leaf name in `eval_thresholds.yaml` so the mapping is mechanical and obvious: `classifier.macro_f1_min` → `metrics.macro_f1`. The checker strips the `_min` suffix.
- For `==` gates (`required_refusal_rate`, `required_secret_leak_count`), the leaf metric name in the JSON is the `required_*` value without the `required_` prefix: `refusal_rate`, `secret_leak_count`. This is documented in the contract.

**Alternatives considered**:
- *Flat JSON keys matching the full dotted path (`"classifier.macro_f1": 0.83`)*. Rejected: the dotted key would tie the JSON shape to `eval_thresholds.yaml`'s exact nesting; if Ayoub later regroups the YAML, every CLI breaks.
- *Per-gate JSON Schema files*. Rejected: speculative; the shape is uniform enough that one rule covers all five gates.

## R4 — Threshold direction inference

**Decision**: `scripts/check_threshold.py` infers comparison direction from the threshold key suffix in `eval_thresholds.yaml`:
- `*_min` → measured MUST be ≥ threshold; fail with `<gate>.<metric>: measured <m> < min <t>` otherwise.
- `required_<metric>` → measured MUST equal the required value exactly; fail with `<gate>.<metric>: measured <m> != required <t>` otherwise. The JSON key consumed is `<metric>` (drop the `required_` prefix).

**Rationale**:
- Mechanical mapping from threshold key shape to comparison rule — no per-gate special case in the helper.
- Keeps the helper at ~80 LOC; adding a YAML field to declare direction per gate would be over-engineering.

**Alternatives considered**:
- *Explicit `operator: ">="` field per gate in `eval_thresholds.yaml`*. Rejected: requires modifying the Ayoub-owned file, and the suffix convention is already self-documenting and used today.
- *Hardcoded direction map keyed by gate name inside `check_threshold.py`*. Rejected: more fragile (every new gate requires a helper edit) and less self-evident than reading the suffix.

## R5 — Five parallel jobs vs. a matrix

**Decision**: Five distinct jobs in `ci.yml`, one per gate. Not a `strategy.matrix`.

**Rationale**:
- Each gate has a different owner and different failure semantics (≥ vs. ==). A matrix obscures ownership and produces noisier failure logs.
- The GitHub Actions UI shows one named check per gate, which is what code reviewers want to scan — five lines: `classifier-eval ✅`, `rag-eval ✅`, etc. A matrix collapses to a single check.
- Cost is identical (each matrix leg spawns a runner anyway).

**Alternatives considered**:
- *Single matrix job with `gate` as the dimension*. Rejected: collapses five checks into one, masks ownership, and makes the artifact upload step harder (one artifact per matrix leg requires `${{ matrix.gate }}` interpolation everywhere).
- *Two jobs grouped by direction (`min-gates` and `eq-gates`)*. Rejected: arbitrary grouping; reviewers do not think in terms of comparison direction.

## R6 — Artifact upload on success and on failure

**Decision**: Use `actions/upload-artifact@v4` with `if: always()` so the JSON artifact is uploaded whether the gate passes or fails. Artifact name pattern: `<gate>-eval-output` (e.g., `classifier-eval-output`).

**Rationale**:
- Reviewers need the JSON on failure (to debug); they also occasionally want it on success (to compare across runs or to feed a dashboard).
- `actions/upload-artifact@v4` is the current GitHub-supported version (v3 is deprecated as of Jan 2025).
- Five distinct artifact names map cleanly to the five jobs — no name collisions when the workflow re-runs across matrix legs (we are not using a matrix anyway).

**Alternatives considered**:
- *Upload only on failure*. Rejected: reviewers in spec.md SC-003 explicitly want artifacts on every run.
- *One combined artifact*. Rejected: requires a sixth job to assemble it; gives no advantage.

## R7 — Trigger refinement: `pull_request` + `push to main` only

**Decision** (already pinned by clarify Q3): Eval jobs run on `pull_request` events and on `push` events filtered to `branches: [main]`. The `lint-test-build` job retains its current broader trigger set unchanged (runs on every push and every PR).

**Rationale**:
- Eval jobs may be expensive (especially RAG and red-team across full suites once real CLIs land).
- Developers want fast lint/test/build feedback on every feature-branch push.
- A green `main` is still re-verified by the post-merge `push: branches: [main]` run, so the constitution's "every PR must pass these gates" promise is upheld.

**Implementation note**: GitHub Actions has no `needs:` cross-trigger filter, but `if: github.event_name == 'pull_request' || (github.event_name == 'push' && github.ref == 'refs/heads/main')` on each eval job achieves the same effect cleanly. This expression is duplicated across the five jobs; per Principle VII, ~5 identical lines beats one shared anchor/env-var abstraction.

## R8 — DECISIONS.md entry numbering

**Decision**: This entry will be `Decision 9 — CI Eval Gates Enforced (Amer, 2026-05-27)`.

**Rationale**: Decisions 1–8 are already recorded in `DECISIONS.md`. Decision 9 is the next sequential number. Per CONTRACT.md §16, this is a "changing Docker/CI behavior" change — a recognized "major decision" category — so the entry is required.

**Format**: Follows the established Context / Decision / Consequences / References shape used by Decisions 4–8, plus the one-line-per-gate table the user explicitly requested in the planning input (threshold, owner, eval-script path).

## R9 — Helper script location and ownership

**Decision**: `scripts/check_threshold.py` (Amer-owned, header banner `# Owner: Amer`).

**Rationale**:
- `scripts/` is the existing home for Amer-owned, project-wide CLIs (`seed_tenants.py`, `smoke_check.py`, `vault_seed.py`). The threshold checker fits the same shape.
- One file, ~80 LOC, one responsibility (read YAML, read JSON, compare, exit code) — keeps Principle VII happy.

**Alternatives considered**:
- *Inline the comparison inside each CI step*. Rejected: 5× duplicated YAML+JSON parsing in bash is harder to test and harder to read than one Python helper.
- *Put it under `evals/`*. Rejected: `evals/` is the home for owner-supplied measurement code (Ayoub/Nasser will replace files there). The threshold checker is workflow plumbing and belongs with `seed_tenants.py` and friends.

## R10 — How the mocks are "owned" while still being shipped by Amer

**Decision**: Each mock file carries a file-header that names both Amer (current author) and the real owner (Ayoub or Nasser) to swap in the replacement. Example header:

```python
# Owner: Ayoub (TEMPORARY MOCK by Amer, 2026-05-27 — replace this file with the real classifier evaluator)
"""Mock classifier evaluator. Replace with real measurement CLI."""
```

**Rationale**:
- The constitution's `# Owner:` header rule (development workflow) names the *responsible* owner, not the most recent author. The eval logic belongs to Ayoub/Nasser.
- The parenthetical names Amer as the author of the placeholder so future blame / archaeology is clear.
- Identical to Decision 7's `_StubAuditLogger` pattern — Amer ships a no-op stub that the real owner replaces.

## Coverage of remaining spec ambiguities

| spec.md item | Resolved in |
|---|---|
| Bootstrap behavior (Q1 + planning refinement) | R1 |
| CLI invocation contract (Q2) | R2, R3, R4 |
| Trigger scope (Q3) | R7 |
| Job grouping (parallel vs. matrix) | R5 |
| Artifact upload conditions | R6 |
| Helper script location | R9 |
| Mock-file ownership semantics | R10 |
| DECISIONS.md placement | R8 |

No NEEDS CLARIFICATION items remain.
