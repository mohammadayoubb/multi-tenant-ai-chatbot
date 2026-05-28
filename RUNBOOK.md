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
=====================
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
