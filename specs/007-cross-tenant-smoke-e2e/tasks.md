---
description: "Task list for feature 007-cross-tenant-smoke-e2e"
---

# Tasks: Cross-Tenant Smoke E2E

**Input**: Design documents in [specs/007-cross-tenant-smoke-e2e/](./)
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/)

**Tests**: The feature IS a test suite. There are no separate "tests for the tests" — each `test_*` function in `tests/smoke/test_cross_tenant_e2e.py` is itself the deliverable. No TDD wrapper layer is added; that would just push the smoke-test responsibility down one level.

**Organization**: Tasks are grouped by the three user stories in [spec.md](spec.md). Foundational tasks (Phase 2) are the docker-compose healthchecks and `depends_on` hardening — without them, every story's tests are flaky. The CI orchestration belongs to Story 3.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: can run in parallel (different files, no in-phase dependencies)
- **[Story]**: which user story this task belongs to (US1, US2, US3)
- File paths are absolute relative to repo root

## Path Conventions

Single-project backend layout. The full delta for this feature:

```text
tests/smoke/test_cross_tenant_e2e.py   # NEW
scripts/smoke_check.py                 # REWRITTEN
docker-compose.yml                     # MODIFIED (Amer-owned protected file)
.github/workflows/ci.yml               # MODIFIED (Amer-owned protected file)
DECISIONS.md                           # APPENDED
```

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm prerequisites; this feature adds no new third-party libraries.

- [X] T001 Verify [pyproject.toml](../../pyproject.toml) dev extras already include `asyncpg`, `httpx`, `pyjwt`, and `pytest-asyncio` (confirmed during planning); if any drift has occurred, add the missing entry. No source code change is required when the verification passes.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Make the Compose stack come up reliably so every story's tests can run without flake. Until these tasks are complete, no probe in Stories 1–3 is meaningful.

**⚠️ CRITICAL**: No user-story task can begin until this phase is complete.

- [X] T002 Add healthchecks to [docker-compose.yml](../../docker-compose.yml) for `api`, `modelserver`, `guardrails`, and `redis` per [contracts/docker-healthcheck.md](contracts/docker-healthcheck.md) (commands, interval=5s, timeout=5s, retries=12, start_period=5s for the three HTTP services; `redis-cli ping` for redis).
- [X] T003 Update `depends_on` in [docker-compose.yml](../../docker-compose.yml) so `api` waits on `modelserver.service_healthy` and `guardrails.service_healthy` (currently `service_started`); keep `db`/`vault`/`redis` conditions as already specified in [contracts/docker-healthcheck.md](contracts/docker-healthcheck.md).
- [X] T004 Delete the placeholder [tests/smoke/test_stack_placeholder.py](../../tests/smoke/test_stack_placeholder.py); its sole `assert True` is being replaced by real probes.
- [X] T005 Create the skeleton of [tests/smoke/test_cross_tenant_e2e.py](../../tests/smoke/test_cross_tenant_e2e.py) — `# Owner: Amer` header, module docstring referencing [spec.md](spec.md), env-variable readers (`SMOKE_API_BASE`, `SMOKE_DB_DSN`, `SMOKE_E2E_REQUIRE_FULL_STACK`, `WIDGET_JWT_SECRET`), and three module-scoped pytest fixtures: a shared `httpx.AsyncClient`, an `asyncpg` connection (lazy), and the `SmokeTenantFixture` dataclass from [data-model.md](data-model.md) E1.
- [X] T006 In the same file, add a `_redact(s: str) -> str` helper plus a phase-gate decorator (`require_full_stack`) that wraps probes in `pytest.mark.xfail(strict=True, reason="phase-N dependency pending")` when `SMOKE_E2E_REQUIRE_FULL_STACK="0"`, per [research.md](research.md) R6.

**Checkpoint**: `docker compose up -d --wait` returns healthy for every service; the pytest module imports clean with `pytest --collect-only`. User-story probes can now be added.

---

## Phase 3: User Story 1 — Prove Cross-Tenant Content Isolation in CI (Priority: P1) 🎯 MVP

**Goal**: Two tenants are provisioned, each seeded with disjoint CMS markers; identical chat questions return tenant-scoped answers with no cross-leak; a JWT bearing a forged origin claim is rejected with 403.

**Independent Test**: Run `pytest tests/smoke/test_cross_tenant_e2e.py::test_cross_tenant_content_isolation_A tests/smoke/test_cross_tenant_e2e.py::test_cross_tenant_content_isolation_B tests/smoke/test_cross_tenant_e2e.py::test_forged_origin_returns_403 -v` against a live stack. All three pass on a non-leaking system; the forged probe in particular must return 403, not a benign 200 with a generic answer.

### Implementation for User Story 1

- [X] T007 [US1] In [tests/smoke/test_cross_tenant_e2e.py](../../tests/smoke/test_cross_tenant_e2e.py), implement `provision_tenant(client, name) -> SmokeTenantFixture` — POSTs to `/tenants`, PUTs `/widgets/config` with one `allowed_origin`, captures `tenant_id`/`widget_id`. Uses canonical `tenant_id` / `widget_id` per [CONTRACT.md](../../CONTRACT.md) §6.
- [X] T008 [US1] Add `seed_cms_pages(client, fixture, keyword)` that POSTs two pages to `/cms/pages` whose body text contains `keyword` (`"alpha-cookies"` or `"bravo-pastries"`) twice each; returns the two `page_id`s for storage on the fixture.
- [X] T009 [US1] Add `obtain_widget_token(client, fixture)` that POSTs to `/widgets/token` with `widget_id` + `Origin: <fixture.origin>` and stores `token` + `session_id` on the fixture; assert token is a valid HS256 JWT whose `tenant_id` claim equals `fixture.tenant_id`.
- [X] T010 [US1] Add `ask_chat(client, fixture, message) -> (status, body)` helper that POSTs `/chat` with `Authorization: Bearer <token>` and returns `(response.status_code, response.json())`. Bounded retry loop (30 s, 1 s sleep) on first call per US1 fixture, used as the RAG-ready readiness signal per [research.md](research.md) R2.
- [X] T011 [US1] Implement `test_cross_tenant_content_isolation_A` — provisions both tenants, seeds them, asks the chat question as Tenant A, asserts `"alpha-cookies"` substring present and `"bravo-pastries"` substring absent. Decorated with `@require_full_stack`.
- [X] T012 [US1] Implement `test_cross_tenant_content_isolation_B` — reuses the same two provisioned fixtures (via a module-scoped `_tenants` fixture set up by T011 or a shared setup), asks as Tenant B, asserts `"bravo-pastries"` present and `"alpha-cookies"` absent. Decorated with `@require_full_stack`.
- [X] T013 [US1] Add `mint_forged_jwt(fixture_a, forged_origin) -> str` that synthesizes an HS256 JWT with `tenant_id=fixture_a.tenant_id`, `widget_id=fixture_a.widget_id`, `origin=forged_origin`, `session_id=<new uuid>`, `exp=<now+5min>` signed with `widget_settings().widget_jwt_secret`. Per [research.md](research.md) R1.
- [X] T014 [US1] Implement `test_forged_origin_returns_403` — mints a forged JWT with Tenant B's origin, sends `/chat` with `Authorization: Bearer <forged>` and `Origin: <fixture_b.origin>`, asserts `response.status_code == 403`. Decorated with `@require_full_stack`.

**Checkpoint**: Story 1 stands alone — running just these three probes proves cross-tenant content isolation. This is the MVP.

---

## Phase 4: User Story 2 — Verify Lead Capture and Escalation Stay Tenant-Scoped (Priority: P2)

**Goal**: The two write-side agent tools (`capture_lead`, `escalate`) produce records that are tenant-scoped at the storage layer and surface in the audit log.

**Independent Test**: Run `pytest tests/smoke/test_cross_tenant_e2e.py -k "lead or escalate or audit" -v` against a live stack. Lead/ticket ids are returned over HTTP; corresponding rows visible in Postgres only under Tenant A's `tenant_id`; audit-log entry recorded for the escalation.

### Implementation for User Story 2

- [X] T015 [US2] In [tests/smoke/test_cross_tenant_e2e.py](../../tests/smoke/test_cross_tenant_e2e.py), add `drive_chat_to_lead_capture(client, fixture_a) -> str` helper — sends a message designed to trigger `capture_lead` (e.g., "please contact me at alice@example.com about alpha-cookies"); asserts the response's `used_tools` includes `"capture_lead"`; returns the `lead_id` from the chat response per [CONTRACT.md](../../CONTRACT.md) §2.7. If the response body doesn't surface `lead_id`, fall back to scanning the most recent row in `leads` for `fixture_a.tenant_id` (per [research.md](research.md) "Open follow-ups"). **FR-012 note:** this helper uses the same `Authorization: Bearer <widget-token>` path a visitor would; it does not call any internal-only or service-to-service endpoint. The subsequent DB readback in T016 is a passive read-only observation scoped by `tenant_id`, not an auth bypass.
- [X] T016 [US2] Add `db_select_lead(dsn, lead_id, tenant_id) -> dict | None` helper that opens an asyncpg connection, runs `SELECT tenant_id, status FROM leads WHERE lead_id=$1 AND tenant_id=$2`, and returns the row (or None). Read-only; closes connection on exit. Per [research.md](research.md) R3.
- [X] T017 [US2] Implement `test_lead_capture_scoped_to_tenant_A` — drives lead capture under Tenant A; asserts `db_select_lead(..., fixture_a.tenant_id)` returns one row whose `tenant_id == fixture_a.tenant_id`. Decorated with `@require_full_stack`.
- [X] T018 [US2] Implement `test_lead_not_visible_to_tenant_B` — re-uses the same `lead_id`; asserts `db_select_lead(..., fixture_b.tenant_id)` returns `None`. This is the negative-side proof that the row is not merely tagged but truly scoped. Decorated with `@require_full_stack`.
- [X] T019 [US2] Add `drive_chat_to_escalate(client, fixture_a) -> str` helper — sends a message designed to trigger `escalate` (e.g., "I need to speak to a human now"); asserts `used_tools` includes `"escalate"`; returns the `ticket_id`. **FR-012 note:** same constraint as T015 — uses the public widget-token-authenticated `/chat` path, no internal-only endpoints; the audit-log readback in T020 is passive and tenant-scoped.
- [X] T020 [US2] Add `db_select_audit_log(dsn, tenant_id, ticket_id) -> dict | None` that runs `SELECT actor_role, action, metadata FROM audit_logs WHERE tenant_id=$1 AND metadata->>'ticket_id'=$2`.
- [X] T021 [US2] Implement `test_escalate_returns_ticket_for_A` — drives escalation; asserts `ticket_id` is a valid UUID string and the chat response's `route == "escalate"` per [CONTRACT.md](../../CONTRACT.md) §2.4. Decorated with `@require_full_stack`.
- [X] T022 [US2] Implement `test_audit_log_entry_exists_for_A` — reuses the same `ticket_id`; asserts `db_select_audit_log(..., fixture_a.tenant_id, ticket_id)` returns a row whose `action` references escalation. Decorated with `@require_full_stack`.

**Checkpoint**: Stories 1 AND 2 both pass independently. Write-side isolation is now verified end-to-end alongside read-side.

---

## Phase 5: User Story 3 — Smoke Test Runs Reliably in CI and Locally (Priority: P3)

**Goal**: One command brings the stack up, runs the suite, and tears the stack down — identically in CI and on a developer laptop. Failures produce useful artifacts.

**Independent Test**: From a clean checkout: `docker compose up -d --wait && python scripts/smoke_check.py && docker compose down -v` exits 0 (or exits non-zero with a readable probe failure). In CI, the `smoke-e2e` job appears as a separate check on the PR.

### Implementation for User Story 3

- [X] T023 [US3] Rewrite [scripts/smoke_check.py](../../scripts/smoke_check.py) per [contracts/smoke-runner-cli.md](contracts/smoke-runner-cli.md): argparse `--api-base`, `--db-dsn`, `-k`, `-v` flags; pre-flight `GET /health` probe (30 s budget); `os.execvp` into pytest with `tests/smoke/test_cross_tenant_e2e.py` plus forwarded args; exit codes 0/1/2/3 per the contract. `# Owner: Amer` header preserved.
- [X] T024 [US3] Add the `smoke-e2e` job to [.github/workflows/ci.yml](../../.github/workflows/ci.yml) per [contracts/ci-smoke-e2e-job.md](contracts/ci-smoke-e2e-job.md): `needs:` includes `lint-test-build` + all five eval jobs; `runs-on: ubuntu-latest`; `timeout-minutes: 15`; `env: SMOKE_E2E_REQUIRE_FULL_STACK: "1"`; steps for checkout, Python setup, `uv pip install`, `docker compose up -d --wait`, `python scripts/smoke_check.py -v`, log capture on failure, artifact upload on failure, `docker compose down -v` with `if: always()`.
- [X] T025 [US3] Validate end-to-end against a live local stack per [quickstart.md](quickstart.md): run the one-command form; observe exit code; observe `docker compose down -v` cleans up all named volumes. Until Phases 1/2/5/6 ship, this validation runs with `SMOKE_E2E_REQUIRE_FULL_STACK=0` and expects `xfail` markers — record observed counts in the PR description.

**Checkpoint**: The smoke gate appears on every PR; teardown always runs; local and CI behavior match.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T026 In [tests/smoke/test_cross_tenant_e2e.py](../../tests/smoke/test_cross_tenant_e2e.py), add a session-scoped pytest hook that writes `smoke-report.json` per [data-model.md](data-model.md) E3 (probes, timing, redacted observed-strings). Used by the CI artifact upload step.
- [X] T027 Append a `DECISIONS.md` entry documenting: (a) why the smoke gate runs after evals (research R7); (b) why direct asyncpg readback is acceptable for audit-log verification (constitution post-design review); (c) the `SMOKE_E2E_REQUIRE_FULL_STACK` phase-gate flag and the contract that whoever lands a Phase 1/2/5/6 slice must flip it back to `"1"`.
- [X] T028 Verify [CLAUDE.md Pre-Merge Checklist](../../CLAUDE.md) line "Smoke test pass rate: 1.0" is satisfied by this PR's CI run (or notes the xfail-mode reading if dependencies are still pending).
- [X] T029 Run the [quickstart.md](quickstart.md) Troubleshooting table commands as a final sanity check (`docker compose logs <service>`, `docker compose down -v` after a deliberately failed run) and update the table if any output drifted.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 — no upstream dependency.
- **Foundational (Phase 2)**: T002, T003, T004, T005, T006 — all depend on T001; T005 depends on T004 (file rename hygiene); T006 depends on T005 (extends the same file). **Phase 2 blocks every story phase.**
- **User Stories (Phase 3+)**: all depend on Phase 2.
  - Story 1 (T007–T014) must finish before Story 2 starts, because Story 2 reuses Story 1's tenant fixtures and helpers.
  - Story 3 (T023–T025) depends on the test file existing (Phase 2 / Story 1) but is otherwise independent — it can run in parallel with Story 2 once Story 1's skeleton is in place.
- **Polish (Phase 6)**: depends on all three user stories.

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2. MVP boundary.
- **US2 (P2)**: Can start after US1 (shares fixtures and helpers in the same file). Conceptually independent — passes or fails on its own merits — but writes append to the same test file as US1, so sequencing within the file matters.
- **US3 (P3)**: Can start in parallel with US2 once US1 has produced a runnable suite — US3 only touches `scripts/smoke_check.py` and `.github/workflows/ci.yml`, neither of which collide with US1/US2 file edits.

### Within Each User Story

- Helpers first, then test functions that use them (T007–T010 before T011/T012/T014 in US1; T015/T016 before T017/T018; T019/T020 before T021/T022).
- Decorate every probe with `@require_full_stack` until the dependency phase ships.
- Commit after each completed task or logical group.

### Parallel Opportunities

- T002 and T003 touch the same file (`docker-compose.yml`); **not** parallelizable — do them in one PR-friendly edit pass.
- T023 (`scripts/smoke_check.py`) and T024 (`.github/workflows/ci.yml`) touch different files; can be done in parallel once the test file is runnable.
- T026, T027, T028, T029 in Polish all touch different files; can be done in parallel.

---

## Parallel Example: User Story 3

```bash
# Once Phase 3 (US1) produces a runnable test file:
Task: "T023 [US3] Rewrite scripts/smoke_check.py per contracts/smoke-runner-cli.md"
Task: "T024 [US3] Add smoke-e2e job to .github/workflows/ci.yml per contracts/ci-smoke-e2e-job.md"
# Different files, no in-phase dependency.
```

---

## Implementation Strategy

### MVP first (User Story 1 only)

1. T001 (Setup).
2. T002–T006 (Foundational — healthchecks, depends_on, file skeleton).
3. T007–T014 (US1 — cross-tenant content + forged-origin probes).
4. **Stop, validate**: run the three US1 tests against `docker compose up -d --wait`. If they all pass (or all xfail with `SMOKE_E2E_REQUIRE_FULL_STACK=0`), the MVP is in.
5. Open the PR for review. Cross-owner review: **Hiba** (tenant_id query in audit-log readback once T020 lands; mention up front for context), **Ayoub** (none — no guardrails or Vault changes here), **Amer** (own review of compose + workflow protected files).

### Incremental delivery

1. MVP merged → Story 2 (write-side isolation) on a follow-up branch.
2. Story 2 merged → Story 3 (CI job + script wrapper).
3. Story 3 merged → Polish.

Each step is a green CI on its own.

### Parallel team strategy

Single-owner feature (Amer). No team parallelism beyond the parallel opportunities listed above within a single developer's session.

---

## Notes

- The "Smoke test pass rate: 1.0" line in [CLAUDE.md Pre-Merge Checklist](../../CLAUDE.md) is what this feature operationalizes.
- The phase-gate flag (`SMOKE_E2E_REQUIRE_FULL_STACK`) is the **only** allowed form of skip in this suite. `pytest.skip()` is forbidden by design — it silently passes, which is the failure mode this whole feature exists to fix.
- Canonical IDs used everywhere: `tenant_id`, `widget_id`, `session_id`, `lead_id`, `ticket_id`. No `business_id`, `org_id`, `customer_id`, etc., per [CONTRACT.md](../../CONTRACT.md) §6.
- Cross-owner review reminder: `docker-compose.yml` and `.github/workflows/ci.yml` are Amer-owned protected files; the direct-DB audit-log readback in T020/T022 warrants a Hiba review per [CONTRACT.md](../../CONTRACT.md) §4 even though no production-side audit_logs schema is being touched.
