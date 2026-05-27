# Implementation Plan: Admin Read-Only Pages

**Branch**: `005-admin-read-only-pages` | **Date**: 2026-05-27 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/005-admin-read-only-pages/spec.md`

## Summary

Ship the four read-only Streamlit admin pages — Tenant overview, CMS list, Leads viewer, Usage dashboard — as a single Spec Kit cycle. One foundational scaffold (sidebar wiring in [admin/streamlit_app.py](../../admin/streamlit_app.py)) routes a sidebar selection to four independently testable page modules under `admin/`. Each page is a single `render()` function that issues one `httpx` GET against a teammate's backend endpoint, parses defensively, and either renders real data or canned sample data tagged with a visible "(placeholder)" badge — same renderer code path either way. No write surface is introduced; the only mutating admin surface in the entire app remains the Widget page from Phase 4. Tests use `streamlit.testing.v1.AppTest` with `httpx.MockTransport` so the test suite needs no live backend.

## Technical Context

**Language/Version**: Python 3.11.
**Primary Dependencies**: Streamlit ≥ 1.32 (UI + `streamlit.testing.v1.AppTest`), `httpx` (sync `httpx.Client` for live calls, `httpx.MockTransport` for tests), `pytest`.
**Storage**: None at this layer. Admin pages call FastAPI via HTTP; backend endpoints own all SQL.
**Testing**: `pytest` + `streamlit.testing.v1.AppTest`; one integration test file per page in [tests/integration/](../../tests/integration/). Backend mocked at transport layer via `httpx.MockTransport`.
**Target Platform**: Streamlit admin app run locally and in the dev `docker-compose` stack; intended consumer is a tenant administrator on a desktop browser.
**Project Type**: Web admin UI (Streamlit) consuming an existing FastAPI backend over HTTP. No new backend code introduced by this slice.
**Performance Goals**: Initial render under 3 s per page on demo-scale data (<10 rows). No pagination, no caching layer.
**Constraints**: Read-only — no PUT/POST/DELETE/PATCH HTTP calls and no Save/Edit/Delete UI controls on any of the four new pages. Each page file targets ~120 LOC; shared helpers extracted only after duplication appears in implementation. Tenant scoping derived from trusted server-side context only (dev headers today, real admin session when Hiba's auth lands).
**Scale/Scope**: 1 admin app, 4 new page modules, 1 sidebar wiring change, 4 integration test files. Demo-scale data volumes (<100 rows per table in any environment this UI targets).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The plan MUST pass each gate before Phase 0 research and again after Phase 1 design. Cite the constitution principle by number in any waiver.

- [x] **Principle I (Tenant Isolation):** no new table introduced; every HTTP call relies on the backend's tenant scoping. The admin client sends an `X-Concierge-Tenant-Id` dev header (placeholder for Hiba's real admin auth — see Decision 5 in [DECISIONS.md](../../DECISIONS.md)). No `tenant_id` is read from a query string, URL fragment, or user-typed input anywhere in `admin/`. No SQL is executed from `admin/`.
- [x] **Principle II (Layered Architecture):** `admin/*` contains only UI render and HTTP-client code. No SQL, no business logic, no repository imports. Each `render()` formats data the backend returned and nothing more.
- [x] **Principle III (Bounded Agent):** N/A — no agent code, no tool, no prompt, no `rag_search` / `capture_lead` / `escalate` invocation touched. The agent's three-tool surface is unchanged.
- [x] **Principle IV (Defense-in-Depth Auth):** no new attack surface. The admin auth header is the same dev stand-in already in use by Phase 4's [admin/widget_page.py](../../admin/widget_page.py). Real admin session replaces it as a single follow-up when Hiba's admin auth slice lands. No widget token, CORS, or CSP rule is changed.
- [x] **Principle V (Lean Serving & Redaction):** no `torch` / `transformers` introduced. The Leads viewer redacts every rendered `contact` value to the first three characters plus asterisks before display (FR-009). No raw PII is persisted or logged by `admin/`.
- [x] **Principle VI (Phased Build):** sits squarely in Phase 8 (Admin UI — Amer-owned) per the constitution. Cross-phase consumption is via the documented endpoint shapes in [CONTRACT.md](../../CONTRACT.md) only — no reaching into Hiba's or Nasser's source files.
- [x] **Principle VII (Clean & Simple Code):** target ≤ ~120 LOC per page; one `render()` per file; no speculative helper extraction (the `admin/_admin_http.py` helper is created only if duplication appears in more than two pages, per the user-provided plan input). Canonical `tenant_id` naming. No `print`; logging via Streamlit error states only.

All gates pass — no entry needed under Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/005-admin-read-only-pages/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (read-only response shapes)
├── quickstart.md        # Phase 1 output (how to run & test the pages)
├── contracts/           # Phase 1 output (HTTP request shape per page)
│   ├── tenant-overview.md
│   ├── cms-list.md
│   ├── leads-viewer.md
│   └── usage-dashboard.md
├── spec.md              # Feature spec (from /speckit-specify)
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
admin/
├── __init__.py          # unchanged
├── streamlit_app.py     # MODIFIED: sidebar adds Tenant / CMS / Leads / Usage routes
├── widget_page.py       # UNCHANGED (Phase 4 — sole mutating admin surface)
├── tenant_page.py       # NEW — US1 Tenant overview
├── cms_page.py          # NEW — US2 CMS list + detail viewer
├── leads_page.py        # NEW — US3 Leads viewer (redacted contact)
├── usage_page.py        # NEW — US4 Usage dashboard (totals + line chart)
└── _admin_http.py       # NEW only-if-needed — shared dev headers / base_url helper.
                         # Created lazily once duplication appears in > 2 pages
                         # (Principle VII smallest-change).

tests/integration/
├── test_tenant_page.py  # NEW — happy + placeholder-fallback
├── test_cms_page.py     # NEW — happy + placeholder-fallback + status filter
├── test_leads_page.py   # NEW — happy + placeholder-fallback + status filter + redaction
└── test_usage_page.py   # NEW — happy + placeholder-fallback + line-chart datapoints
```

**Structure Decision**: Single-project admin UI layout extending the existing `admin/` package. No new top-level project; the FastAPI backend, widget runtime, modelserver, and guardrails stacks are untouched. The four pages each live in their own module beside [admin/widget_page.py](../../admin/widget_page.py), and the sidebar in [admin/streamlit_app.py](../../admin/streamlit_app.py) is extended to route to them. The shared helper `_admin_http.py` is *staged* in the structure but only materialized once we observe duplication in more than two pages during implementation (Principle VII — no speculative abstraction).

## Complexity Tracking

> No Constitution Check gates failed; this table is intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| —         | —          | —                                    |
