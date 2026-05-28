# Implementation Plan: Cross-Tenant Smoke E2E

**Branch**: `007-cross-tenant-smoke-e2e` | **Date**: 2026-05-28 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/007-cross-tenant-smoke-e2e/spec.md`

## Summary

Replace [tests/smoke/test_stack_placeholder.py](../../tests/smoke/test_stack_placeholder.py) and the
echo-only [scripts/smoke_check.py](../../scripts/smoke_check.py) with a real end-to-end pytest
suite that proves tenant isolation against the live Docker Compose stack. The suite provisions
two tenants (alpha, bravo), seeds CMS content with disjoint markers, drives the public chat path
via httpx using real widget tokens, and asserts: each tenant only sees its own content; forged-origin
tokens are rejected with 403; lead capture and escalate produce tenant-scoped records visible in
the audit log. A new `smoke-e2e` GitHub Actions job brings the stack up, waits for healthchecks,
runs the suite, and tears the stack down on completion. `scripts/smoke_check.py` becomes a thin
wrapper that invokes the same pytest module — one suite, two invocation paths (CI and local).

The feature also adds missing Docker Compose healthchecks for `api`, `modelserver`, and
`guardrails`, and hardens `depends_on` ordering so the readiness wait is reliable rather than
timing-based.

## Technical Context

**Language/Version**: Python 3.11 (test suite, smoke runner)
**Primary Dependencies**: pytest 8.x, httpx (async), pyjwt (forged-token construction),
  asyncpg or psycopg (audit-log readback), `docker compose` v2 CLI (CI invocation only)
**Storage**: PostgreSQL + pgvector running inside the Compose stack (already configured); the
  smoke runner connects to the host-published port for audit-log verification only — production
  routes are exercised over HTTP, never via direct DB writes.
**Testing**: pytest with `pytest-asyncio`; one file at `tests/smoke/test_cross_tenant_e2e.py`.
  No mocks: the suite talks to a real, running stack on `http://localhost:8000` (API),
  `http://localhost:8010` (modelserver), `http://localhost:8020` (guardrails).
**Target Platform**: Linux GitHub-hosted runner (`ubuntu-latest`) for CI; macOS/Linux developer
  laptops for local invocation. Windows hosts run the suite via the same `docker compose` CLI.
**Project Type**: Web-service backend (FastAPI). No new src layout introduced — the change is
  test, script, compose, and workflow files only.
**Performance Goals**: Whole-suite wall time < 10 minutes on `ubuntu-latest`, including stack
  cold-start. Each individual probe step < 30 s once the stack is healthy.
**Constraints**: No flakiness across 20 consecutive runs (SC-003); zero orphan containers,
  networks, or volumes after teardown (SC-005); identical pass/fail locally vs. CI (SC-006).
**Scale/Scope**: Two tenants, four CMS pages total, ≤ 6 chat requests, one lead, one escalation
  per run. The suite is a probe, not a load test.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **Principle I (Tenant Isolation):** the smoke test *verifies* tenant isolation; it does
      not weaken it. No new tenant-owned table is introduced. The audit-log readback uses a
      tenant-filtered query (`WHERE tenant_id = $1`) executed by the test against an already-RLS-protected
      table. `tenant_id` in every probe is derived from a server-issued widget token, never injected by
      the test into a request body.
- [x] **Principle II (Layered Architecture):** the suite only consumes public HTTP routes; it
      adds no new routes, services, or repositories. The one direct-DB readback (audit log) is a
      test-side observation, not application logic, and is restricted to the smoke module.
- [x] **Principle III (Bounded Agent):** no new agent tool. The suite exercises `rag_search`
      indirectly via `/chat`, and `capture_lead` / `escalate` indirectly via the chat-driven tool
      calls. The current set (`rag_search`, `capture_lead`, `escalate`) is preserved.
- [x] **Principle IV (Defense-in-Depth Auth):** the forged-origin probe specifically validates
      that a JWT bearing a mismatched origin claim is rejected server-side. The HS256 secret used
      to mint the forged token is read from the same `widget_settings()` accessor used by the
      production token service in test mode — no secret is hardcoded, no `.env` is committed, no
      Vault credential is exposed.
- [x] **Principle V (Lean Serving & Redaction):** the suite adds no dependencies to
      `modelserver` or `guardrails` images. The healthcheck commands added to those services use
      tools already present in the base images (`curl` from the Python slim base, or `wget`).
- [x] **Principle VI (Phased Build):** this feature is Phase 10 (CI/CD & eval gates, Amer).
      It transitively depends on slices owned by Hiba (Phase 1: real `/tenants`), Nasser
      (Phase 2/5: real `/cms/pages` + RAG ingest + agent tools), and Ayoub (Phase 6: guardrails
      healthcheck endpoint). The plan introduces a single environment switch
      (`SMOKE_E2E_REQUIRE_FULL_STACK`) so the suite **runs and fails loudly** when those slices
      land, but can be temporarily marked `xfail` until they do — never silently skipped.
- [x] **Principle VII (Clean & Simple Code):** one pytest module, one thin script wrapper,
      one CI job, one compose patch. No frameworks, no fixtures factory, no helpers package.
      Canonical IDs used everywhere: `tenant_id`, `widget_id`, `session_id`, `lead_id`,
      `ticket_id` (per `CONTRACT.md` §6).

No unchecked boxes → no Complexity Tracking entries needed.

## Project Structure

### Documentation (this feature)

```text
specs/007-cross-tenant-smoke-e2e/
├── plan.md                        # This file
├── spec.md                        # Feature spec (already written)
├── research.md                    # Phase 0 output
├── data-model.md                  # Phase 1 output (test-side entities only)
├── quickstart.md                  # Phase 1 output (local run instructions)
├── contracts/
│   ├── smoke-runner-cli.md        # scripts/smoke_check.py contract
│   ├── docker-healthcheck.md      # healthcheck command per service
│   └── ci-smoke-e2e-job.md        # GitHub Actions job contract
└── checklists/
    └── requirements.md            # Already written by /speckit-specify
```

### Source Code (repository root)

This feature does **not** add new source modules. The full delta is:

```text
tests/smoke/
├── test_cross_tenant_e2e.py       # NEW — the suite (Owner: Amer)
└── test_stack_placeholder.py      # DELETED — no longer needed

scripts/
└── smoke_check.py                 # REWRITTEN — thin pytest wrapper (Owner: Amer)

docker-compose.yml                 # MODIFIED — healthchecks for api/modelserver/guardrails,
                                   #            depends_on conditions hardened (Owner: Amer)

.github/workflows/ci.yml           # MODIFIED — new smoke-e2e job (Owner: Amer)

specs/007-cross-tenant-smoke-e2e/  # NEW — this spec/plan/research bundle
```

**Structure Decision**: Single-project backend, no layout changes. The smoke test is intentionally
implemented as one file with no shared helper module: the suite is short, the steps are linear,
and a future reader can audit tenant-isolation behavior without chasing fixtures across files
(Principle VII).

## Complexity Tracking

> No constitutional violations. This section intentionally left empty.

---

## Phase 0 — Research

See [research.md](research.md). Resolved questions:

- **R1 — Forged-origin construction:** mint a fresh HS256 JWT in-test using
  `widget_settings().widget_jwt_secret`, with the forged `origin` claim; do **not** tamper with
  the issued token's bytes. This mirrors a realistic threat (attacker who knows the secret format)
  and avoids brittle signature-stripping.
- **R2 — RAG ingestion trigger:** call Nasser's `POST /cms/pages` which (per Phase 2) triggers
  synchronous ingest on commit. The test then polls `retrieve_chunks(tenant_id, "cookies")`
  via an internal `/__test__/rag` endpoint **only if Nasser exposes one** — otherwise the test
  polls by repeatedly asking the chat question and treating "alpha-cookies" appearing in the
  answer as the readiness signal, with a bounded retry budget (30 s).
- **R3 — Lead and audit-log readback:** the test opens an asyncpg connection to the
  Compose-published Postgres port and runs two read-only queries (`SELECT … FROM leads WHERE
  lead_id = $1`, `SELECT … FROM audit_logs WHERE ticket_id = $1`). Both queries include
  `tenant_id = $tenant_a_id` as a filter to confirm scope.
- **R4 — Healthcheck commands:**
  - `api`: `curl -fsS http://localhost:8000/health || exit 1`
  - `modelserver`: `curl -fsS http://localhost:8010/health || exit 1`
  - `guardrails`: `curl -fsS http://localhost:8020/health || exit 1`
  - All three already (or will, per their respective Phase plans) expose a `/health` endpoint
    per `CONTRACT.md`; the smoke plan does not add new endpoints.
- **R5 — depends_on hardening:** `api` waits on `db.service_healthy`, `vault.service_healthy`,
  `modelserver.service_healthy`, `guardrails.service_healthy`, `redis.service_started`. The
  current compose file already waits on `db` and `vault` health but starts modelserver/guardrails
  unconditionally — this is the gap.
- **R6 — Dependency phasing:** the suite imports a `SMOKE_E2E_REQUIRE_FULL_STACK` env flag.
  Default `true` in CI once Phases 1/2/5/6 ship. Until then, the failing tests are marked
  `xfail(strict=True)` with a `# TODO(phase-N): unflag when <slice> ships` line tied to the
  blocking phase, so when the slice lands the test will fail-on-xpass and force the gate on.
- **R7 — CI job placement:** `smoke-e2e` runs *after* `lint-test-build` and the five eval
  jobs (`classifier-eval`, `rag-eval`, `agent-tool-eval`, `red-team`, `redaction-eval`) — its
  `needs:` list includes all of them. Rationale: smoke is the most expensive job; failing eval
  gates should short-circuit before paying the Compose-startup cost.

## Phase 1 — Design & Contracts

### Test-side data model

See [data-model.md](data-model.md). The suite uses three transient in-test entities:

- **`SmokeTenantFixture`**: per-tenant bundle of `tenant_id`, `widget_id`, `origin`, `token`,
  `session_id`, `seed_keyword` (e.g., `"alpha-cookies"`).
- **`ProbeOutcome`**: pass/fail record for each numbered scenario (probe id, scenario name,
  tenant, expected, observed, latency_ms).
- **`SmokeRunReport`**: aggregate of all `ProbeOutcome`s, written to stdout in the CI log and
  uploaded as an artifact if any probe fails.

None of these are persisted to the database; they exist only in the test process.

### Contracts

- [contracts/smoke-runner-cli.md](contracts/smoke-runner-cli.md) — `scripts/smoke_check.py`
  exit codes, argument shape, and how it forwards to pytest.
- [contracts/docker-healthcheck.md](contracts/docker-healthcheck.md) — healthcheck command,
  interval, timeout, retries, and `depends_on.condition` matrix.
- [contracts/ci-smoke-e2e-job.md](contracts/ci-smoke-e2e-job.md) — GitHub Actions job name,
  trigger, `needs:` graph, teardown semantics (`if: always()`).

### Quickstart

See [quickstart.md](quickstart.md). One-command local invocation:

```bash
docker compose up -d --wait
pytest tests/smoke/test_cross_tenant_e2e.py -v
docker compose down -v
```

Or equivalently via the wrapper:

```bash
docker compose up -d --wait
python scripts/smoke_check.py
docker compose down -v
```

### Agent context update

The active spec-kit feature pointer in [CLAUDE.md](../../CLAUDE.md) will be updated to point at
`specs/007-cross-tenant-smoke-e2e/plan.md` as part of this PR.

## Re-evaluated Constitution Check (post-design)

- [x] All seven principles still pass after Phase 1 design. The audit-log direct-DB readback
      (R3) was the only design choice with constitutional implications and was reviewed against
      Principle II: it is acceptable because the readback is **test code**, lives in
      `tests/smoke/`, never modifies state, and includes an explicit `tenant_id` filter that
      mirrors what the application-side repository would do. Hiba is the audit-log owner and
      will review this PR per `CONTRACT.md` §4.

## Next Step

`/speckit-tasks` to generate the dependency-ordered task list for `tests/smoke/test_cross_tenant_e2e.py`,
`scripts/smoke_check.py`, `docker-compose.yml`, and the new `smoke-e2e` CI job.
