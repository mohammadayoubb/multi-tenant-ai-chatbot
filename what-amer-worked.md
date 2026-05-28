# what-amer-worked.md

Personal scratch doc. Gitignored. Not shared with the team.

---

## 1. What we finished

### Feature 008 — Demo Polish (this branch, `008-demo-polish`)

| Change | File | Purpose |
|---|---|---|
| Added "Embed the widget" section | [README.md](README.md) | Copy-pasteable `<script src=… data-widget-id=… data-backend-url=…>` snippet for tenants |
| Rewrote Demo Flow as 9 numbered steps + "Run smoke test" | [RUNBOOK.md](RUNBOOK.md) | Each step now has the actual command and what to watch for |
| `admin → api` long-form `condition: service_healthy` | [docker-compose.yml](docker-compose.yml) | Eliminated cold-start race; admin no longer starts before api is healthy |
| New top-level entry point | [Makefile](Makefile) | One target `lean-image-audit`; thin wrapper around the script |
| Lean-image audit | [scripts/check_lean_images.sh](scripts/check_lean_images.sh) | Runs `pip list` inside modelserver+guardrails; fails on `torch`/`transformers`. Enforces Constitution Principle V |
| New CI job `lean-image-audit` + fixed two pre-existing CI bugs | [.github/workflows/ci.yml](.github/workflows/ci.yml) | (1) added constitutional gate (2) `lint-test-build` no longer discovers smoke tests (3) smoke-e2e seeds `.env` |
| Decision 11 | [DECISIONS.md](DECISIONS.md) | Recorded lean-image audit + compose race fix (constitution §Development Workflow requires this for CI changes) |
| Per-person blocker inventory | [BLOCKED.md](BLOCKED.md) | Hiba/Nasser/Ayoub blocking items + this branch's unfinished-but-not-blocked items |

### Verifications run

- **T004**: cold-start sanity ✓ (you ran)
- **T006**: README snippet works against host-test.html ✓ (you ran)
- **T011**: lean-image-audit clean → exit 0, "clean (2 images, 2 regexes)" ✓
- **T013**: failure path → exit 1, `multi-tenant-ai-chatbot-modelserver: forbidden package torch (matched: torch==2.12.0)`. Dockerfile reverted ✓
- **T015**: 3/3 cold-start cycles healthy in ~16s each; admin proven to wait on api-healthy ✓
- **T009 (skipped)**: clean-clone runbook walk — see BLOCKED.md §3 U1

### Prior Amer features (shipped, on amer-init-spec)

001 widget-token-exchange · 002 widget-chat-ui · 003 widget-loader-hardening · 004 widget-admin-config · 005 admin-read-only-pages · 006 ci-eval-gates · 007 cross-tenant-smoke-e2e

---

## 2. How to use each tool

### Local stack

```bash
cp .env.example .env       # one time per clone
docker compose up --build --wait    # builds, starts, blocks until all healthchecks pass
docker compose ps                   # service status
docker compose down -v              # stops + wipes volumes (DB, MinIO)
docker compose logs <service>       # logs for one service
```

### Seed tenants

```bash
python scripts/seed_tenants.py      # inserts demo Tenant A + B with widgets and CMS rows
```

### Lean-image audit (constitution Principle V gate)

```bash
docker compose build modelserver guardrails
make lean-image-audit               # on machines with make
bash scripts/check_lean_images.sh   # on Windows without make (e.g., this dev box)
```

Exit codes: `0` clean · `1` torch/transformers found · `2` image missing · `64` usage error.

### Smoke test (cross-tenant E2E)

```bash
# Against a running local stack (the canonical local invocation):
pytest tests/smoke/

# CI-equivalent wrapper with phase-gate flag handling:
python scripts/smoke_check.py -v
SMOKE_E2E_REQUIRE_FULL_STACK=0 pytest tests/smoke/   # xfail probes whose upstream phase hasn't shipped
```

### Lint / type / unit tests

```bash
ruff check .          # lint
mypy app/             # type check (strict)
pytest --ignore=tests/smoke   # unit + integration + security tests (no stack needed)
pytest                # everything — only when a local stack is up
```

### Widget host-test page

Open `http://localhost:5173/host-test.html` once the stack is up. Loads `public/widget.js` (verbatim, ES2019, no bundle) with the seeded demo widget id. DevTools → Network → `POST /widgets/token` 200 confirms the token exchange path.

### Admin UI (Streamlit)

`http://localhost:8501`. Pages: tenant overview, CMS list, leads viewer, usage dashboard, widget config. All read-only except widget config. Dev auth via `X-Concierge-Role` / `X-Concierge-Tenant-Id` headers (mock until Hiba's auth lands — see BLOCKED.md H1, H4).

### CI eval gates (locally)

```bash
python -m evals.classifier --output classifier-eval.json
python scripts/check_threshold.py --gate classifier --metric macro_f1_min --json classifier-eval.json
# Same shape for rag, agent_tool, red_team, redaction. All mocks for now (DECISIONS Decision 9).
```

---

## 3. File-by-file explanation (Amer-owned)

### Top-level docs

| File | What it does |
|---|---|
| [README.md](README.md) | Project intro + "Run Locally" + new "Embed the widget" |
| [RUNBOOK.md](RUNBOOK.md) | Demo Flow + smoke test + run/lint/type-check commands |
| [DECISIONS.md](DECISIONS.md) | Major decisions log (constitution-required) |
| [BLOCKED.md](BLOCKED.md) | What's blocked on which teammate; what's deferred but not blocked |
| [.gitignore](.gitignore) / [.dockerignore](.dockerignore) | Standard ignores + Amer's personal docs + smoke-runner artifacts |
| [.pre-commit-config.yaml](.pre-commit-config.yaml) | ruff + mypy hooks |

### Build & CI

| File | What it does |
|---|---|
| [Dockerfile](Dockerfile) | Multi-stage: `base` → `api`, `modelserver`, `guardrails`, `admin`. Lean (no torch/transformers in serving stages) |
| [docker-compose.yml](docker-compose.yml) | All services + healthchecks + `depends_on … service_healthy` ordering |
| [Makefile](Makefile) | Single entry point `lean-image-audit` |
| [.github/workflows/ci.yml](.github/workflows/ci.yml) | Jobs: lint-test-build → lean-image-audit + five eval gates → smoke-e2e |
| [frontend/widget/Dockerfile](frontend/widget/Dockerfile) | Node 20 alpine, `vite --host 0.0.0.0` |

### Scripts

| File | What it does |
|---|---|
| [scripts/check_lean_images.sh](scripts/check_lean_images.sh) | Audits modelserver/guardrails for forbidden Python packages. Contract: [008/contracts/lean-image-audit-cli.md](specs/008-demo-polish/contracts/lean-image-audit-cli.md) |
| [scripts/smoke_check.py](scripts/smoke_check.py) | Wraps `pytest tests/smoke/` with API-up gating + 30s health-poll. The CI smoke runner |
| [scripts/check_threshold.py](scripts/check_threshold.py) | Reads eval CLI JSON, compares to `eval_thresholds.yaml`, exits non-zero on miss. Used by every eval CI gate |
| [scripts/seed_tenants.py](scripts/seed_tenants.py) | Seeds Tenant A / B for demo + smoke. Not Amer's primary slice but used by RUNBOOK |

### Widget slice (Phase 7) — backend

| File | What it does |
|---|---|
| [app/api/routes/widgets.py](app/api/routes/widgets.py) | `POST /widgets/token` (anonymous), `GET/PUT /widgets/config` (tenant-admin) |
| [app/services/widget_service.py](app/services/widget_service.py) | Token issuance, origin validation, AuditLogger Protocol, config logic |
| [app/services/widget_settings.py](app/services/widget_settings.py) | Vault-backed JWT secret + token TTL settings |
| [app/services/widget_logging.py](app/services/widget_logging.py) | Redacted log helpers for the widget surface |
| [app/services/rate_limiter.py](app/services/rate_limiter.py) | Per-IP and per-widget rate baselines on `/widgets/token` (Decision 4) |
| [app/repositories/widget_repo.py](app/repositories/widget_repo.py) | `InMemoryWidgetRepository` (dev) + SQL adapter stub (blocked on Hiba's migration — BLOCKED.md H2) |
| [app/domain/widget.py](app/domain/widget.py) | `WidgetConfigDomain` Pydantic model (carries `theme_json`, `greeting` with `None` defaults) |
| [app/api/deps.py](app/api/deps.py) (Amer's section) | Mock `require_tenant_admin` reading dev headers (BLOCKED.md H1) |

### Widget slice — frontend (`frontend/widget/`)

| Sub-area | What it does |
|---|---|
| `public/widget.js` | Hand-authored ES2019 loader. Reads `data-*` attrs from `currentScript`; injects iframe |
| `public/host-test.html` | Local sanity-check page (the practical "substituted README snippet") |
| `src/main.tsx` + components | React iframe app (chat UI from feature 002) |
| `src/api.ts` | `POST /widgets/token` + `POST /chat` client; in-memory token only |
| `vite.config.ts` | ES2019 target; dev-only proxy `/widgets` + `/chat` → `api:8000` |
| `vitest.config.ts` + `src/__tests__/` | Loader + chat + api unit tests; harness for the loader |

### Admin slice (Phase 8) — `admin/`

| File | What it does |
|---|---|
| `streamlit_app.py` | Sidebar nav + page registry |
| `tenant_page.py` | Tenant overview + audit log view (placeholder fallback — BLOCKED.md H5) |
| `cms_page.py` | CMS pages list (placeholder fallback — BLOCKED.md N9) |
| `leads_page.py` | Leads viewer (placeholder fallback — BLOCKED.md N8) |
| `usage_page.py` | Usage dashboard (placeholder fallback — BLOCKED.md H6) |
| `widget_page.py` | Widget configuration (the one mutating admin page) |
| `_admin_http.py` | Shared httpx client + dev `X-Concierge-*` headers (BLOCKED.md H4) |

### Tests Amer owns

| Path | What it does |
|---|---|
| `tests/smoke/test_cross_tenant_e2e.py` | Seven cross-tenant isolation probes against a live stack |
| `tests/smoke/test_widget_token_smoke.py` | Anonymous `/widgets/token` happy + error paths |
| `tests/security/test_widget_token*.py` | Signed JWT, origin allowlist, rate-limiter, redaction |
| `tests/security/test_widget_admin_config.py` | `tenant_admin` role enforcement, audit-on-write semantics |
| `tests/unit/test_widget_service.py` + `test_widget_config_service.py` | Service-layer unit tests |
| `tests/integration/test_*_page.py` + `_*_page_entry.py` | Streamlit page integration tests (mocked httpx transport) |

### Eval gates plumbing (Phase 10)

| File | What it does |
|---|---|
| [evals/__init__.py](evals/__init__.py) | Package marker; eval modules live under here (mocks owned by Ayoub/Nasser — BLOCKED.md N5/N6/A1/A2/A3) |
| [scripts/check_threshold.py](scripts/check_threshold.py) | Threshold checker (contract: [006/contracts/threshold-checker.md](specs/006-ci-eval-gates/contracts/threshold-checker.md)) |
| [eval_thresholds.yaml](eval_thresholds.yaml) | Threshold values; missing `rag.mrr_min` (BLOCKED.md A4) |

---

## Quick references

- Constitution: [.specify/memory/constitution.md](.specify/memory/constitution.md) — Principle V is the one this branch enforces
- Active spec: [specs/008-demo-polish/](specs/008-demo-polish/) — spec, plan, research, tasks, contracts, quickstart
- Per-handoff TODO grep:
  ```bash
  grep -rn "TODO(hiba-handoff)\|TODO(nasser-handoff)\|TODO(ayoub-handoff)\|TEMPORARY MOCK\|_StubAuditLogger\|InMemoryWidgetRepository\|@require_full_stack" \
    app/ admin/ evals/ tests/ scripts/ .github/
  ```
