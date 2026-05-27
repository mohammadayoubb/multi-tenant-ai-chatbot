# Implementation Plan: Tenant Admin Widget Configuration Page

**Branch**: `004-widget-admin-config` | **Date**: 2026-05-27 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-widget-admin-config/spec.md`

## Summary

Extend the existing widget backend with two tenant-admin-scoped endpoints — `GET /widgets/config` and `PUT /widgets/config` — and wire a new Streamlit page ([admin/widget_page.py](../../admin/widget_page.py)) into the admin app so a tenant admin can view and edit their widget's allowed origins, theme JSON, greeting, and enabled flag. Origin additions and removals call `TenantRepository.add_audit_log(...)` (CONTRACT.md §line 190) with action `widget.origin_added` / `widget.origin_removed`; all other field changes are not audited. The token endpoint already reads `allowed_origins` and `enabled` live from `widget_configs` per token request (per /clarify Q2), so propagation is immediate without cache plumbing. Token revocation for removed origins is passive via the existing short JWT TTL (per /clarify Q1). Theme JSON is stored as a free-form blob (per /clarify Q3) — typed fields land in a later phase with the widget runtime's theme support.

The `tenant_admin` role check is mocked locally with a clearly-marked stand-in dependency that the implementation swaps for Hiba's role dep when it lands. The `widget_configs` row needs two new columns (`theme_json`, `greeting`) for full functionality; until Hiba's migration lands they're persisted in memory only via the existing `InMemoryWidgetRepository` test-affordance, with a clear TODO and Hiba-review flag.

## Technical Context

**Language/Version**: Python 3.11 (FastAPI backend, Streamlit admin); existing project pyproject pins.
**Primary Dependencies**: FastAPI ≥ 0.111, Pydantic v2, SQLAlchemy 2 async (via `app/db/session.py` — Hiba), httpx (already in dev deps for backend tests), Streamlit ≥ 1.32 (existing dep), `streamlit.testing` for frontend integration tests.
**Storage**: PostgreSQL via `widget_configs` row keyed by `tenant_id`. New columns required: `theme_json JSONB NULL`, `greeting TEXT NULL` (length-checked in app, not DDL). Schema change requires Hiba review.
**Testing**: pytest + httpx `AsyncClient` against FastAPI for backend; `streamlit.testing.v1.AppTest` for the admin page integration test. Existing widget test suite in `tests/security/test_widget_token*.py` and `tests/unit/test_widget_service.py` is unchanged.
**Target Platform**: Backend runs in the existing `api` container; admin runs in the existing `admin` Streamlit container. Same FastAPI app process for both endpoints.
**Project Type**: Web app — FastAPI backend + Streamlit frontend, both Amer-owned per Decision 5.
**Performance Goals**: GET /widgets/config: < 100ms p95 (single tenant-scoped DB read). PUT /widgets/config: < 250ms p95 (single update + at most N audit log writes where N = origins added + removed, typically ≤ 2). SC-008's 30-second admin round-trip target is dominated by human typing time, not the network.
**Constraints**:
- Tenant isolation (Principle I): every read and write scoped by `tenant_id` derived from the trusted role dependency, never the request body.
- Layered architecture (Principle II): route does validation + role gate; service does diff + audit + delegation; repo does SQL.
- Fail-closed on audit (FR-013): the widget update and the audit log entries MUST be in the same database transaction. If `add_audit_log` raises, the widget update rolls back.
- Mock role dep is a clearly-marked stand-in. It MUST be replaceable by a one-line FastAPI `Depends(...)` swap when Hiba's real dep lands — no surrounding refactor.
**Scale/Scope**: One tenant has one widget_config row. Tenants count today is single-digit (early stage). Origin list per tenant typically < 10 entries; audit log entries per save typically ≤ 2.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **Principle I (Tenant Isolation):** `widget_configs` already has `tenant_id UUID NOT NULL`. Both new endpoints derive `tenant_id` from the trusted role dependency (`tenant_admin` session/JWT), never the request body. The repository update function takes `tenant_id` as a required argument and includes it in the WHERE clause of every UPDATE. The cross-tenant negative test (SC-004) is required.
- [x] **Principle II (Layered Architecture):** route handles HTTP + role gate + Pydantic validation; service handles diff (added/removed origins), normalization (case-insensitive host, strip path/trailing slash), audit log calls, and transaction management; repository handles SQL. No layer is bypassed.
- [x] **Principle III (Bounded Agent):** N/A — no agent tool added, removed, or modified. The widget config is data, not an agent surface.
- [x] **Principle IV (Defense-in-Depth Auth):** the `tenant_admin` role check is the first defense; tenant scoping in the repo is the second. The widget token endpoint continues to validate origin live against `allowed_origins` server-side (per /clarify Q2) — no client-side check is introduced. Mocked role dep is marked as a stand-in with a clear TODO; it does NOT relax the contract.
- [x] **Principle V (Lean Serving & Redaction):** no new model artifacts, no `torch`/`transformers`. The audit log function call is the existing platform path; this feature does not write to the audit_logs table directly. Logs do not record raw origin lists for tenants beyond the audit log itself (which is the intended record).
- [x] **Principle VI (Phased Build):** Phase 8 (Admin UI) per the constitution. Per Decision 5 in DECISIONS.md, Amer's parallel-track is sanctioned for Amer-owned files. Cross-slice consumption (the audit log function, the role dep) is via shared contracts, not by reaching into Hiba's files.
- [x] **Principle VII (Clean & Simple Code):** Smallest change satisfying the spec. The new `WidgetConfigService` is added alongside the existing `WidgetTokenService` rather than overloading the token service. Mock role dep is a single function, clearly named, with a one-line TODO comment. No speculative caching, no premature abstraction over the audit log call.

All gates pass with no waivers. **Complexity Tracking** has two flagged affordances (the mock role dep and the schema-pending theme/greeting columns) — see below.

## Project Structure

### Documentation (this feature)

```text
specs/004-widget-admin-config/
├── plan.md              # This file
├── spec.md              # Feature spec (already complete + clarified)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output (end-to-end local walkthrough)
├── contracts/
│   ├── widget-config-endpoint.md   # GET /widgets/config + PUT /widgets/config
│   └── audit-log-consumption.md    # How this feature uses TenantRepository.add_audit_log
├── checklists/
│   └── requirements.md  # Spec quality checklist (already complete)
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
app/
├── api/
│   ├── deps.py                       # MODIFIED — add mock require_tenant_admin dependency
│   └── routes/
│       └── widgets.py                # MODIFIED — add GET + PUT /widgets/config alongside existing POST /widgets/token
├── domain/
│   └── widget.py                     # MODIFIED — WidgetConfigDomain gains theme_json, greeting; new WidgetConfigUpdateRequest + WidgetConfigResponse models
├── services/
│   └── widget_service.py             # MODIFIED — new WidgetConfigService class alongside existing WidgetTokenService
├── repositories/
│   └── widget_repo.py                # MODIFIED — WidgetRepository Protocol gains get_by_tenant_id + update_by_tenant_id; InMemoryWidgetRepository implements both

admin/
├── streamlit_app.py                  # MODIFIED — route the Widget tab to widget_page.render()
└── widget_page.py                    # NEW — origins editor, theme JSON editor with preview, greeting input, enabled toggle, Save button

tests/
├── security/
│   └── test_widget_admin_config.py   # NEW — happy-path, role gate, isolation, validation, audit-call assertions
├── unit/
│   └── test_widget_config_service.py # NEW — diff/normalize/audit-call logic
└── integration/
    └── test_admin_widget_page.py     # NEW — Streamlit AppTest harness exercising add/remove/save round-trip
```

**Structure Decision**: Backend slice + admin slice, both Amer-owned. Keep route/service/repo layering strict (Principle II). The new `WidgetConfigService` is its own class in the same `widget_service.py` file as `WidgetTokenService` because they share owner, file scope is already widget-focused, and splitting into two files at this size would be premature. The mock `require_tenant_admin` dependency lives in [app/api/deps.py](../../app/api/deps.py) so that swapping in Hiba's real dep is a one-line import change without touching the route file.

## Complexity Tracking

No constitutional violations. Two **temporary cross-team affordances** are flagged here for explicit visibility. They are not constitutional waivers but must be removed in the PR cycle that consumes the corresponding real dependencies:

| Affordance | Why needed now | Removed when |
|------------|---------------|--------------|
| Mock `require_tenant_admin` dependency in [app/api/deps.py](../../app/api/deps.py) | Hiba's authenticated role dependency does not exist yet. The feature is blocked without *some* way to gate the endpoints. The mock reads development headers (`X-Concierge-Role`, `X-Concierge-Tenant-Id`) and returns the same shape (`{tenant_id: UUID, actor_id: str \| None}`) the real dep will return. Marked clearly as a stand-in; raises in production environments by checking `ENVIRONMENT != "dev"`. | Hiba's authenticated role dep lands. The route's `Depends(...)` swaps to her import; no surrounding refactor. |
| `theme_json` and `greeting` persisted only in `InMemoryWidgetRepository` | The columns don't exist in the `widget_configs` table yet. The InMemory implementation stores them in its dict. The SQL adapter continues to raise `NotImplementedError` for the SQL backend, matching the existing pattern. | Hiba's `widget_configs` migration adds `theme_json JSONB NULL` and `greeting TEXT NULL`. The SQL adapter (currently unimplemented) can then read/write them. **Tagged for Hiba review** before merge. |
