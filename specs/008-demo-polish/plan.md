# Implementation Plan: Demo Polish

**Branch**: `008-demo-polish` | **Date**: 2026-05-28 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/008-demo-polish/spec.md`

## Summary

Polish the repo for the live demo. Four concrete deliverables:

1. **README.md** gets an "Embed the widget" section with a copy-pasteable `<script src=".../widget.js" data-widget-id="..." data-backend-url="...">` snippet.
2. **RUNBOOK.md** gets the existing Demo Flow rewritten as nine numbered steps with the actual commands that work on a clean clone, plus a one-line `pytest tests/smoke/` invocation.
3. **Lean-image audit** lands as a shell script + a `Makefile` target + a new CI job that runs `pip list` inside the built `modelserver` and `guardrails` images and fails on any line matching `^(torch|transformers)\b`. This enforces Constitution Principle V.
4. **`docker-compose.yml` healthcheck audit**: confirm `api`, `modelserver`, `guardrails` healthchecks already work; verify no `depends_on` short-form races on cold start; fix only what is actually broken.

Three demo screenshots (admin audit-log rejection, widget mid-chat, CI green) are captured out-of-repo per the user's explicit instruction and are not part of the merge.

No new product code, no new routes, no schema changes, no agent or auth changes.

## Technical Context

**Language/Version**: Python 3.11 (for the lean-check script); Bash + PowerShell (for invoking the check locally on contributors' machines); Markdown (README, RUNBOOK); GitHub Actions YAML; Docker Compose v2 YAML.
**Primary Dependencies**: Docker (already a hard prerequisite), `docker compose`, `make` (new — Amer adds a tiny `Makefile` only if not already present), GitHub Actions `actions/checkout@v4`, the existing widget loader at `frontend/widget/dist/widget.js`, the existing smoke runner at `scripts/smoke_check.py` and the test suite under `tests/smoke/`.
**Storage**: N/A (this feature touches no database, no Redis, no MinIO, no Vault).
**Testing**: `pytest tests/smoke/` against a running local stack for end-to-end verification of the runbook; manual three-times cold-start of `docker compose up --wait` for the healthcheck/depends_on race check; CI green on the new `lean-image-audit` job for the constitutional gate.
**Target Platform**: Linux CI (ubuntu-latest), macOS + Windows + Linux contributor machines (the Makefile target must work on all three since `make` is available; the underlying shell snippet must be portable enough or the target falls back to invoking `docker compose run --rm --entrypoint pip <service> list`).
**Project Type**: Documentation + CI/CD hardening. No new application code.
**Performance Goals**: Lean-image-audit job MUST complete in under two minutes on `ubuntu-latest`, reusing the existing `docker compose build` artifact from `lint-test-build`. Demo Flow end-to-end (clean clone → smoke pass) MUST complete in under 15 minutes on a developer laptop (SC-002).
**Constraints**: No changes to protected files except `docker-compose.yml` (already on the allowlist for this feature) and `.github/workflows/ci.yml` (the audit job is wired in here). No edits to `app/`, `modelserver/main.py`, `guardrails/main.py`, agent code, prompts, guardrails rails, migrations, or `eval_thresholds.yaml`.
**Scale/Scope**: Edits to five files (`README.md`, `RUNBOOK.md`, `docker-compose.yml`, `.github/workflows/ci.yml`, `DECISIONS.md`) and creation of two new files (`Makefile`, `scripts/check_lean_images.sh`). The `DECISIONS.md` entry is required because adding a CI job is "changing Docker/CI behavior" per constitution §Development Workflow.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **Principle I (Tenant Isolation):** N/A — no new tables, no new queries, no new pgvector calls, no `tenant_id` flow changes. Documentation only.
- [x] **Principle II (Layered Architecture):** N/A — no route, service, or repository code is touched. The lean-check script lives under `scripts/` and is invoked by CI and developers; it does not call into the application layers.
- [x] **Principle III (Bounded Agent):** N/A — the agent tool set (`rag_search`, `capture_lead`, `escalate`), loop limits (5 / 4000), and tool schemas are not touched.
- [x] **Principle IV (Defense-in-Depth Auth):** N/A — widget auth flow is not changed. The README snippet documents the existing `data-widget-id` / `data-backend-url` flow; it does not introduce any new auth path. No secrets are introduced; the snippet uses obvious placeholder values.
- [x] **Principle V (Lean Serving & Redaction):** This feature **enforces** Principle V. The new lean-image-audit job runs `pip list` inside the built `modelserver` and `guardrails` images and fails the PR if `torch` or `transformers` appears. No log/redaction surface changes.
- [x] **Principle VI (Phased Build):** Fits Phase 10 (CI/CD and eval gates) and Phase 11 (Documentation), both owned by Amer per the constitution. No cross-phase reach into app/agent/guardrails code.
- [x] **Principle VII (Clean & Simple Code):** Smallest possible change — one shell script, one tiny Makefile, one new CI job, two markdown edits, and a compose audit. No abstractions, no new helper libraries, no speculative scope.

No violations. **Complexity Tracking** section omitted (no waivers).

## Project Structure

### Documentation (this feature)

```text
specs/008-demo-polish/
├── plan.md              # This file
├── research.md          # Phase 0 output — Makefile portability, lean-check command shape, runbook drift inventory, compose race inventory
├── data-model.md        # Phase 1 output — entities are doc artifacts and CI artifacts, not DB rows
├── quickstart.md        # Phase 1 output — how to run the lean-check locally; how to capture the three demo screenshots
├── contracts/
│   └── lean-image-audit-cli.md   # Contract for scripts/check_lean_images.sh (args, exit codes, output format)
└── tasks.md             # Phase 2 output (/speckit-tasks command)
```

### Source Code (repository root)

This feature edits and adds files at the repo root and under `scripts/` and `.github/`. No `app/`, `modelserver/`, `guardrails/`, `frontend/`, or `admin/` code is modified.

```text
README.md                          # EDIT — add "Embed the widget" section
RUNBOOK.md                         # EDIT — rewrite Demo Flow as 9 numbered concrete steps; add `pytest tests/smoke/` line
docker-compose.yml                 # EDIT (only if audit finds a real race) — currently has healthchecks
                                   # on api/modelserver/guardrails; audit confirms or fixes depends_on chains
.github/workflows/ci.yml           # EDIT — add `lean-image-audit` job between lint-test-build and the eval jobs
Makefile                           # NEW — single target `lean-image-audit` invokes the script below
scripts/check_lean_images.sh       # NEW — runs `pip list` inside modelserver and guardrails images;
                                   # exits non-zero with "<image>: forbidden package <name>" on any match
                                   # of ^(torch|transformers)\b
DECISIONS.md                       # APPEND (required) — adding a CI job is "changing Docker/CI behavior",
                                   # which constitution §Development Workflow lists as a major decision
                                   # that MUST be recorded. See tasks.md T019.
```

**Structure Decision**: Use the existing single-project layout. The lean-check is a one-file shell script under `scripts/` (consistent with `scripts/check_threshold.py`, `scripts/smoke_check.py`, `scripts/seed_tenants.py`, `scripts/vault_seed.py`). The Makefile is the developer-facing entry point and also the CI invocation point, so developers and CI run the *same* command.

## Complexity Tracking

> No violations — section intentionally empty.
