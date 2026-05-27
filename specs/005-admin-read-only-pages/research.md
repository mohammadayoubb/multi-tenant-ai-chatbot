# Phase 0 Research: Admin Read-Only Pages

**Branch**: `005-admin-read-only-pages` | **Date**: 2026-05-27

This document resolves every NEEDS CLARIFICATION from the plan's Technical Context and records the rationale for each technical choice. All decisions follow constitution Principle VII (smallest change satisfying the requirement; no speculative abstraction).

---

## Decision 1 — UI framework: Streamlit (already in place)

**Decision**: Continue with Streamlit (≥ 1.32) as the admin UI framework.

**Rationale**:
- Phase 8 of the constitution ([.specify/memory/constitution.md](../../.specify/memory/constitution.md)) names Streamlit as the admin UI. The existing app entrypoint [admin/streamlit_app.py](../../admin/streamlit_app.py) and the Phase 4 widget configuration page [admin/widget_page.py](../../admin/widget_page.py) already run on Streamlit.
- Streamlit's first-party test harness `streamlit.testing.v1.AppTest` (1.28+) supports headless rendering and direct widget interaction in `pytest`, which matches the test plan exactly.
- No second UI framework is needed; introducing one would violate Principle VII.

**Alternatives considered**:
- React/Next.js admin: rejected — outside the agreed admin stack for Phase 8 and would add a separate build/deploy chain.
- A FastAPI HTML template: rejected — would dilute the layered architecture (admin views straddling backend routes).

---

## Decision 2 — HTTP client: `httpx.Client` (sync)

**Decision**: Use `httpx.Client` (sync) for backend calls from each page's `render()`, matching the existing pattern in [admin/widget_page.py](../../admin/widget_page.py).

**Rationale**:
- Streamlit `render()` is sync. Mixing `asyncio` into Streamlit pages requires `asyncio.run()` inside `render()`, which is awkward and provides no observable benefit at demo-scale data volumes.
- Phase 4's widget page is already sync `httpx.Client`; matching that pattern keeps the admin codebase coherent for any reviewer (Principle VII).
- `httpx.MockTransport` lets tests intercept HTTP at the transport layer without a running backend.

**Alternatives considered**:
- `httpx.AsyncClient` inside `render()`: rejected — costlier in cognitive load with no win at this scale.
- `requests`: rejected — `httpx` is already a dependency, and `MockTransport` is materially easier than `responses` for clean per-test fixtures.

---

## Decision 3 — Auth: reuse Phase 4 dev headers

**Decision**: Every page sends the same dev headers as [admin/widget_page.py](../../admin/widget_page.py):

```python
{
  "X-Concierge-Role": "tenant_admin",
  "X-Concierge-Tenant-Id": "11111111-1111-1111-1111-111111111111",
  "X-Concierge-Actor-Id": "admin@example.com",
}
```

with a `TODO(hiba-handoff)` comment in the same line-style as widget_page.py.

**Rationale**:
- Decision 5 in [DECISIONS.md](../../DECISIONS.md) sanctions this dev stand-in pattern until Hiba's real admin auth slice lands.
- Reusing the exact header set means the handoff is a single grep-and-replace and matches a precedent the team has already accepted in review.
- No new attack surface (constitution Principle IV): the header is trusted only inside dev environments; backends still apply their own scoping rules.

**Alternatives considered**:
- Implementing a new admin JWT now: rejected — premature, blocks on Hiba's auth design, and is out of scope per spec Out-of-Scope section.
- Reading the tenant id from a Streamlit query param: rejected — would violate Principle I (trusted-context-only `tenant_id`).

---

## Decision 4 — Backend response shapes & contract gaps

**Decision**: Treat the documented response shapes in [CONTRACT.md](../../CONTRACT.md) as the source of truth, but parse defensively — required fields fail loud (raise) and optional/contract-gap fields default to `None`, `[]`, or `0`. Specifically:

| Endpoint | Spec source | Notes / gap |
|----------|-------------|-------------|
| `GET /tenants/{tenant_id}` | CONTRACT.md §2.6 (Tenant response) and §8.1 (`tenants` table) | The §2.6 JSON example shows `{id, name, status, created_at, updated_at}` but the `tenants` table schema also has `slug` and `plan`. Spec FR-004 requires `slug` and `plan` on the header card. Resolution: render `slug` and `plan` as optional fields displaying "—" if absent so the page does not crash if Hiba's response omits them in early dev. |
| Audit logs | CONTRACT.md §2.6 (`TenantRepository.list_audit_logs`) and §8.1 (`audit_logs` table) | No HTTP route is published yet. Resolution: page attempts `GET /tenants/{tenant_id}/audit-logs`; on 404 / placeholder, fall back to canned sample with the "(placeholder)" badge. The exact route is captured in [contracts/tenant-overview.md](contracts/tenant-overview.md) for handoff. |
| `GET /cms/pages` | CONTRACT.md §13 (API Route Naming) and §8.1 (`cms_pages` table) | Defined. Use `title, slug, status, updated_at` for the list, and `title, slug, body, source_url` for the detail viewer. |
| Leads list | CONTRACT.md §8.1 (`leads` table); ownership Nasser/Hiba review | No published route yet. Resolution: page attempts `GET /leads`; on 404 / placeholder, fall back. Captured in [contracts/leads-viewer.md](contracts/leads-viewer.md). |
| `tenant_usage` rollup | CONTRACT.md §8.1 (`tenant_usage` table) | No published HTTP rollup yet. Resolution: page attempts `GET /tenants/{tenant_id}/usage`; on 404 / placeholder, fall back. Captured in [contracts/usage-dashboard.md](contracts/usage-dashboard.md). |

**Rationale**: Phase 1 admin must be runnable for demos and tests before all teammate endpoints exist. The "(placeholder)" badge + canned sample data shaped per the documented table schemas keeps the demo path alive and keeps the renderer code path identical (constitution Principle VII — one code path, not two).

**Alternatives considered**:
- Block this slice on Hiba's audit-log HTTP route, Nasser's leads route, and Hiba's usage rollup route: rejected — would stall Phase 8 demo readiness for a slice that is otherwise read-only and risk-free.
- Build the admin against a richer fake server: rejected — `httpx.MockTransport` in tests already covers test isolation; runtime fallback is a tiny per-page constant.

---

## Decision 5 — Placeholder detection rule

**Decision**: A page renders canned sample data with the visible "(placeholder)" badge whenever **any** of the following is true:

1. The HTTP response status is **not 2xx** (covers 404 "not yet wired", any 4xx, and any 5xx), **OR**
2. The HTTP response status is **2xx** but the JSON body matches the placeholder marker described in CONTRACT.md or is missing every spec-required field for that page, **OR**
3. The HTTP request raises a transport error (`httpx.HTTPError` — connect timeout, DNS failure, refused connection, etc.).

In all three cases the page renders canned sample data (defined inline in the page module) and displays a small "(placeholder)" badge near the page header. The badge is a Streamlit `st.caption` or `st.warning` with the literal text `(placeholder)` — easy for AppTest to assert on. There are only two render paths anywhere on these four pages: **real data** and **placeholder**.

**Rationale**: Collapsing every failure mode into one fallback path keeps the renderer code identical for live, stub, and broken backends, satisfies FR-003 and FR-013 simultaneously, and means tests only need to cover two branches per page (happy / fallback). The original two-branch decision missed 5xx and network errors; this revision aligns the renderer with the spec's edge-case wording.

**Alternatives considered**:
- Separate `st.error("Could not load …")` branch for 5xx / network: rejected — adds a third render path and a third test branch for no operator benefit at demo scale; a visible "(placeholder)" badge already conveys "data is not real".
- Detect placeholder via a custom response header: rejected — requires teammate cooperation and complicates the contract.
- Throw on missing fields: rejected — directly contradicts FR-003 and SC-002.

---

## Decision 6 — Lead contact redaction

**Decision**: The Leads viewer renders the `contact` column by displaying the first 3 characters in clear text and replacing the rest with a literal `***` string (three asterisks), regardless of original length. For a contact shorter than 3 characters, render the available characters plus `***`.

```python
def redact_contact(value: str) -> str:
    head = value[:3]
    return f"{head}***"
```

**Rationale**:
- Matches FR-009 and constitution Principle V (mandatory redaction in any rendered surface).
- Single-line, trivially auditable, no dependence on the original length leaking how long the contact was.
- Edge cases tested explicitly in [tests/integration/test_leads_page.py](../../tests/integration/test_leads_page.py): empty string, 1 char, 3 chars, long contact.

**Alternatives considered**:
- Variable-length asterisks (one per masked character): rejected — leaks information about contact length.
- Hash-based redaction: rejected — overkill for in-app display and harder to test.

---

## Decision 7 — Testing: `streamlit.testing.v1.AppTest` + `httpx.MockTransport`

**Decision**: Each page has its own integration test file under `tests/integration/`. Tests use `AppTest.from_function(render, args=(client,))` (or equivalent) and inject an `httpx.Client(transport=httpx.MockTransport(handler))` so no live backend is needed. Assertions cover:

1. Happy path: mock returns the documented shape → table/card renders the expected fields.
2. Placeholder fallback: mock returns 404 or a placeholder body → page renders sample data **and** the literal `(placeholder)` text is visible.
3. Where applicable, widget interaction (CMS status filter, Leads status filter) updates the rendered rows.
4. For Usage: the `st.line_chart` element receives the expected per-day datapoints.

**Rationale**:
- AppTest is the standard test harness for Streamlit; introducing Playwright/Selenium would inflate the test surface for no extra coverage.
- `MockTransport` decouples tests from the FastAPI backend entirely, so this slice can ship without coordinating live endpoints.

**Alternatives considered**:
- End-to-end browser tests with Playwright: rejected — Phase 7 already owns widget smoke tests; admin AppTest is sufficient for read-only views.
- Pytest fixtures hitting a live FastAPI instance: rejected — couples the admin test suite to teammate timelines.

---

## Decision 8 — Page file ceiling and shared-helper extraction rule

**Decision**: Each page file targets ~120 LOC and stays self-contained. A shared helper `admin/_admin_http.py` is **only** materialized once duplicated logic (e.g., header construction, base-URL resolution, placeholder detection) appears in **more than two** of the new pages. Until then each page inlines its own tiny helpers.

**Rationale**: Direct application of constitution Principle VII ("the smallest change that satisfies the requirement; three obvious lines beat one clever abstraction"). Premature extraction is rejected explicitly in the user-provided plan input.

**Alternatives considered**:
- Build `_admin_http.py` up front: rejected — speculative abstraction.
- Inline everything forever: rejected only if/when duplication count crosses two — we revisit at the implementation/review stage.

---

## All NEEDS CLARIFICATION resolved

| Item | Resolution |
|------|------------|
| UI framework | Decision 1 — Streamlit |
| HTTP client | Decision 2 — `httpx.Client` sync |
| Auth header | Decision 3 — Phase 4 dev headers |
| Contract gaps for unpublished routes | Decision 4 — placeholder fallback |
| Placeholder detection | Decision 5 — 404 or missing required fields |
| Redaction algorithm | Decision 6 — first 3 chars + `***` |
| Test harness | Decision 7 — AppTest + MockTransport |
| Shared helper threshold | Decision 8 — > 2 pages duplication required |
