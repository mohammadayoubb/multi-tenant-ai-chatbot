# Quickstart: Tenant Admin Widget Configuration

**Feature**: 004-widget-admin-config
**Audience**: anyone on the team pulling this branch who wants to run the tests, exercise the endpoints locally, or sanity-check the admin Streamlit page in a browser.

---

## Prerequisites

- Python 3.11 with the project's dev deps installed (`pip install -e ".[dev]"` from repo root).
- For the admin UI: Streamlit 1.32+ (already pinned).
- For end-to-end browser testing: the `api` and `admin` docker containers, OR `uvicorn app.main:app` + `streamlit run admin/streamlit_app.py` locally.

No `widget_configs` migration is required for tests — the `InMemoryWidgetRepository` is the default backend (per `WIDGET_REPO_BACKEND=memory`). Hiba's real schema migration will replace it later.

---

## 1. Run the backend tests

```sh
pytest tests/security/test_widget_admin_config.py tests/unit/test_widget_config_service.py -v
```

Expected: all contract clauses E1–E5 pass, plus the unit-layer diff/normalize/audit cases.

Full backend suite:

```sh
pytest -v
```

Should remain green; this feature adds tests but doesn't modify existing ones.

---

## 2. Run the admin frontend test

```sh
pytest tests/integration/test_admin_widget_page.py -v
```

Uses `streamlit.testing.v1.AppTest` with a fake HTTP client — no live FastAPI or browser needed.

---

## 3. Exercise the endpoints locally with `curl`

In one terminal:

```sh
ENVIRONMENT=dev uvicorn app.main:app --reload --port 8000
```

In another, **read** the current widget config (mock dev auth via headers):

```sh
curl -s http://localhost:8000/widgets/config \
  -H "X-Concierge-Role: tenant_admin" \
  -H "X-Concierge-Tenant-Id: 11111111-1111-1111-1111-111111111111" | jq
```

Expected: 200 OK with the fixture row (the `InMemoryWidgetRepository` seeds tenant `11111111-...` with `https://customer-site.example` and `http://localhost:5500`).

**Write** an updated config:

```sh
curl -sX PUT http://localhost:8000/widgets/config \
  -H "Content-Type: application/json" \
  -H "X-Concierge-Role: tenant_admin" \
  -H "X-Concierge-Tenant-Id: 11111111-1111-1111-1111-111111111111" \
  -d '{
    "allowed_origins": ["https://customer-site.example", "https://new.customer-site.example"],
    "enabled": true,
    "theme_json": {"primary": "#ff0066"},
    "greeting": "Hi from Acme"
  }' | jq
```

Expected: 200 OK with the new state echoed back, and one `widget.origin_added` audit log entry recorded for `https://new.customer-site.example`. Check the server logs for the audit-log call line.

**Role gate** (omit the role header):

```sh
curl -sX PUT http://localhost:8000/widgets/config \
  -H "Content-Type: application/json" \
  -H "X-Concierge-Tenant-Id: 11111111-1111-1111-1111-111111111111" \
  -d '{"allowed_origins":["https://x.com"],"enabled":true}' -w '\n%{http_code}\n'
```

Expected: 403 with body `{"error":"forbidden"}`.

---

## 4. Sanity-check the admin Streamlit page

In one terminal (after starting `uvicorn` per §3):

```sh
streamlit run admin/streamlit_app.py
```

Then open `http://localhost:8501/`, pick the **Widget** tab in the sidebar. You should see:

- The current origins list, with an "Add origin" input and a "Remove" button per row.
- A theme JSON textarea (empty by default) with an inline JSON parse-error indicator if you type invalid JSON.
- A greeting text input with a 280-character cap.
- An "Enabled" toggle.
- A "Save" button (disabled while any field has a validation error).

Save behavior: clicking Save issues one PUT, then displays the server's response. A successful save shows "Saved." and re-fetches the row.

**Mock auth in dev**: the Streamlit page hard-codes the dev headers (`X-Concierge-Role: tenant_admin`, `X-Concierge-Tenant-Id: 11111111-...`) until Hiba's session-based admin auth lands.

---

## 5. Verify cross-tenant isolation

With `uvicorn` running, attempt to read another tenant's config (a non-existent tenant id):

```sh
curl -s http://localhost:8000/widgets/config \
  -H "X-Concierge-Role: tenant_admin" \
  -H "X-Concierge-Tenant-Id: 22222222-2222-2222-2222-222222222222" -w '\n%{http_code}\n'
```

Expected: 403 with body `{"error":"forbidden"}` — **same response** as the role-missing case, so a tenant id's existence cannot be inferred from the response.

---

## 6. CI-equivalent local sweep

Before opening the PR, run the full local CI equivalent:

```sh
ruff check .
pytest
cd frontend/widget && npm test && cd -
# docker compose build (optional — slow; run if Dockerfiles changed)
```

The widget vitest suite (52 cases from feature 003) should remain green. This feature doesn't modify the widget loader or any TypeScript code.

---

## 7. Cleanup of temporary affordances

Two items in this PR are temporary affordances that future PRs remove (per plan.md Complexity Tracking):

- `app/api/deps.py:require_tenant_admin` — mock role dep, replaced by Hiba's authenticated role dependency.
- `theme_json` and `greeting` only persisted in `InMemoryWidgetRepository` — replaced when Hiba's `ALTER TABLE widget_configs ADD COLUMN theme_json, greeting` migration lands.

Both are marked with `# TODO(hiba-handoff):` comments in the code so they show up in a single grep.
