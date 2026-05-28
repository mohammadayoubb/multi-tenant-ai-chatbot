# Owner: Amer

# RUNBOOK.md

## Start From Fresh Clone

```bash
cp .env.example .env
docker compose up --build
```

On the first boot the stack runs two one-shot bootstrap services automatically
before `api` starts:

| Service | Runs | Purpose |
|---------|------|---------|
| `vault-seed` | once per `up`, exits | Writes the dev app secrets into Vault (DB URL, Redis URL, widget signing key, …). Idempotent. |
| `migrations` | once per `up`, exits | Runs `alembic upgrade head` against the Postgres container. Idempotent. |

`api` depends on both via `service_completed_successfully`, so it won't accept
traffic until the database is on the latest revision.

## pgAdmin

pgAdmin is wired in as `pgadmin` and reachable at `http://localhost:${PGADMIN_PORT:-5050}`.

- Default credentials (override via `.env`): `PGADMIN_DEFAULT_EMAIL=admin@concierge.local` / `PGADMIN_DEFAULT_PASSWORD=admin`.
- The Concierge DB server is pre-registered in the sidebar via
  `scripts/pgadmin/servers.json`. You'll be prompted for the Postgres password
  (`postgres` in dev) the first time you connect — pgAdmin caches it for the
  session.
- Dev only. The default credentials and the bypassed master-password prompt
  are tagged as dev-only in `docker-compose.yml`; change both before exposing
  the port outside localhost.

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

1. Start stack.
2. Seed two tenants.
3. Load widget for Tenant A.
4. Ask a tenant-specific question.
5. Try to extract Tenant B content.
6. Show refusal.
7. Capture a lead.
8. Escalate to human.
9. Show CI gates.

## Owner B — Router, Agent, RAG, Tools, and Memory Runbook

### 1. Required environment variables

Owner B uses these environment variables:

```env
MODEL_SERVER_URL=http://modelserver:8010
MODELSERVER_SERVICE_TOKEN=local-modelserver-token
REDIS_URL=redis://redis:6379
SESSION_MEMORY_TTL_SECONDS=1800
```

Local fallback behavior exists for development, but final Docker/demo flow should provide these values through `.env`.

### 2. Run Section B tests

Run the agent/tool-selection eval:

```cmd
python -m pytest -q tests/evals/test_agent_tool_selection.py
```

Expected:

```text
10 passed
```

Run the RAG retrieval eval:

```cmd
python -m pytest -q tests/evals/test_rag_retrieval.py
```

Expected:

```text
5 passed
```

Run the Section B report:

```cmd
python evals\section_b_report.py
```

Expected:

```text
Section B Eval Report
Agent/tool selection: 10/10 passed
RAG retrieval:        5/5 passed

Status: PASS
```

Run the full suite:

```cmd
python -m pytest -q
```

Expected after Owner B evals:

```text
51 passed
```

### 3. Section B runtime flow

The chat flow is:

```text
POST /chat
  -> ChatService
  -> Redis memory append/load
  -> classifier-driven router
  -> direct workflow OR bounded agent
  -> tools
  -> Redis memory append
  -> ChatResponse
```

Direct workflow routes:

```text
spam -> blocked
faq -> rag_search
sales_or_contact -> capture_lead
human_request -> escalate
ambiguous / low confidence -> agent
```

### 4. Redis memory behavior

Redis memory key format:

```text
session:{tenant_id}:{session_id}
```

Default TTL:

```text
1800 seconds
```

This keeps short-term visitor memory for a browsing session without storing anonymous conversations forever.

Messages are redacted before storage.

### 5. RAG behavior

Current implementation:

- reads tenant CMS pages
- filters by `CmsPage.tenant_id == tenant_id`
- chunks text with overlap
- ranks chunks with deterministic lexical scoring

Important isolation rule:

```sql
WHERE tenant_id = :tenant_id
```

This rule must remain when pgvector retrieval is fully wired.

### 6. Bounded agent behavior

The agent uses only these tools:

```text
rag_search
capture_lead
escalate
```

Agent limits:

```text
MAX_AGENT_ITERATIONS = 5
MAX_AGENT_TOKENS_PER_TURN = 4000
```

The visitor and LLM never choose `tenant_id`; it is passed from trusted backend context.

### 7. Demo messages

Try these messages in the widget/API:

```text
What services do you offer?
```

Expected path:

```text
rag_search
```

```text
Please contact me about pricing. My email is buyer@example.com
```

Expected path:

```text
capture_lead
```

```text
Can I speak to a human representative?
```

Expected path:

```text
escalate
```

```text
What are your pricing options and can someone email me?
```

Expected path:

```text
agent -> rag_search + capture_lead
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
