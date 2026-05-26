# CLAUDE.md
Shared Claude Code instructions for Concierge.
For additional context about technologies, project structure, shell commands, and other important information, read the current plan.

---

## Project

Concierge is a multi-tenant AI SaaS platform for businesses.
Any business (tenant) can manage CMS content, configure an AI agent, and embed a chat widget on its public website.
Visitors chat with the tenant's agent. The agent answers from that tenant's CMS content, captures leads, and escalates to humans when needed.

**The highest priority is tenant isolation.**
Tenant A must never access Tenant B data, vectors, leads, conversations, embeddings, prompts, widget config, costs, sessions, or audit logs — under any circumstances.

---

## Team and Ownership

| Member | Name | Primary Ownership |
|--------|------|-------------------|
| A | Hiba | Platform, tenancy, RLS, roles, provisioning, erasure, audit logs, cost/rate limits |
| B | Nasser | Agent, RAG, router, tools, memory, prompts, CMS, leads, RAG/agent evals |
| C | Ayoub | Classifier, modelserver, guardrails, redaction, service-to-service auth, Vault, tracing |
| D | Amer | React widget, admin UI, widget auth, origin allowlist, Docker, CI/CD, smoke tests |

Cross-review rules:
Any file touching `tenant_id` scoping or RLS → Hiba reviews before merge.
Any file touching guardrails, redaction, or service credentials → Ayoub reviews before merge.

---

## Team Rules

Do not push directly to main.
Work on a branch.
Keep PRs small and focused.
Do not hardcode secrets.
Do not commit `.env`.
Do not add real API keys, tokens, passwords, or private keys.
Do not skip tests for changed behavior.
Do not build ahead of the requested phase.
Every major decision must be documented in `DECISIONS.md` before or immediately after implementation.

---

## Architecture Rules

Keep logic separated:
- `routes`
- `schemas` / `domain`
- `services`
- `repositories`
- `infra` clients
- `config`

Use async patterns for all API, database, and network work.
Use centralized config via `app/config.py` with `pydantic-settings`.
Application must fail to start if any required env variable is missing.
Use logging, not print.
Do not log secrets, tokens, passwords, PII, or raw sensitive data.
Keep Docker containers lean.
Do not add `torch` or `transformers` to serving containers.
Training happens in notebooks only and never in any container that is part of the serving stack.

---

## Tenant Safety Rules

Never trust `tenant_id` from a visitor or client request body.
Tenant identity must come from a verified signed widget token, JWT, or session set by the server.
Every tenant-owned database table must have a `tenant_id UUID NOT NULL` column.
Every repository query against a tenant-owned table must be scoped by `tenant_id`.
Every pgvector similarity search must include a `WHERE tenant_id = :tenant_id` filter.
Redis session keys must be namespaced: `session:{tenant_id}:{session_id}`.
Platform guardrails are locked and cannot be weakened by any tenant configuration.
Tenant Manager must not be able to read tenant conversations, leads, or CMS content.
Every Tenant Manager action (provision, suspend, erase) must be audit-logged.

---

## Agent Rules

The agent has exactly three tools. No more, no fewer.

| Tool | Purpose |
|------|---------|
| `rag_search` | Retrieve from the current tenant's CMS content only |
| `capture_lead` | Write a lead scoped to the current tenant only |
| `escalate` | Mark the conversation for human follow-up |

Every tool call must be schema-validated before execution.
Every tool must derive `tenant_id` from trusted context only, never from tool arguments or the message body.
The agent loop must have a hard cap on iterations (default: 5).
The agent loop must have a hard cap on tokens per turn (default: 4000).

---

## Widget Auth Rules

Widget session flow:
1. Browser loads `widget.js` with `data-widget-id` attribute.
2. Widget calls `POST /widget/session` with `{ widget_id, origin }`.
3. Server validates origin against the tenant's allowed origins list (database).
4. Server returns a signed short-lived JWT containing `{ tenant_id, widget_id, exp }`.
5. Widget stores the token in memory only — not localStorage, not cookies.
6. Every chat request includes `Authorization: Bearer <token>`.
7. API derives `tenant_id` from the token only.

CORS and CSP `frame-ancestors` are applied as defense-in-depth after server-side origin validation.
CORS is not authentication.

---

## Classifier and Modelserver Rules

Three approaches must be compared and committed:
1. Classical ML baseline (TF-IDF + logistic regression or gradient boosting).
2. Small DL model exported to ONNX.
3. LLM zero-shot baseline.

Comparison must include: macro-F1, per-class F1, latency, and cost.
The chosen model must be documented in `DECISIONS.md` with the metric that justified the choice.
A `model_card.json` must accompany every artifact: task, dataset source, dataset hash, metrics, chosen model, artifact SHA-256.
The modelserver must refuse to boot if the artifact SHA-256 does not match the model card.
No `torch` or `transformers` in any modelserver image.

---

## Spec Kit Workflow

Use Spec Kit for all feature work.

For simple, safe features:
```
/speckit-specify
/speckit-plan
/speckit-tasks
/speckit-implement
```

For risky features:
```
/speckit-specify
/speckit-clarify
/speckit-plan
/speckit-tasks
/speckit-analyze
/speckit-implement
```

Risky features include:
- Auth (any kind)
- Tenant isolation changes
- RLS policies or migrations
- Widget token auth
- Service-to-service auth
- Guardrails (platform or tenant)
- Tenant erasure
- CI eval gates
- Any repository function touching a tenant-owned table

---

## Protected Files

Warn before editing any of these. Do not edit without explicit user confirmation:

```
.env.example
.gitignore
.dockerignore
docker-compose.yml
Makefile
.github/workflows/*
app/config.py
app/main.py
app/api/deps.py
app/api/middleware.py
app/core/security.py
app/core/logging.py
app/db/session.py
app/db/migrations/*
app/infra/vault.py
app/infra/guardrails.py
prompts/system.md
guardrails/rails/*
modelserver/model_card.json
eval_thresholds.yaml
```

---

## CI Eval Gates

These gates must pass on every PR. Thresholds are committed in `eval_thresholds.yaml`.

| Gate | Threshold |
|------|-----------|
| Lint | Must pass |
| Type check | Must pass |
| Docker build | Must pass |
| Classifier macro-F1 | ≥ 0.80 |
| RAG hit@5 | ≥ 0.70 |
| RAG MRR | ≥ 0.50 |
| RAG faithfulness | ≥ 0.80 |
| Agent tool-selection accuracy | ≥ 0.80 |
| Red-team pass rate | 1.0 |
| Redaction pass rate | 1.0 |
| Smoke test | Must pass |

A failed gate blocks merge. Thresholds may be adjusted after real results are in, but must always be committed.

---

## Pre-Merge Checklist

Before opening a PR, confirm:

- [ ] Every new tenant-owned table has `tenant_id UUID NOT NULL`.
- [ ] Every repository function for a tenant-owned table is scoped by `tenant_id`.
- [ ] No hardcoded secrets.
- [ ] No `torch` or `transformers` in serving code.
- [ ] No raw exception or stack trace exposed to the client.
- [ ] No unredacted PII or fake secret in logs.
- [ ] Tests cover the happy path and the tenant-isolation path.
- [ ] Every new route has role-based access control.
- [ ] Platform guardrails were not weakened.
- [ ] `tenant_id` in any tool or agent code comes from trusted context only.
- [ ] Any new migration has been reviewed by Hiba.
- [ ] Any security file change has been reviewed by Ayoub.
- [ ] `DECISIONS.md` is updated if a non-trivial decision was made.
- [ ] CI is green.

---

## Git Rule

Claude should not run Git actions unless the user explicitly asks.
Prefer suggesting commands instead of running them.

---

## Phase Build Order

Do not build ahead of the requested phase.

| Phase | Focus | Owner |
|-------|-------|-------|
| 0 | Specs, repo skeleton, shared contracts | All |
| 1 | Platform, tenancy, RLS, roles, audit | Hiba |
| 2 | CMS content, embeddings, tenant-filtered RAG | Nasser |
| 3 | Classifier training, ONNX export, modelserver | Ayoub |
| 4 | Classifier router, hybrid message flow | Nasser |
| 5 | Tool-calling agent, tools, Redis memory, prompts | Nasser |
| 6 | Guardrails, redaction, service-to-service security | Ayoub |
| 7 | Widget, widget auth, origin allowlist, public chat | Amer |
| 8 | Admin UI (Streamlit) | Amer |
| 9 | Right to erasure | Hiba |
| 10 | CI/CD and eval gates | Amer |
| 11 | Documentation | All |

---

<!-- SPECKIT START -->
## Active Spec-Kit Feature

For technologies, project structure, shell commands, and feature-specific decisions, read the current plan: [specs/002-widget-chat-ui/plan.md](specs/002-widget-chat-ui/plan.md).

Related artifacts:
- [specs/002-widget-chat-ui/spec.md](specs/002-widget-chat-ui/spec.md)
- [specs/002-widget-chat-ui/research.md](specs/002-widget-chat-ui/research.md)
- [specs/002-widget-chat-ui/data-model.md](specs/002-widget-chat-ui/data-model.md)
- [specs/002-widget-chat-ui/contracts/](specs/002-widget-chat-ui/contracts/)
- [specs/002-widget-chat-ui/quickstart.md](specs/002-widget-chat-ui/quickstart.md)

Prior feature (shipped):
- [specs/001-widget-token-exchange/](specs/001-widget-token-exchange/)
<!-- SPECKIT END -->
