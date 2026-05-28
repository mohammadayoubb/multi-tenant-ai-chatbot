# Contract: GitHub Actions `smoke-e2e` Job

**Owner**: Amer
**Status**: Adds a new job to the protected file [.github/workflows/ci.yml](../../../.github/workflows/ci.yml).

## Job name

`smoke-e2e` — appears as a check on every PR and on push to `main`.

## Triggers

```yaml
if: github.event_name == 'pull_request' || (github.event_name == 'push' && github.ref == 'refs/heads/main')
```

Matches the existing eval-job gating in the workflow.

## Dependencies (`needs:`)

```yaml
needs:
  - lint-test-build
  - classifier-eval
  - rag-eval
  - agent-tool-eval
  - red-team
  - redaction-eval
```

Runs last. Rationale in [research.md](../research.md) R7.

## Job definition (canonical form)

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
  env:
    SMOKE_E2E_REQUIRE_FULL_STACK: "1"
  steps:
    - uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: "3.11"
        cache: pip
        cache-dependency-path: pyproject.toml

    - name: Install Python dependencies
      run: |
        pip install uv
        uv pip install --system -e ".[dev]"

    - name: Bring stack up
      run: docker compose up -d --wait

    - name: Show stack status
      if: always()
      run: docker compose ps

    - name: Run smoke suite
      run: python scripts/smoke_check.py -v

    - name: Capture compose logs on failure
      if: failure()
      run: docker compose logs > docker-compose.logs

    - name: Upload smoke artifacts
      if: failure()
      uses: actions/upload-artifact@v4
      with:
        name: smoke-e2e-logs
        path: |
          smoke-report.json
          docker-compose.logs

    - name: Tear stack down
      if: always()
      run: docker compose down -v
```

## Pass / fail semantics

- **Pass**: `docker compose up -d --wait` exits 0 **and** `scripts/smoke_check.py` exits 0.
- **Fail**: any of the above exits non-zero, **or** `pytest` reports `XPASS(strict)` from a
  probe currently xfailed under `SMOKE_E2E_REQUIRE_FULL_STACK="0"` (would only happen if the
  flag is in the wrong position when a dependency lands — surfaces the misconfiguration).
- **Teardown always runs** (`if: always()`) — no orphan containers, networks, or volumes.

## What this job does **not** do

- Does not run lint, type checks, or unit tests — those live in `lint-test-build`.
- Does not run eval gates — those live in their own jobs.
- Does not push artifacts on success — only failures upload, to keep storage costs flat.
- Does not retry on failure — flakes are bugs.

## What CI publishes

| Artifact name      | Path                                | Uploaded when |
|--------------------|-------------------------------------|---------------|
| `smoke-e2e-logs`   | `smoke-report.json` + `docker-compose.logs` | Only on failure |
