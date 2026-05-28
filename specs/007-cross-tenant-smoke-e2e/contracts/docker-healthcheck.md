# Contract: Docker Compose Healthchecks

**Owner**: Amer
**Status**: Modifies the protected file [docker-compose.yml](../../../docker-compose.yml). Requires
Amer-as-owner and acknowledgement that the change leaves all service contracts intact (no port
changes, no image changes, no command changes).

## Services affected

### `api`

```yaml
api:
  # ... existing build/ports/env_file/networks unchanged ...
  healthcheck:
    test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/openapi.json', timeout=2)\" || exit 1"]
    interval: 5s
    timeout: 5s
    retries: 12
    start_period: 5s
  depends_on:
    db:           { condition: service_healthy }
    vault:        { condition: service_healthy }
    redis:        { condition: service_healthy }
    modelserver:  { condition: service_healthy }
    guardrails:   { condition: service_healthy }
```

### `modelserver`

```yaml
modelserver:
  # ... existing build/ports/env_file/networks unchanged ...
  healthcheck:
    test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8010/openapi.json', timeout=2)\" || exit 1"]
    interval: 5s
    timeout: 5s
    retries: 12
    start_period: 5s
```

### `guardrails`

```yaml
guardrails:
  # ... existing build/ports/env_file/networks unchanged ...
  healthcheck:
    test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8020/openapi.json', timeout=2)\" || exit 1"]
    interval: 5s
    timeout: 5s
    retries: 12
    start_period: 5s
```

> **Why `/openapi.json` and not `/health`:** the `python:3.11-slim` base images used by these
> three services don't ship `curl`, and none of the services currently exposes a `/health`
> route. `/openapi.json` is a FastAPI default; a 200 here proves both that the process is up
> and that the route stack is mounted (strictly stronger than a hand-rolled `/health` that
> can be hardcoded to return 200 without any real routes). Avoids cross-owner edits to
> Hiba's `app/main.py` and Ayoub's `modelserver/main.py` / `guardrails/main.py`.

### `redis` (defensive — currently has no healthcheck)

```yaml
redis:
  # ... existing image/ports/networks unchanged ...
  healthcheck:
    test: ["CMD-SHELL", "redis-cli ping | grep -q PONG"]
    interval: 5s
    timeout: 3s
    retries: 10
    start_period: 3s
```

### `db` and `vault`

Already have healthchecks; left untouched.

## Rationale

Each healthcheck command must:
1. Run inside the container using only tools present in the image (no new packages).
2. Return non-zero unless the **application** (not just the process) is serving traffic.
3. Complete within the timeout consistently.

`curl -fsS` returns non-zero on any non-2xx response or transport failure. `redis-cli ping`
returns `PONG` only when the server is accepting commands. The intervals × retries budget gives
each service one minute to come up cold before being declared unhealthy — measured against the
existing observed cold-start time on `ubuntu-latest` runners.

## Validation

After applying this contract, `docker compose up -d --wait` must:
- Exit 0 within 90 s on a warm cache.
- Exit 0 within 180 s on a cold cache (image pulls included).
- Exit non-zero if any service fails to reach healthy within its retry budget.

The CI job sets `timeout-minutes: 15`, leaving generous headroom over both cases.

## Out of scope

- No change to image base, target, or installed packages.
- No exposure of internal ports to the host beyond what is already published.
- No new container.
