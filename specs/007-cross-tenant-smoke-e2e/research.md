# Research: Cross-Tenant Smoke E2E

**Date**: 2026-05-28
**Plan**: [plan.md](plan.md)

Resolves every NEEDS-CLARIFICATION-class question identified in the plan's Technical Context.
Each decision is recorded with rationale and the alternatives that were considered and rejected.

---

## R1 — How to construct the forged-origin negative probe

**Decision:** Mint a fresh HS256 JWT inside the test using the shared widget secret from
`app.services.widget_settings.widget_settings().widget_jwt_secret`, with `tenant_id` = Tenant A's
id, `widget_id` = Tenant A's widget id, `session_id` = a freshly generated session id, `origin`
= Tenant B's registered origin (the *forged* claim), and a near-term `exp`. Send it to
`POST /chat` with `Origin: <Tenant B's origin>`. Assert the response status is 403.

**Rationale:** This isolates the property under test (server-side origin validation) without
depending on tooling that strips or alters JWT signatures. It models a credible threat — an
attacker who has captured one valid token and tries to reuse its secret material to forge a new
one with different claims — and confirms the server rejects on the origin mismatch.

**Alternatives rejected:**
- *Tamper with the issued token's payload and re-sign:* same outcome, more brittle (encoding
  details leak into the test).
- *Send Tenant A's real token but with `Origin: <Tenant B>` in the HTTP header:* this tests
  a different layer (header-vs-claim consistency check) and could pass for the wrong reason if
  the server only validates the token claim. Out of scope for *this* probe.

---

## R2 — How to trigger and confirm RAG ingestion before the chat probe

**Decision:** The test seeds CMS pages via `POST /cms/pages` and assumes synchronous ingestion
on commit, which is the Phase-2 contract documented under `CONTRACT.md` §2.7. After the seed
calls return 201, the test issues the chat question in a bounded retry loop (max 30 s, 1 s
between tries) and treats the first response containing the tenant's keyword as the readiness
signal. The retry loop exists only to absorb embedder warm-up jitter on the first run.

**Rationale:** Calling an internal `retrieve_chunks` function from the test would bypass the
HTTP boundary the smoke suite is supposed to exercise. The chat-driven probe is the same path
a real visitor takes, and the retry budget is small enough to surface real regressions but large
enough to absorb cold-start.

**Alternatives rejected:**
- *Sleep N seconds after seeding:* fixed sleeps are the textbook smoke-test flakiness source.
- *Call `app.rag.retrieve_chunks(...)` directly from the test:* bypasses HTTP, RLS context
  setup, and tenant scoping at the route layer — exactly the layers we want to verify.
- *Add a dedicated `/__test__/rag-ready` endpoint:* surface-area expansion in production
  builds for a problem that retry resolves.

---

## R3 — How to verify the lead is tenant-scoped and the audit log entry exists

**Decision:** The test opens a single asyncpg connection to the Compose-published Postgres
port (default `localhost:5432`, credentials from the same env as the API container) and runs
two read-only queries after the probe:

```sql
SELECT tenant_id, status FROM leads
  WHERE lead_id = $1 AND tenant_id = $2;

SELECT actor_role, action, metadata FROM audit_logs
  WHERE tenant_id = $1 AND metadata->>'ticket_id' = $2;
```

Both queries are scoped by `tenant_id` and confirm the row exists with the expected scope.
A second negative query confirms Tenant B's tenant_id does **not** return the same lead row.

**Rationale:** A read-only test query against published Postgres is the simplest path that
confirms tenant scoping at the data layer without inventing a new admin endpoint. The query
mirrors what the production repository function would do (per CONTRACT.md §2.6) and exercises
the actual `audit_logs` table that Hiba's slice writes to.

**Alternatives rejected:**
- *Call `TenantRepository.list_audit_logs(...)` directly:* the repository is bound to an async
  session that the test process doesn't own; recreating that wiring duplicates the production
  composition root for negligible benefit.
- *Add a `GET /tenants/{id}/audit-logs` admin endpoint solely for the smoke test:* surface-area
  expansion. Hiba may add one anyway as part of Phase 1 — if and when she does, the test can be
  refactored to use it (one-line change).
- *Trust the agent's tool-call return values without reading back:* the whole point is to verify
  what was *stored*, not what was *reported*.

---

## R4 — Healthcheck command per service

**Decision (revised during implementation, 2026-05-28):**

| Service       | Healthcheck command                                                                                                          | interval | timeout | retries |
|---------------|------------------------------------------------------------------------------------------------------------------------------|----------|---------|---------|
| `api`         | `python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/openapi.json', timeout=2)" \|\| exit 1`     | 5 s      | 5 s     | 12      |
| `modelserver` | `python -c "import urllib.request; urllib.request.urlopen('http://localhost:8010/openapi.json', timeout=2)" \|\| exit 1`     | 5 s      | 5 s     | 12      |
| `guardrails`  | `python -c "import urllib.request; urllib.request.urlopen('http://localhost:8020/openapi.json', timeout=2)" \|\| exit 1`     | 5 s      | 5 s     | 12      |
| `db`          | (already present) `pg_isready -U postgres -d concierge`                                                                      | 5 s      | 5 s     | 10      |
| `vault`       | (already present) `vault status`                                                                                              | 5 s      | n/a     | 10      |
| `redis`       | `redis-cli ping \| grep -q PONG`                                                                                              | 5 s      | 3 s     | 10      |

**Rationale:** The original draft of this section assumed a `curl http://localhost:PORT/health`
form, but implementation discovered two compounding issues: (1) the `python:3.11-slim` base
image used by `api`, `modelserver`, and `guardrails` does **not** ship `curl`; and (2) none of
the three FastAPI services actually exposes a `/health` route today — they expose only the
contract endpoints in `CONTRACT.md` §§2.6, 2.8, 2.9. Rather than (a) add `curl` to three slim
images (image-weight bloat, against Principle V) or (b) add `/health` routes to three
cross-owner files (Hiba's `app/main.py`, Ayoub's `modelserver/main.py` and `guardrails/main.py`,
requiring approvals for what should be a healthcheck-only concern), the healthchecks now probe
`/openapi.json`. Every FastAPI app exposes it by default; a 200 here proves the process is up
*and* the route stack is mounted (strictly stronger than a hand-rolled `/health` endpoint,
which can be hardcoded to return 200 without any real routes). The 12-retry budget × 5 s
interval gives each service a full minute to come up before Compose declares it unhealthy.

**Alternatives rejected:**
- *TCP-port-open check:* a TCP-up service can still be returning 500 to `/health`. Not enough.
- *No healthcheck, longer `sleep` in CI:* fixed sleep flakes under runner load (see Story 3
  in spec.md).

---

## R5 — `depends_on` ordering

**Decision:** `api`'s `depends_on` map becomes:

```yaml
depends_on:
  db:           { condition: service_healthy }
  vault:        { condition: service_healthy }
  redis:        { condition: service_started }
  modelserver:  { condition: service_healthy }
  guardrails:   { condition: service_healthy }
```

The current file waits on `modelserver` and `guardrails` only via `service_started`, which
returns immediately after the container PID starts and *before* the process is accepting
connections. That is the root of any flakiness the current smoke test would have once it does
real work.

**Rationale:** Compose's wait-for-healthy is the cheapest correct primitive available. Once
the healthchecks from R4 are in place, switching the condition is one line per service.

**Alternatives rejected:**
- *Wait-for-it / dockerize external scripts:* duplicates what `condition: service_healthy`
  already provides.
- *Application-side retry on first request:* pushes a Compose concern into application code.

---

## R6 — How to behave while upstream phases are still in flight

**Decision:** The suite reads `SMOKE_E2E_REQUIRE_FULL_STACK` from env (default `"1"`). When set
to `"0"`, the probes that depend on not-yet-shipped slices (Hiba's real `/tenants`, Nasser's
real `/cms/pages` + agent tool calls, Ayoub's guardrails `/health`) are marked
`@pytest.mark.xfail(strict=True, reason="phase-N dependency pending")`. When the slice ships,
the previously-xfail probe will pass, pytest will report `XPASS(strict)` as a failure, and the
PR introducing the slice must flip the env flag back to `"1"`. This is the **only** allowed
form of "skip" — there is no silent bypass.

**Rationale:** This enforces Principle VI (Phased Build): the suite is in-tree and runs every
PR, but it doesn't block Phase 1/2/5/6 owners from making partial progress, and it *forces* the
gate on the moment the last dependency lands.

**Alternatives rejected:**
- *Wait to write the suite until everything ships:* leaves a placeholder smoke test as the
  merge gate for the entire interim, which is exactly the problem this feature exists to fix.
- *Plain `pytest.skip(...)`:* silently passing is the failure mode this design rejects.
- *Hand-maintained "is feature X ready?" flags:* duplicates state already encoded in the
  passing/failing assertion.

---

## R7 — CI job placement and teardown

**Decision:** A new job `smoke-e2e` in [.github/workflows/ci.yml](../../.github/workflows/ci.yml):

```yaml
smoke-e2e:
  needs:
    - lint-test-build
    - classifier-eval
    - rag-eval
    - agent-tool-eval
    - red-team
    - redaction-eval
  if: github.event_name == 'pull_request' || (github.event_name == 'push' && github.ref == 'refs/heads/main')
  runs-on: ubuntu-latest
  timeout-minutes: 15
  steps:
    - uses: actions/checkout@v4
    - name: Bring stack up
      run: docker compose up -d --wait
    - name: Run smoke suite
      run: python scripts/smoke_check.py
    - name: Tear stack down
      if: always()
      run: docker compose down -v
    - name: Upload smoke artifacts
      if: failure()
      uses: actions/upload-artifact@v4
      with:
        name: smoke-e2e-logs
        path: |
          smoke-report.json
          docker-compose.logs
```

**Rationale:** Smoke is the most expensive single job in the matrix because of the Compose
cold-start, so it runs last and only when everything upstream is green. `docker compose up
-d --wait` blocks on healthchecks (now reliable per R4/R5). `if: always()` on the teardown
step guarantees no orphan containers, networks, or volumes (SC-005). The `-v` flag in
`docker compose down` removes named volumes for full hygiene between runs. Artifacts upload
only on failure so we don't bloat green runs.

**Alternatives rejected:**
- *Run smoke before evals:* burns Compose-startup cost on PRs that will fail evals anyway.
- *Single combined eval + smoke job:* couples failure modes and makes the PR-checks page
  unreadable. CI-research §R5 (006) already established one-job-per-gate as the team norm.
- *Skip teardown to speed re-runs:* leaves orphan volumes across job retries, contaminating
  state. Direct violation of SC-005.

---

## Open follow-ups (non-blocking)

These are not required for the smoke gate to land but are tracked here for the owners they
belong to:

- **Hiba (Phase 1):** consider adding `GET /tenants/{id}/audit-logs` so the smoke suite can
  drop its direct asyncpg readback (R3) in a future cleanup PR.
- **Nasser (Phase 5):** if `capture_lead` / `escalate` tool calls are surfaced through chat,
  decide whether the chat response should include `lead_id` / `ticket_id` in the top-level
  body (currently shown in `used_tools` per CONTRACT.md §2.9). The smoke test currently expects
  the response to expose them; if not, the test will read them from the DB instead.
- **Ayoub (Phase 6):** confirm `guardrails` exposes `/health` per CONTRACT; if it does not yet,
  Phase 6 should add it before R6's flag flips to `"1"`.
