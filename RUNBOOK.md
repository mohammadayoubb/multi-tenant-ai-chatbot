# Owner: Amer
# RUNBOOK.md

## Start From Fresh Clone

```bash
cp .env.example .env
docker compose up --build
```

## Run API Locally

```bash
uvicorn app.main:app --reload
```

## Run Tests

```bash
pytest
```

## Run Lint

```bash
ruff check .
```

## Run Type Check

```bash
mypy app/
```

## Demo Flow

Each step lists the command or UI action and what to watch for. Run from a fresh clone with `.env` copied from `.env.example`.

1. **Start the stack.**
   ```bash
   docker compose up --build --wait
   ```
   `--wait` blocks until every healthcheck passes. `docker compose ps` should show `api`, `modelserver`, `guardrails`, `db`, `redis`, `vault` all `healthy` and `admin`, `widget`, `minio` running.

2. **Seed two tenants.**
   ```bash
   python scripts/seed_tenants.py
   ```
   Two tenant rows are inserted with seeded CMS content and widget configs.

3. **Open the host page for Tenant A.**
   Navigate to `http://localhost:5173/host-test.html`. The widget mounts in the bottom-right corner. Open DevTools → Network and confirm a `POST /widgets/token` call returns 200.

4. **Ask a Tenant A-specific question.**
   Type a question grounded in Tenant A's seeded CMS content. The agent responds using `rag_search` against Tenant A's vectors only.

5. **Attempt to extract Tenant B content.**
   From the same Tenant A session, ask a question whose answer would require Tenant B data (e.g., "What products does Acme Corp sell?" if Acme is Tenant B).

6. **Observe the refusal.**
   The agent declines or returns a grounded refusal. Open the admin UI at `http://localhost:8501` → tenant audit-log view; a new entry shows the cross-tenant attempt was rejected. (This is the source for demo screenshot 1.)

7. **Capture a lead.**
   Give the agent a contact email (e.g., "I'd like a quote — reach me at demo@example.com"). The `capture_lead` tool fires; the admin UI's leads view shows the new lead scoped to Tenant A.

8. **Escalate to human.**
   Ask the agent to escalate ("Can a human follow up on this?"). The conversation is marked for human follow-up; the admin UI shows the escalation flag set.

9. **Show CI gates.**
   Open the GitHub Actions page for the latest commit on `main`. Every required check is green: `lint-test-build`, `lean-image-audit`, `classifier-eval`, `rag-eval`, `agent-tool-eval`, `red-team`, `redaction-eval`, `smoke-e2e`. (This is the source for demo screenshot 3.)

## Run smoke test

```bash
pytest tests/smoke/
```

Exits 0 against a running local stack — that is the passing signal. The same suite runs in CI via the `smoke-e2e` job; `scripts/smoke_check.py -v` is the CI-equivalent wrapper used by the workflow.
