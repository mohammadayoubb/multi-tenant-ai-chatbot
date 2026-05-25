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
