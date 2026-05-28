# Implementation Plan: Secure Widget Token Exchange

**Branch**: `001-widget-token-exchange` | **Date**: 2026-05-26 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-widget-token-exchange/spec.md`

## Summary

Implement the `POST /widgets/token` endpoint that turns a `(widget_id, origin)` pair into a short-lived signed JWT, plus the widget-side fetch flow that consumes it and keeps the token in volatile memory only. The endpoint enforces tenant isolation (FR-001, FR-003), strict exact-host origin matching (FR-002), indistinguishable refusals (FR-007, FR-008, FR-008a), per-IP + per-widget rate baselines (FR-015–FR-019), and structured observability (FR-020–FR-023). Technical approach: thin FastAPI route → `WidgetTokenService` (validation + JWT signing) → tenant-scoped `WidgetRepository`; PyJWT for HS256 signing with `WIDGET_JWT_SECRET` from env (Vault swap deferred to Ayoub); structlog for hashed-identifier refusal logs; SQLAlchemy async repository against a `widget_configs` table that Hiba's slice will migrate, mocked behind an in-memory implementation until that migration lands.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x (frontend widget)
**Primary Dependencies**: FastAPI, Pydantic + pydantic-settings, SQLAlchemy[asyncio] + asyncpg, PyJWT, structlog, httpx (test client); React + Vite (frontend)
**Storage**: PostgreSQL — `widget_configs` table (CONTRACT.md §8.1, schema owned by Hiba). No new table added by this feature. In-memory fallback adapter behind the same repository interface until Hiba's migration is merged.
**Testing**: pytest + pytest-asyncio (backend, `asyncio_mode = auto` per `pyproject.toml`); vitest (frontend — new dev dependency for `frontend/widget`).
**Target Platform**: Linux (Python 3.11-slim Docker container) for the backend; modern evergreen browsers (ES2019 target) for the widget bundle.
**Project Type**: Web — multi-service monorepo. Backend is a FastAPI app under `app/`; widget is a Vite/React SPA bundled to a static file under `frontend/widget/`.
**Performance Goals**: Token endpoint p95 server-side latency < 50 ms (so end-to-end "widget chat-ready in 1 s" per SC-003 is achievable on a residential connection). Sustained throughput: 100 req/s/instance baseline; burst absorbed by per-IP + per-widget rate baselines.
**Constraints**: Tenant isolation absolute (Principle I); token in volatile browser memory only (FR-011, FR-012, Principle IV); no torch/transformers in any image (Principle V — not violated since this feature ships no ML code); zero raw visitor PII in logs (FR-021, Principle V); JWT signing secret from environment for this phase, Vault swap is a separate feature owned by Ayoub.
**Scale/Scope**: 10s–1000s of tenants per platform (constitution scope). Per visitor: 1 token request per page load, plus rare refresh-driven re-issuance. No long polling — the endpoint is one-shot per token.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The plan MUST pass each gate before Phase 0 research and again after Phase 1 design. Cite the constitution principle by number in any waiver.

- [x] **Principle I (Tenant Isolation):** `tenant_id` is derived server-side from the `widget_configs` lookup keyed by `widget_id`; it is NOT read from the request body. The repository function `get_widget_config_by_widget_id(widget_id)` returns the entire row including the owning `tenant_id`. JWT carries `tenant_id` only after that server-side resolution. No new tenant-owned tables added; the existing `widget_configs` already has `tenant_id UUID NOT NULL` per CONTRACT.md §8.1. No pgvector queries in this feature.
- [x] **Principle II (Layered Architecture):** Route ([app/api/routes/widgets.py](../../app/api/routes/widgets.py)) holds only request/response shaping and dependency wiring. Business logic — origin matching, tenant-active check, widget-enabled check, JWT minting, refusal-log emission — lives in `app/services/widget_service.py`. SQL access is confined to `app/repositories/widget_repo.py`. No SQL in the route; no business logic in the repository.
- [x] **Principle III (Bounded Agent):** N/A — this feature adds no agent tools and does not touch the agent loop. The set of tools (`rag_search`, `capture_lead`, `escalate`) remains exactly three. Marked ✓ as inapplicable.
- [x] **Principle IV (Defense-in-Depth Auth):** Widget token is a signed JWT (HS256). Frontend stores it in a module-scope `let` inside the iframe, never `localStorage`/`sessionStorage`/cookies (FR-011, FR-012). Origin is validated server-side against the `widget_configs.allowed_origins_json` allowlist (FR-002) — CORS is not used as authentication. The signing secret reads from env var `WIDGET_JWT_SECRET`; Vault integration is explicitly deferred to a separate feature owned by Ayoub. `.env` files remain gitignored.
- [x] **Principle V (Lean Serving & Redaction):** No `torch` / `transformers` added (this feature ships no ML). Refusal logs use HMAC-SHA256 hashed `widget_id` and hashed source IP, both with a per-deployment salt (FR-020, FR-021). The JWT signing secret and raw tokens never appear in any log. SC-009 commits to an automated redaction test on log samples.
- [x] **Principle VI (Phased Build):** This is constitution-Phase-7 work (Amer's slice — Widget, widget auth, origin allowlist). The team is currently in Phase 0. This is parallel-track work, not "ahead of phase" — see Complexity Tracking row 1 for the explicit interpretation. Cross-slice deps (`widget_configs` migration, `tenant.status` lookup, `add_audit_log` for future origin edits) all go through CONTRACT.md contracts; no teammate's file is touched.
- [x] **Principle VII (Clean & Simple Code):** Three new files added (route additions are minimal): `app/services/widget_service.py`, `app/repositories/widget_repo.py`, and one frontend `api.ts` helper. No speculative abstractions — no token revocation surface (deferred per Q2 clarification), no constant-time padding (deferred per Q5), no rate-limiter framework — the simplest correct rate baseline is implemented in-process per worker with optional Redis backing if the platform needs cross-worker counts. Canonical ID names used throughout (`tenant_id`, `widget_id`, `session_id`). Async everywhere. No `print`.

All seven boxes ticked. One nuance documented in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/001-widget-token-exchange/
├── plan.md                      # This file (/speckit-plan output)
├── spec.md                      # Feature specification (/speckit-specify output)
├── research.md                  # Phase 0 output (this command)
├── data-model.md                # Phase 1 output (this command)
├── quickstart.md                # Phase 1 output (this command)
├── contracts/                   # Phase 1 output (this command)
│   ├── widget-token-endpoint.md
│   └── widget-loader-postmessage.md
├── checklists/
│   └── requirements.md          # Quality checklist (/speckit-specify output)
└── tasks.md                     # Phase 2 output (/speckit-tasks - NOT created here)
```

### Source Code (repository root — files this feature touches)

```text
app/
├── api/
│   └── routes/
│       └── widgets.py           # (existing, owner Amer) — replace placeholder POST /widgets/token with real logic
├── services/
│   ├── widget_service.py        # NEW (owner Amer) — validation, JWT signing, orchestration
│   ├── widget_settings.py       # NEW (owner Amer) — pydantic-settings BaseSettings for WIDGET_* env vars
│   ├── widget_logging.py        # NEW (owner Amer) — structlog refusal/issuance emitters + trace-span context manager (FR-022)
│   └── rate_limiter.py          # NEW (owner Amer) — RateLimiter Protocol + InMemoryTokenBucketRateLimiter
├── repositories/
│   └── widget_repo.py           # NEW (owner Amer, schema reviewed by Hiba) — tenant-scoped widget_configs lookup; in-memory + SQL impls
├── domain/
│   └── widget.py                # NEW (owner Amer) — Pydantic request/response models for the route
├── config.py                    # (existing, owner Hiba) — read-only; this feature does NOT modify it (widget-scoped settings live in app/services/widget_settings.py)
└── infra/
    └── (no changes)             # Vault integration not done here

frontend/widget/
├── src/
│   ├── main.tsx                 # MODIFY (owner Amer) — fetch token on boot, render "Widget unavailable" on failure (UI shell only; full chat UI is Phase 2)
│   ├── api.ts                   # NEW (owner Amer) — fetch helper for /widgets/token; in-memory token store
│   └── types.ts                 # NEW (owner Amer) — TypeScript types matching the contract
├── public/
│   └── widget.js                # MODIFY (owner Amer) — postMessage(window.location.origin) to the iframe on boot
└── package.json                 # MODIFY (owner Amer) — add vitest, jsonwebtoken (for test-side verify), @types/node devDeps

tests/
├── security/
│   ├── test_widget_token.py     # NEW (owner Amer) — happy path, all refusal causes, response indistinguishability, tenant-active gate
│   └── test_widget_token_redaction.py   # NEW (owner Amer) — SC-009 hashed-identifier compliance
└── unit/
    └── test_widget_service.py   # NEW (owner Amer) — JWT minting, origin matching exactness, hashing salt usage

.env.example                     # MODIFY (owner Amer) — add WIDGET_JWT_SECRET (placeholder), WIDGET_TOKEN_TTL_SECONDS, WIDGET_RATE_PER_IP, WIDGET_RATE_PER_WIDGET, WIDGET_LOG_SALT
```

**Structure Decision**: The repository is already a multi-service monorepo (backend `app/` + frontend `frontend/widget/` + admin `admin/` + sidecars `modelserver/`, `guardrails/`). This feature touches the backend (route + service + repo + domain) and the widget (loader + iframe boot). It does NOT cross into any teammate's owned files — confirmed against the `# Owner: <Name>` headers and CONTRACT.md §2.9. Files marked **NEW** include a new file under `app/services/`, `app/repositories/`, and `app/domain/`; per Constitution Principle II (Layered Architecture) and CONTRACT.md §2.9 (Amer owns widget token exchange backend), these new files carry an `# Owner: Amer` header. The schema-touching repository functions are tagged for Hiba review at PR time per CONTRACT.md §4 cross-review rule.

## Phase 0: Research

See [research.md](research.md). Resolves three open technical questions: (1) JWT library choice (PyJWT vs python-jose), (2) rate-limiter implementation (in-process counter vs Redis-backed) for this phase, (3) HMAC salt provisioning for log identifiers. All three are concrete decisions, not blockers.

## Phase 1: Design & Contracts

- **Data model**: [data-model.md](data-model.md) — `widget_configs` row shape (re-used from CONTRACT.md §8.1, no schema change), `WidgetSessionToken` JWT claim shape, `WidgetTokenRefusalLog` structured-log shape.
- **Contracts**:
  - [contracts/widget-token-endpoint.md](contracts/widget-token-endpoint.md) — full HTTP contract for `POST /widgets/token` including the indistinguishable-refusal response shape.
  - [contracts/widget-loader-postmessage.md](contracts/widget-loader-postmessage.md) — the `postMessage` protocol the host-page loader uses to hand `window.location.origin` to the iframe.
- **Quickstart**: [quickstart.md](quickstart.md) — local-dev steps to seed a test widget config, exchange a token via curl, and verify the widget renders chat-ready in a browser.

## Complexity Tracking

> Filled because Principle VI carries a nuanced interpretation worth documenting.

| Item | Why it needs a note | Simpler alternative rejected because |
|------|---------------------|--------------------------------------|
| **Principle VI parallel-track interpretation.** This is constitution-Phase-7 (Amer's widget slice) being built while the team's *platform* is still in Phase 0. | PROJECT_PLAN.md's five-day plan explicitly schedules Amer to deliver widget token exchange on **Wednesday**, in parallel with Hiba's Phase-1 platform work and Nasser's Phase-2 RAG work. The constitution's intent is to prevent *reaching into another phase's files* (constitution §VI bullet 2), not to serialize the team. This feature stays inside Amer's owned files and consumes other phases only via CONTRACT.md contracts (widget_configs schema §8.1, audit_log §2.6, tenant status §8.1). | Serializing the team to one phase at a time would push this feature to week 2+ and break the demo schedule. The parallel-track interpretation is recorded here so a reviewer reading only the constitution doesn't flag it as a violation. |
| **In-memory `WidgetRepository` adapter behind the repository interface.** Hiba's `widget_configs` migration is not yet merged. | Without a real table, this feature cannot run end-to-end. The in-memory adapter implements the same async interface as the SQL adapter and is selected via the `WIDGET_REPO_BACKEND` env var. It will be deleted from the codebase the same PR cycle that introduces the SQL adapter against Hiba's migration. | Waiting on Hiba's migration would block all of Amer's downstream phases (chat UI consumes this token, admin UI edits the same table) and leave the demo schedule unrecoverable. The adapter is a documented temporary affordance, not an abstraction left in place. |

## Post-Design Constitution Re-Evaluation

After Phase 1 artifacts were written:

- **Principle I, II, IV, V, VII**: Unchanged — the design preserved every gate.
- **Principle III**: Still N/A.
- **Principle VI**: The contracts directory makes the cross-slice integration points explicit and machine-checkable; the data-model.md confirms that `widget_configs` is re-used as-is (no schema drift); the in-memory adapter is bounded by Complexity Tracking row 2 with a clear deletion trigger. Re-evaluation confirms the parallel-track interpretation holds.

All gates remain ticked. Ready for `/speckit-tasks`.
