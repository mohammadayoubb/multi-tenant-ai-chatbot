# Quickstart: Cross-Tenant Smoke E2E

## What this is

A pytest suite that proves Tenant A's chat answers never leak Tenant B's content (and vice
versa), plus the same property for lead capture and escalation. It runs against a live Docker
Compose stack — no mocks, no patched HTTP clients.

## Prerequisites

- Docker Desktop or Docker Engine + `docker compose` v2.
- Python 3.11 with project dev deps installed (`uv pip install -e ".[dev]"`).
- `.env` populated at repo root (use `.env.example` as the template).

> **Important — phase-gate flag**: until Phases 1/2/5/6 ship their slices, run the suite with
> `SMOKE_E2E_REQUIRE_FULL_STACK=0`. In that mode the probes that depend on not-yet-shipped
> endpoints are wrapped in `xfail(strict)`. With the flag at its default `"1"` you will see
> errors like `POST /tenants response is missing required field 'id'` — that's the suite
> telling you the upstream isn't ready, not a bug in the test. Set the env var before invoking
> the runner. See the "Running while phases are still in flight" section below.

## Run locally

```bash
# 1. Bring the stack up (waits for healthchecks)
docker compose up -d --wait

# 2. Run the suite
python scripts/smoke_check.py -v

# 3. Tear down — MANDATORY, including on failure
docker compose down -v
```

**Step 3 is not optional.** The suite provisions two tenants per run; if the stack is reused
without `down -v`, those tenants accumulate in the local Postgres volume and subsequent runs
either collide on origin allowlists or read stale audit-log rows from prior runs. This is the
local-laptop side of spec FR-013 ("clean up the two tenants it provisions, or run against a
disposable database") — `down -v` makes the volume disposable.

If you forget step 3 and need to recover state without rerunning:

```bash
docker compose down -v && docker compose up -d --wait
```

Equivalent direct pytest invocation (step 2 only — steps 1 and 3 still required):

```bash
pytest tests/smoke/test_cross_tenant_e2e.py -v
```

Both paths run the same module and produce the same `smoke-report.json` in the working
directory.

## Expected output (happy path)

```text
tests/smoke/test_cross_tenant_e2e.py::test_cross_tenant_content_isolation_A   PASSED
tests/smoke/test_cross_tenant_e2e.py::test_cross_tenant_content_isolation_B   PASSED
tests/smoke/test_cross_tenant_e2e.py::test_forged_origin_returns_403           PASSED
tests/smoke/test_cross_tenant_e2e.py::test_lead_capture_scoped_to_tenant_A    PASSED
tests/smoke/test_cross_tenant_e2e.py::test_lead_not_visible_to_tenant_B       PASSED
tests/smoke/test_cross_tenant_e2e.py::test_escalate_returns_ticket_for_A      PASSED
tests/smoke/test_cross_tenant_e2e.py::test_audit_log_entry_exists_for_A       PASSED

7 passed in 42.3s
```

## Configuration

| Env var                          | Default                                                        | Purpose                                          |
|----------------------------------|----------------------------------------------------------------|--------------------------------------------------|
| `SMOKE_API_BASE`                 | `http://localhost:8000`                                        | Where httpx points                                |
| `SMOKE_DB_DSN`                   | `postgresql://postgres:postgres@localhost:5432/concierge`      | Audit-log readback                                |
| `SMOKE_E2E_REQUIRE_FULL_STACK`   | `1`                                                            | `"0"` allows xfailed probes while phases catch up |
| `WIDGET_JWT_SECRET`              | (from `.env`)                                                  | Used by the forged-origin negative probe          |

## Running while phases are still in flight

Until Phases 1/2/5/6 ship their slices, set `SMOKE_E2E_REQUIRE_FULL_STACK=0` to allow probes
that depend on those slices to xfail rather than fail:

```bash
SMOKE_E2E_REQUIRE_FULL_STACK=0 python scripts/smoke_check.py -v
```

When a slice lands, its previously-xfail probe will pass, pytest will report `XPASS(strict)`
as a failure, and the PR that lands the slice must flip the env var back to `"1"`. There is
no silent skip.

## Troubleshooting

| Symptom                                       | Likely cause                                                    | Fix                                                            |
|-----------------------------------------------|-----------------------------------------------------------------|----------------------------------------------------------------|
| `docker compose up -d --wait` times out        | One service's healthcheck never goes green                       | `docker compose logs <service>` and check `/health` manually   |
| `test_forged_origin_returns_403` returns 200   | Server is not validating the origin claim                        | This is the regression the test exists to catch — file a bug   |
| `bravo-pastries` appears in Tenant A's answer  | RAG isn't filtering by tenant, or a chunk leaked across tenants  | Hard fail — escalate to Hiba (RLS) and Nasser (RAG filter)     |
| `XPASS(strict)` on a probe                     | Dependency shipped; flag is still `0`                            | Set `SMOKE_E2E_REQUIRE_FULL_STACK=1` in the PR landing the dep |
| Orphan containers after a failed run           | CI's `if: always()` teardown ran; local run didn't               | `docker compose down -v`                                       |

## What this suite is **not**

- Not a load test. Six chat requests, two tenants. Performance is out of scope (see spec.md).
- Not a UI test. The widget JS bundle is not exercised; the suite calls the API directly the
  way the widget would.
- Not a multi-region test. One Compose project, one network, one runner.
