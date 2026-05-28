# Owner: Amer
"""Thin wrapper that invokes tests/smoke/test_cross_tenant_e2e.py against a live stack.

This script does NOT start or stop docker compose — that responsibility lives
in the caller (the CI job's `docker compose up -d --wait` / `down -v` steps, or
a developer's terminal). Keeping orchestration out of this script avoids two
parallel sources of truth for "how does the stack come up."

Contract: specs/007-cross-tenant-smoke-e2e/contracts/smoke-runner-cli.md

Exit codes:
    0   all probes passed (or xfailed-as-expected under SMOKE_E2E_REQUIRE_FULL_STACK=0)
    1   one or more probes failed
    2   stack not reachable (API base did not respond to /health within 30 s)
    3   invalid CLI arguments
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

DEFAULT_API_BASE = "http://localhost:8000"
DEFAULT_DB_DSN = "postgresql://postgres:postgres@localhost:5432/concierge"
HEALTH_PROBE_TIMEOUT_S = 30.0
HEALTH_PROBE_INTERVAL_S = 1.0
TEST_TARGET = "tests/smoke/test_cross_tenant_e2e.py"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the cross-tenant smoke suite against a running stack.",
    )
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--db-dsn", default=DEFAULT_DB_DSN)
    parser.add_argument("-k", default=None, help="forwarded to pytest")
    parser.add_argument(
        "-v",
        action="count",
        default=0,
        help="verbosity (forwarded to pytest, repeatable)",
    )
    return parser.parse_args(argv)


def _wait_for_health(api_base: str) -> bool:
    """Block until the API is serving HTTP or the timeout elapses.

    Probes `/openapi.json` (a FastAPI default that returns 200 once the route
    stack is mounted) for the same reason as the docker-compose healthchecks:
    no `/health` route exists on the api today, and `/openapi.json` is a
    strictly stronger readiness signal than a hand-rolled `/health`. See
    specs/007-cross-tenant-smoke-e2e/research.md R4.
    """
    probe_url = api_base.rstrip("/") + "/openapi.json"
    deadline = time.monotonic() + HEALTH_PROBE_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            with urlopen(probe_url, timeout=2.0) as resp:
                if 200 <= resp.status < 300:
                    return True
        except (URLError, ConnectionError, TimeoutError, OSError):
            pass
        time.sleep(HEALTH_PROBE_INTERVAL_S)
    return False


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(list(argv) if argv is not None else sys.argv[1:])
    except SystemExit as exc:
        return 3 if exc.code not in (0, None) else 0

    os.environ["SMOKE_API_BASE"] = args.api_base
    os.environ["SMOKE_DB_DSN"] = args.db_dsn

    if not _wait_for_health(args.api_base):
        sys.stderr.write(
            f"smoke_check: API at {args.api_base}/health did not respond within "
            f"{HEALTH_PROBE_TIMEOUT_S:.0f}s\n"
        )
        return 2

    pytest_args = ["python", "-m", "pytest", TEST_TARGET]
    if args.v:
        pytest_args.append("-" + "v" * args.v)
    if args.k:
        pytest_args.extend(["-k", args.k])

    os.execvp(pytest_args[0], pytest_args)


if __name__ == "__main__":
    raise SystemExit(main())
