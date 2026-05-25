# Owner: Hiba
# CLAUDE.md — Concierge Architecture Contract

This file is the engineering contract for the Week 8 Concierge project.

Every teammate must understand and defend every line of code.

## Golden Rule

Tenant isolation is the grade. A working chatbot that leaks tenant data fails.

## Layered Architecture

```text
HTTP request
  ↓
app/api/routes/       HTTP only
  ↓
app/services/         business logic
  ↓
app/repositories/     SQL only, tenant scoped
  ↓
app/db/models.py      ORM models
  ↓
PostgreSQL + pgvector
```

## Rules

- Routes do not contain SQL.
- Services own business logic.
- Repositories own queries.
- Every tenant-owned query is scoped by tenant_id.
- RLS is required.
- Widget auth uses signed short-lived tokens.
- CORS is not authentication.
- Platform guardrails are not tenant-editable.
- Prompts live in `app/prompts/`.
- No torch or transformers in production containers.
- CI must gate classifier, RAG, agent tools, red-team, redaction, and smoke tests.
