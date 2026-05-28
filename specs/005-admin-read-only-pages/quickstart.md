# Quickstart — Admin Read-Only Pages

**Branch**: `005-admin-read-only-pages`
**Audience**: anyone who wants to run, demo, or test the four new admin pages locally.

## Prerequisites

- Python 3.11
- The repo's existing virtualenv / `pyproject.toml` dependencies installed
- (Optional, for live data) FastAPI backend running at `CONCIERGE_BACKEND_URL` (default `http://localhost:8000`)

## Run the admin app

From the repo root:

```bash
streamlit run admin/streamlit_app.py
```

Open the URL Streamlit prints (default `http://localhost:8501`).

The sidebar now exposes five tabs:

| Tab | Module | Source |
|-----|--------|--------|
| Tenant | `admin/tenant_page.py` | NEW (US1) |
| CMS | `admin/cms_page.py` | NEW (US2) |
| Leads | `admin/leads_page.py` | NEW (US3) |
| Usage | `admin/usage_page.py` | NEW (US4) |
| Widget | `admin/widget_page.py` | UNCHANGED (Phase 4) |

## What you should see

### With no backend running (or backend at placeholder mode)

Each new page renders canned sample data with a visible `(placeholder)` badge near the page header. The Widget tab is unaffected (it has its own error handling from Phase 4).

This is the demo-safe default — the slice ships even before teammates' endpoints are live.

### With a live backend

Each new page issues exactly one `GET` per render and surfaces real data:

- **Tenant**: `GET /tenants/{tenant_id}` (live) + `GET /tenants/{tenant_id}/audit-logs` (when Hiba ships it; otherwise falls back).
- **CMS**: `GET /cms/pages`.
- **Leads**: `GET /leads` (when Nasser ships it; otherwise falls back).
- **Usage**: `GET /tenants/{tenant_id}/usage` (when Hiba ships it; otherwise falls back).

`{tenant_id}` is taken from the `X-Concierge-Tenant-Id` dev header (currently the fixture UUID `11111111-1111-1111-1111-111111111111`). When Hiba's real admin auth lands, this header is replaced with the trusted session value — no other page logic changes.

## Run the tests

```bash
pytest tests/integration/test_tenant_page.py \
       tests/integration/test_cms_page.py \
       tests/integration/test_leads_page.py \
       tests/integration/test_usage_page.py
```

Each file covers (at minimum):

1. **Happy path** — `httpx.MockTransport` returns the documented response shape → page renders real data, no `(placeholder)` badge.
2. **Placeholder fallback** — `MockTransport` returns 404 (or a placeholder body) → page renders sample data **and** the literal `(placeholder)` text is visible.
3. **Filter interaction** (CMS, Leads only) — selecting a status narrows the rendered rows.
4. **Line chart datapoints** (Usage only) — the rendered `st.line_chart` receives the expected per-day series.

No live backend is required; total runtime should be under 30 s locally (SC-005).

## Verify the read-only invariant

Manual check before opening a PR:

```bash
# Should print NOTHING for the four new page modules.
grep -nE "client\.(put|post|delete|patch)\(|st\.button.*Save|st\.button.*Delete|st\.form_submit_button" \
     admin/tenant_page.py admin/cms_page.py admin/leads_page.py admin/usage_page.py
```

The Widget page from Phase 4 is the **only** mutating admin surface (FR-002, FR-006, FR-008, FR-010, FR-012).

## Verify lead contact redaction

In the Leads viewer with the placeholder dataset:

- One row has the contact `avery@example.com` → table renders `ave***`.
- One row has a 1-character contact `"a"` → table renders `a***`.
- One row has an empty contact `""` → table renders `***`.

No row should display the unredacted contact anywhere on the page (Principle V, FR-009, SC-004).

## Troubleshooting

- **Page is blank or shows an error banner**: confirm the backend URL via `CONCIERGE_BACKEND_URL`, then re-run. If the error persists, switch off the backend to confirm the placeholder fallback works — that isolates whether the issue is the renderer or the live response shape.
- **AppTest fails with `httpx.ConnectError`**: the mock transport is not wired in. Confirm tests construct the page's `httpx.Client(transport=MockTransport(handler))` and inject it into `render()` (or set the page's HTTP client factory to return that client).
- **Widget tab broke**: it shouldn't have — this slice doesn't touch [admin/widget_page.py](../../admin/widget_page.py). If it did, revert and check the sidebar change in [admin/streamlit_app.py](../../admin/streamlit_app.py).
