<!--
Sync Impact Report
Version change: (none) → 1.0.0
Bump rationale: Initial ratification of the Concierge project constitution.

Modified principles:
  - (initial) → I. Tenant Isolation (NON-NEGOTIABLE)
  - (initial) → II. Layered Architecture
  - (initial) → III. Bounded, Auditable Agent
  - (initial) → IV. Defense-in-Depth Auth & Secrets
  - (initial) → V. Lean Serving & Mandatory Redaction
  - (initial) → VI. Phased Build
  - (initial) → VII. Clean & Simple Code

Added sections:
  - Quality Gates
  - Development Workflow
  - Governance

Removed sections: none.

Templates requiring updates:
  - .specify/templates/plan-template.md — ⚠ pending (review "Constitution Check" section against the seven principles)
  - .specify/templates/spec-template.md — ⚠ pending (verify mandatory scope sections cover tenant isolation requirements)
  - .specify/templates/tasks-template.md — ⚠ pending (ensure task categories cover redaction, RLS, eval gates, audit logging)
  - .specify/templates/checklist-template.md — ⚠ pending (review against pre-merge checklist in CLAUDE.md)
  - CLAUDE.md — ✅ already aligned (constitution distilled from existing rules)
  - CONTRACT.md — ✅ already aligned (constitution distilled from existing contract)

Deferred items: none.
-->

# Concierge Constitution

Concierge is a multi-tenant AI SaaS where businesses manage CMS content, configure an AI agent, and embed a public chat widget. The single highest-priority property of this system is **tenant isolation**: Tenant A MUST NEVER access Tenant B data, vectors, leads, conversations, embeddings, prompts, widget configuration, costs, sessions, or audit logs.

This constitution is the top-level contract. Where this document and any other guidance (including `CLAUDE.md`, `CONTRACT.md`, `DESIGN.md`, `SECURITY.md`) appear to conflict, this constitution wins and the other documents MUST be updated to match.

## Core Principles

### I. Tenant Isolation (NON-NEGOTIABLE)

Tenant isolation is the grade. A working chatbot that leaks tenant data fails.

- Every tenant-owned table MUST include `tenant_id UUID NOT NULL`.
- Every repository query against a tenant-owned table MUST be scoped by `tenant_id`.
- Every pgvector similarity search MUST include `WHERE tenant_id = :tenant_id`.
- PostgreSQL Row-Level Security MUST be enforced in addition to repository scoping — never as a substitute.
- Redis session keys MUST be namespaced `session:{tenant_id}:{session_id}`.
- `tenant_id` MUST be derived from trusted server context (signed widget token or authenticated session) and MUST NEVER be read from a visitor or client request body.
- The Tenant Manager role MUST NOT be able to read tenant conversations, leads, or private CMS content.
- Tenant erasure MUST delete rows, vectors, blobs, sessions, and traces, and MUST be audit-logged.

**Rationale:** Cross-tenant leakage is the single failure mode that voids the product. Two independent enforcement layers (RLS + explicit repo filter) prevent a single forgotten filter from becoming a breach.

### II. Layered Architecture

The HTTP request flow is fixed:

```text
app/api/routes/       HTTP only, no SQL
  ↓
app/services/         business logic
  ↓
app/repositories/     SQL only, tenant-scoped
  ↓
app/db/models.py      ORM models
  ↓
PostgreSQL + pgvector
```

- Routes MUST NOT contain SQL or call repositories directly for business decisions.
- Services MUST own business logic; repositories MUST own queries.
- Layers MUST NOT be bypassed or merged for convenience.
- Configuration MUST be centralized in `app/config.py` via `pydantic-settings`; the application MUST fail to start if any required env variable is missing.

**Rationale:** A predictable layering keeps tenant scoping enforceable at the repository boundary and keeps routes thin enough to review for auth correctness.

### III. Bounded, Auditable Agent

The agent has exactly three tools. No more, no fewer:

| Tool | Purpose |
|------|---------|
| `rag_search` | Retrieve from the current tenant's CMS content only |
| `capture_lead` | Write a lead scoped to the current tenant only |
| `escalate` | Mark the conversation for human follow-up |

- The agent loop MUST cap iterations at 5 and tokens-per-turn at 4000.
- Every tool call MUST be schema-validated before execution.
- Every tool MUST derive `tenant_id` from trusted server context, NEVER from tool arguments or the message body.
- Platform guardrails are mandatory and MUST NOT be weakened by any tenant configuration. Tenant rails MAY add restrictions but MUST NOT relax platform rails.
- Adding, removing, or renaming a tool requires a constitution amendment AND an entry in `DECISIONS.md`.

**Rationale:** Bounding the tool surface, the loop, and the source of `tenant_id` makes agent behavior auditable and makes prompt-injection attacks substantially harder.

### IV. Defense-in-Depth Auth & Secrets

- Widget access MUST use a signed, short-lived JWT obtained from `POST /widgets/token` after server-side validation of `widget_id` and `origin` against the tenant's allowlist.
- Widget tokens MUST be stored in browser memory only. `localStorage`, cookies, and other persistent browser storage MUST NOT be used for widget tokens.
- CORS and CSP `frame-ancestors` are defense-in-depth only. They MUST NOT be relied on as authentication.
- Service-to-service calls MUST use Vault-backed credentials.
- Real secrets MUST resolve from Vault. `.env` files MUST NOT be committed. Hardcoded API keys, tokens, passwords, or private keys are prohibited.

**Rationale:** Browser-side controls (CORS, CSP) are bypassable by any non-browser client; only a server-validated, signed, short-lived token can gate tenant access. Vault centralizes rotation and revocation.

### V. Lean Serving & Mandatory Redaction

- Serving containers (`modelserver`, `guardrails`) MUST NOT include `torch` or `transformers`. Inference uses ONNXRuntime / scikit-learn.
- Every model artifact MUST be accompanied by a `model_card.json` (task, dataset source, dataset hash, metrics, chosen model, artifact SHA-256). The modelserver MUST refuse to boot if the artifact SHA-256 does not match the model card.
- Logs, traces, memory, the `messages` table, and the `traces` table MUST store redacted text only. Raw PII, raw secrets, raw prompts, and raw stack traces MUST NOT be persisted or shipped to logs.
- Training happens in notebooks only and MUST NEVER run inside any container that is part of the serving stack.

**Rationale:** Lean images reduce attack surface, build time, and supply-chain risk. Redaction at write-time prevents incident response and observability tooling from becoming a secondary leakage vector.

### VI. Phased Build

Work proceeds in declared phases. Building ahead of the current phase is prohibited.

| Phase | Focus | Primary Owner |
|-------|-------|---------------|
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

- Work outside the current phase MUST require explicit team agreement before being merged.
- Cross-phase dependencies MUST be coordinated via shared contracts in `CONTRACT.md`, not by reaching into another phase's files.

**Rationale:** With four owners working in parallel under tight isolation requirements, phase discipline prevents premature integration on top of contracts that have not yet been ratified.

### VII. Clean & Simple Code

Code MUST be clean, simple, and defensible. Every member must be able to read and explain every line they merge.

- Prefer the smallest change that satisfies the requirement. Three obvious lines beat one clever abstraction.
- Do not add features, refactors, or abstractions beyond what the task requires. No speculative design for hypothetical future needs.
- Do not add error handling, fallbacks, or validation for cases that cannot happen. Validate at system boundaries (HTTP request, external service response) — not between trusted internal layers.
- Follow the project naming rules in `CONTRACT.md` §6 (`snake_case` for Python and JSON fields, `PascalCase` for classes and Pydantic models, canonical ID names like `tenant_id` — never `business_id`, `org_id`, `customer_id`, etc.).
- Default to no comments. Add one only when the *why* is non-obvious (a hidden constraint, a subtle invariant, a workaround for a specific bug). Do not paraphrase what the code already says.
- Functions and modules MUST stay within their layer (see Principle II). A repository function does not call a service; a route does not assemble SQL.
- Dead code, commented-out blocks, and "just in case" branches MUST be removed before merge.
- Use logging, not `print`. Use `async` consistently for API, database, and network code.

**Rationale:** Tenant isolation only holds if every reviewer can audit the code. Complexity is the enemy of correctness here — abstractions hide where `tenant_id` flows, and over-engineering buries the small number of lines that matter for security.

## Quality Gates

Every PR MUST pass these gates. Thresholds are tracked in `eval_thresholds.yaml` and MAY be tightened (never silently relaxed).

| Gate | Threshold |
|------|-----------|
| Lint (ruff) | MUST pass |
| Type check (mypy strict) | MUST pass |
| Docker build (full stack) | MUST pass |
| Classifier macro-F1 | ≥ 0.80 |
| RAG hit@5 | ≥ 0.70 |
| RAG MRR | ≥ 0.50 |
| RAG faithfulness | ≥ 0.80 |
| Agent tool-selection accuracy | ≥ 0.80 |
| Red-team pass rate | 1.0 |
| Redaction pass rate | 1.0 |
| Smoke test | MUST pass |

- A failed gate blocks merge.
- Thresholds may be adjusted after real measurements land, but the new threshold MUST be committed in the same PR and noted in `DECISIONS.md`.
- The classifier, RAG, agent tool, red-team, redaction, and smoke suites MUST be wired into GitHub Actions before the work they cover is considered complete.

## Development Workflow

- **File ownership:** every source file begins with a `# Owner: <Name>` header. Editing a file owned by another member requires owner approval or a documented integration fix, per `CONTRACT.md` §3–4.
- **Cross-owner review (mandatory before merge):**
  - Tenancy / RLS / tenant-scoped queries / provisioning / audit / rate limits → **Hiba**.
  - Guardrails / redaction / Vault / service-to-service auth / sensitive logging → **Ayoub**.
  - Dockerfiles / `docker-compose.yml` / GitHub Actions / widget build / smoke tests → **Amer**.
  - Agent / tools / RAG / CMS behavior / prompts / agent or RAG evals → **Nasser**.
- **Public-contract changes** (route paths, function names, table names, ID field names, enum values, JSON shapes, error codes) MUST update `CONTRACT.md` in the same PR.
- **Major decisions** MUST be recorded in `DECISIONS.md` before or immediately after implementation. Major decisions include: changing tenant ID type, adding/removing tables, changing route names, changing tool names, changing auth/token flow, changing model choice, changing eval thresholds, changing Docker/CI behavior.
- **Spec Kit workflow** is the default path for feature work:
  - Standard: `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`.
  - Risky (auth, isolation, RLS, widget token, service-to-service, guardrails, erasure, eval gates, any repo function touching a tenant-owned table): insert `/speckit-clarify` after specify and `/speckit-analyze` after tasks.
- **Git discipline:** no direct pushes to `main`; PRs are small and focused; the assistant does not run git actions unless the user explicitly requests them.

## Governance

- This constitution supersedes ad-hoc practice. `CLAUDE.md` and `CONTRACT.md` MUST remain consistent with it; on conflict, the constitution wins and the others are updated.
- All PRs MUST verify compliance with the principles above. Reviewers cite the principle number when requesting a change for constitutional reasons.
- **Amendments** require:
  1. A PR that updates this file.
  2. A version bump following semantic versioning:
     - **MAJOR**: backward-incompatible principle removals or redefinitions, or governance changes that alter who can approve what.
     - **MINOR**: new principle or section, or materially expanded guidance.
     - **PATCH**: clarifications, wording, typo fixes, non-semantic refinements.
  3. A Sync Impact Report prepended to this file as an HTML comment.
  4. A corresponding `DECISIONS.md` entry.
  5. Propagation to dependent templates under `.specify/templates/` and to `CLAUDE.md` / `CONTRACT.md` where applicable.
- **Complexity must be justified.** Any addition that increases the attack surface, the agent's tool set, the serving image weight, or the surface area of tenant-bearing interfaces MUST cite which principle authorizes it (or amend the constitution first).
- **Runtime guidance** for day-to-day work lives in `CLAUDE.md`; this constitution is the constraint layer above it.

**Version**: 1.0.0 | **Ratified**: 2026-05-26 | **Last Amended**: 2026-05-26
