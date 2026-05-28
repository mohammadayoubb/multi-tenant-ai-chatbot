# Contract: `scripts/smoke_check.py`

**Owner**: Amer
**Status**: Replaces the placeholder script in [scripts/smoke_check.py](../../../scripts/smoke_check.py).

## Purpose

A thin invocation wrapper around `tests/smoke/test_cross_tenant_e2e.py` so the same suite runs
identically in two contexts:

- CI: invoked by the `smoke-e2e` GitHub Actions job after `docker compose up -d --wait`.
- Local: invoked by a developer against a running stack on their laptop.

The script does **not** start or stop the Compose stack — that responsibility lives in the CI
job (and the developer's terminal). Keeping orchestration out of the script avoids two parallel
sources of truth for "how does the stack come up."

## CLI

```text
python scripts/smoke_check.py [--api-base URL] [--db-dsn DSN] [-k EXPR] [-v|-vv]
```

| Flag           | Default                                       | Notes                                             |
|----------------|-----------------------------------------------|---------------------------------------------------|
| `--api-base`   | `http://localhost:8000`                       | Forwarded as env `SMOKE_API_BASE`                  |
| `--db-dsn`     | `postgresql://postgres:postgres@localhost:5432/concierge` | Forwarded as env `SMOKE_DB_DSN`           |
| `-k`           | (none)                                        | Forwarded to pytest (probe selection)             |
| `-v`, `-vv`    | (none)                                        | Forwarded to pytest                               |

Internally the script `os.execvp`s pytest with `tests/smoke/test_cross_tenant_e2e.py` plus the
forwarded args. No mocking, no fixtures factory — pytest is the test runner, this script is its
caller.

## Exit codes

| Code | Meaning                                                       |
|------|---------------------------------------------------------------|
| 0    | All probes passed (or xfailed-as-expected under R6's flag)     |
| 1    | One or more probes failed                                     |
| 2    | Stack not reachable (the API base URL did not respond to `/health` within 30 s) |
| 3    | Invalid CLI arguments                                          |

CI treats anything non-zero as a hard failure.

## Environment variables read

| Var                            | Purpose                                                 |
|--------------------------------|---------------------------------------------------------|
| `SMOKE_API_BASE`               | Where the suite points httpx                            |
| `SMOKE_DB_DSN`                 | Audit-log readback (R3)                                 |
| `SMOKE_E2E_REQUIRE_FULL_STACK` | `"1"` (default) or `"0"` per R6                          |
| `WIDGET_JWT_SECRET`            | Shared with the API container; forged-origin probe (R1) |

All four are exported to pytest via `os.environ`; pytest does not re-parse the CLI.

## Non-goals

- Does **not** start the Compose stack.
- Does **not** stop or clean up the Compose stack.
- Does **not** seed fixtures outside of what the suite itself creates via HTTP.
- Does **not** print secrets, full tokens, or full chat response bodies.
