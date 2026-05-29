# Owner: Amer
# BLOCKED.md

Single source of truth for work that is **not done** in this repo and **why**. Each entry names the blocked artifact, the swap-replaceable affordance currently in its place (if any), the file(s) where the handoff lands, and the authoritative reference (a `DECISIONS.md` entry or spec section).

This file is committed (it is **not** gitignored). Update it whenever:

- a teammate's slice lands and a blocked item becomes unblocked → strike the entry and move to a "Resolved" log if you want to keep history.
- a new blocking dependency is discovered → add a new entry under the right owner.
- a task in the active spec was not completed and was not blocked → add it under §3.

Last updated: 2026-05-29 (Feature [010-fe-be-integration](specs/010-fe-be-integration/spec.md) Phase 7 T104). N6 graduated; Track-1 13 endpoints + Track-2 agent loop landed; `SMOKE_E2E_REQUIRE_FULL_STACK` stays `"0"` because **N1 (RAG indexing of CMS pages into `rag_chunks`)** remains the one Track-2 gap — cross-tenant content probes (P1/P2) still depend on it.

---

## 1. Blocked on teammate code

### 1.1 Blocked on Hiba (Phase 1 — platform, tenancy, RLS, audit; Phase 9 — erasure)

| # | Blocked artifact | Current affordance | Files | Reference |
|---|------------------|--------------------|-------|-----------|
| ~~H1~~ | ~~**Authenticated `tenant_admin` role dependency**~~ | ~~Mock `require_tenant_admin` reads `X-Concierge-Role` / `X-Concierge-Tenant-Id` dev headers and refuses outside `CONCIERGE_ENV=dev`. Swap-replaceable by Hiba's real dep with a single import change.~~ | ~~[app/api/deps.py](app/api/deps.py) (TODO marker line 37)~~ | ~~[DECISIONS.md](DECISIONS.md) §Decision 7~~ |
| H1b | **`get_tenant_id_from_widget_token` JWT verifier** ✅ resolved 2026-05-28 | Implemented in [app/api/deps.py](app/api/deps.py): HS256 verify with `WIDGET_JWT_SECRET`, return `tenant_id` claim as UUID, single-401 collapse on any failure. The mock `require_tenant_admin` for the admin-role dep is still in place (see H4 for the admin-session handoff). | [app/api/deps.py](app/api/deps.py) | [specs/001-widget-token-exchange/contracts/widget-token-endpoint.md](specs/001-widget-token-exchange/contracts/widget-token-endpoint.md) "Out of scope" §1 |
| ~~H2~~ | ~~**`widget_configs` migration adding `theme_json JSONB` and `greeting TEXT` columns**~~ ✅ resolved 2026-05-28 | `widget_configs` table created in migration `0004_contract_schema_parity.py` (theme_json JSONB, greeting TEXT, allowed_origins_json JSONB, enabled BOOL, RLS-enabled). `SqlWidgetRepository` in [app/repositories/widget_repo.py](app/repositories/widget_repo.py) implements the `WidgetRepository` Protocol; `get_widget_repository` returns it when `WIDGET_REPO_BACKEND=sql`. Verified end-to-end: SQL-mode container issues a valid 200 JWT against a seeded `widget_configs` row. `scripts/seed_widget_config.py` provisions the demo row. | [app/repositories/widget_repo.py](app/repositories/widget_repo.py), [scripts/seed_widget_config.py](scripts/seed_widget_config.py), [tests/integration/test_sql_widget_repo.py](tests/integration/test_sql_widget_repo.py) | [DECISIONS.md](DECISIONS.md) §Decision 14 |
| ~~H3~~ | ~~**`TenantRepository.add_audit_log` implementation**~~ ✅ resolved 2026-05-28 | `_StubAuditLogger` deleted; [app/api/routes/widgets.py](app/api/routes/widgets.py) `get_audit_logger` now returns `TenantRepository(session)` from a session-bound dep. Audit rows commit/rollback with the request's unit of work. The widget admin config tests still override `get_widget_config_service` directly, so no test rewrite was needed. | [app/api/routes/widgets.py](app/api/routes/widgets.py), [app/repositories/tenant_repo.py](app/repositories/tenant_repo.py) | [DECISIONS.md](DECISIONS.md) §Decision 7 |
| ~~H4~~ | ~~**Real admin session**~~ ✅ resolved 2026-05-28 | `admin_users` table + alembic migration `0002_admin_users.py` (RLS-enabled); `POST /admin/login` mints an HS256 JWT signed with `ADMIN_JWT_SECRET`; Streamlit login page gates all admin pages; `_admin_http.py` attaches `Authorization: Bearer <jwt>` from `st.session_state` (in-process, never browser storage). Dev-header fallback in `require_tenant_admin` is retained but only active when `CONCIERGE_ENV=dev`. Seed via `python -m scripts.seed_admin --email … --tenant-id … --password …`. | [app/api/routes/admin_auth.py](app/api/routes/admin_auth.py), [app/services/admin_auth.py](app/services/admin_auth.py), [admin/login_page.py](admin/login_page.py), [admin/_admin_http.py](admin/_admin_http.py), [scripts/seed_admin.py](scripts/seed_admin.py) | [DECISIONS.md](DECISIONS.md) §Decision 11 |
| ~~H5~~ | ~~**Live tenant audit-log read endpoint**~~ ✅ resolved 2026-05-28 | `GET /tenants/{tid}/audit-logs` in [app/api/routes/tenants.py](app/api/routes/tenants.py): admin-JWT auth (`require_admin_session`), refuses cross-tenant paths with 403, returns `AuditLogDomain` rows via `TenantRepository.list_audit_logs`. | [app/api/routes/tenants.py](app/api/routes/tenants.py), [tests/integration/test_admin_read_endpoints.py](tests/integration/test_admin_read_endpoints.py) | — |
| ~~H6~~ | ~~**Live tenant usage rollup endpoint**~~ ✅ resolved 2026-05-28 | `GET /tenants/{tid}/usage?days=30` in [app/api/routes/tenants.py](app/api/routes/tenants.py); rollup query in [app/repositories/tenant_repo.py](app/repositories/tenant_repo.py) (`usage_rollup`) aggregates `tenant_usage` into the `{total_tokens, total_cost_usd, by_feature, daily_cost_usd}` shape that `admin/usage_page.py` consumes. | [app/api/routes/tenants.py](app/api/routes/tenants.py), [app/repositories/tenant_repo.py](app/repositories/tenant_repo.py) | — |
| H7 | **`POST /tenants` + `tenants` table** | Smoke probes that need to create a tenant are wrapped in `@require_full_stack("phase-1+2+5: ...")` → strict-xfail while `SMOKE_E2E_REQUIRE_FULL_STACK=0`. | [tests/smoke/test_cross_tenant_e2e.py](tests/smoke/test_cross_tenant_e2e.py) line 250, 514, 554 | [DECISIONS.md](DECISIONS.md) §Decision 10 |
| H8 | **`audit_logs` table + escalate-side audit row** | Smoke probe wrapped in strict-xfail with reason `phase-1: audit_logs table + escalate-side audit entry`. | [tests/smoke/test_cross_tenant_e2e.py](tests/smoke/test_cross_tenant_e2e.py) line 747 | [DECISIONS.md](DECISIONS.md) §Decision 10 |
| H9 | **RLS / repository tenant-filter on `leads`** | Smoke probe wrapped in strict-xfail with reason `phase-1: RLS / repository tenant filter on leads`. | [tests/smoke/test_cross_tenant_e2e.py](tests/smoke/test_cross_tenant_e2e.py) line 695 | [DECISIONS.md](DECISIONS.md) §Decision 10 |

**Contract for Hiba**: when any of H1–H9 lands, the same PR MUST replace the affordance (delete the TODO comment / drop the stub / drop the in-memory adapter) and, if the change unblocks a smoke probe, flip `SMOKE_E2E_REQUIRE_FULL_STACK` to `"1"` in [.github/workflows/ci.yml](.github/workflows/ci.yml) line 262. The strict-xfail mechanism will fail CI on XPASS until the flag is flipped.

---

### 1.2 Blocked on Nasser (Phase 2 — CMS / RAG; Phase 4 — router; Phase 5 — agent / tools)

| # | Blocked artifact | Current affordance | Files | Reference |
|---|------------------|--------------------|-------|-----------|
| N1* | **`POST /cms/pages` + `cms_pages` table + RAG indexing** — *partial* | Route + table done; RAG ingestion deferred. `POST /cms/pages` (admin-JWT auth, body validates `extra=forbid` so tenant_id can't be smuggled) added in [app/api/routes/cms.py](app/api/routes/cms.py); `cms_pages` columns now match contract (slug/source_url/status/created_by) via migration `0004_contract_schema_parity.py`. **Still blocked**: RAG indexing of created pages into `rag_chunks` (Nasser — depends on embedding pipeline). Smoke probes at lines 310/514/554 stay xfail until indexing lands. | [app/api/routes/cms.py](app/api/routes/cms.py), [tests/smoke/test_cross_tenant_e2e.py](tests/smoke/test_cross_tenant_e2e.py) | [DECISIONS.md](DECISIONS.md) §Decision 10 |
| ~~N2~~ | ~~**Agent chat path / agent tool-calling loop**~~ ✅ resolved 2026-05-29 (Feature 010 T058–T060) | Real `groq.AsyncGroq` tool-calling loop in [app/agent/agent.py](app/agent/agent.py) with `MAX_AGENT_ITERATIONS = 5`, `MAX_AGENT_TOKENS_PER_TURN = 4000` caps; deterministic fallback when no Groq client is constructable. Smoke probes that depend on the agent path stay xfail until **N1** (RAG indexing) lands so the agent has content to retrieve. | [app/agent/agent.py](app/agent/agent.py) | [DECISIONS.md](DECISIONS.md) §Decision 19b |
| ~~N3~~ | ~~**`capture_lead` tool + `leads` table writes**~~ ✅ resolved 2026-05-29 (Feature 010 T050–T052) | Pydantic-validated `capture_lead` tool with per-session rate limit (`tenant_settings.rate_limit_lead_per_session`); writes scoped to caller's `tenant_id` (trusted context). Smoke probe at line 667 stays xfail under the same N1 gating until cross-tenant content can also flow. | [app/agent/tools.py](app/agent/tools.py) | — |
| ~~N4~~ | ~~**`escalate` tool returning `ticket_id`**~~ ✅ resolved 2026-05-29 (Feature 010 T053) | `escalate` wired to `EscalationRepository.create()` — first call per session INSERTs a real `escalation_tickets` row and emits `escalation.created`; subsequent same-session calls return the existing `ticket_id` without re-INSERT. | [app/agent/tools.py](app/agent/tools.py), [app/repositories/escalation_repo.py](app/repositories/escalation_repo.py) | — |
| N5 | **Real `evals/rag.py` evaluator** | Mock evaluator emits passing JSON with `"_mock": true` and a `MOCK EVALUATOR: rag …` stderr banner. Replaced by a single file swap; no `ci.yml` or threshold-checker change needed. | [evals/rag.py](evals/rag.py) | [DECISIONS.md](DECISIONS.md) §Decision 9 |
| ~~N6~~ | ~~**Real `evals/agent_tool.py` evaluator**~~ ✅ resolved 2026-05-29 (Feature 010 T091) | [evals/agent_tool.py](evals/agent_tool.py) graduated from mock — loops `evals/agent_tool_selection_cases.json` through the real agent path (T058–T090) and reports `accuracy`. `_mock: true` flag and stderr banner removed. | [evals/agent_tool.py](evals/agent_tool.py), [specs/010-fe-be-integration/tasks.md](specs/010-fe-be-integration/tasks.md) T091 | — |
| N7 | **Emit `metrics.mrr` from `evals/rag.py`** | Needed to close the RAG MRR gate gap (constitution `## Quality Gates` lists RAG MRR ≥ 0.50 but `eval_thresholds.yaml` has no `rag.mrr_min` key yet). Two-PR move with Ayoub adding the threshold key (see A4). | [evals/rag.py](evals/rag.py), [eval_thresholds.yaml](eval_thresholds.yaml) | [DECISIONS.md](DECISIONS.md) §Decision 9 known gap |
| ~~N8~~ | ~~**Live `/leads` list endpoint**~~ ✅ resolved 2026-05-28 | `GET /leads` in [app/api/routes/leads.py](app/api/routes/leads.py): admin-JWT auth, lists leads for the caller's tenant only (via `LeadRepository.list_by_tenant`). | [app/api/routes/leads.py](app/api/routes/leads.py), [tests/integration/test_admin_read_endpoints.py](tests/integration/test_admin_read_endpoints.py) | — |
| ~~N9~~ | ~~**Live admin tenant CMS list endpoint**~~ ✅ resolved 2026-05-28 | `GET /cms/pages` rewritten in [app/api/routes/cms.py](app/api/routes/cms.py): admin-JWT auth, returns the caller's tenant pages with the schema admin/cms_page.py expects (`title, slug, body, source_url, status, updated_at`). | [app/api/routes/cms.py](app/api/routes/cms.py) | — |

**Contract for Nasser**: when any of N1–N4 lands and unblocks a smoke probe, the same PR MUST flip `SMOKE_E2E_REQUIRE_FULL_STACK` to `"1"` in [.github/workflows/ci.yml](.github/workflows/ci.yml). For N5–N7, swap the mock file and verify the new evaluator emits the JSON shape required by [specs/006-ci-eval-gates/contracts/eval-cli.md](specs/006-ci-eval-gates/contracts/eval-cli.md).

---

### 1.3 Blocked on Ayoub (Phase 3 — classifier / modelserver; Phase 6 — guardrails / redaction)

| # | Blocked artifact | Current affordance | Files | Reference |
|---|------------------|--------------------|-------|-----------|
| ~~A1~~ | ~~**Real `evals/classifier.py` evaluator**~~ ✅ resolved 2026-05-28 | Real evaluator in [evals/classifier.py](evals/classifier.py) loads the chosen ONNX classifier (`RouterClassifier`), replays the same `random_state=42` stratified split the training notebook used, and reports macro_f1 + accuracy + per-class F1. Measured **macro_f1 = 0.9752** (vs 0.80 floor) on the committed dataset. `dataset_hash` from the model card is echoed in the JSON for provenance. | [evals/classifier.py](evals/classifier.py), [modelserver/classifier.py](modelserver/classifier.py), [modelserver/artifacts/](modelserver/artifacts/) | — |
| ~~A2~~ | ~~**Real `evals/red_team.py` evaluator**~~ ✅ resolved 2026-05-28 | [evals/red_team.py](evals/red_team.py) iterates `evals/red_team/red_team_cases.json` and calls `guardrails.main.evaluate_platform_rails` directly (no HTTP, no service-auth dependency in CI). Measured **refusal_rate = 1.0** (6/6 expected-block cases blocked). | [evals/red_team.py](evals/red_team.py) | — |
| ~~A3~~ | ~~**Real `evals/redaction.py` evaluator**~~ ✅ resolved 2026-05-28 | [evals/redaction.py](evals/redaction.py) iterates `evals/redaction/redaction_cases.json` and runs `app.infra.redaction.redact_text` on each; counts leaks (any `must_not_contain` string still present in the redacted output). Measured **secret_leak_count = 0** of 5 cases. | [evals/redaction.py](evals/redaction.py) | — |
| ~~A4~~ | ~~**Add `rag.mrr_min: 0.50` to `eval_thresholds.yaml`**~~ ✅ resolved 2026-05-28 | Added to [eval_thresholds.yaml](eval_thresholds.yaml). The MRR gate now exists in the thresholds file; it'll start blocking CI as soon as N7 (Nasser emitting `metrics.mrr`) lands. | [eval_thresholds.yaml](eval_thresholds.yaml) | — |
| A5 | **guardrails real readiness endpoint** | Current healthcheck probes `/openapi.json` (proves the route stack is wired, fine for cold-start gating). Smoke probe still wrapped in strict-xfail with reason `phase-6` for the guardrails-mediated paths. | [guardrails/main.py](guardrails/main.py), [tests/smoke/test_cross_tenant_e2e.py](tests/smoke/test_cross_tenant_e2e.py) | [DECISIONS.md](DECISIONS.md) §Decision 10 |

**Contract for Ayoub**: A1–A3 are single file swaps; the threshold-checker contract at [specs/006-ci-eval-gates/contracts/threshold-checker.md](specs/006-ci-eval-gates/contracts/threshold-checker.md) does not change. A4 lands in a PR by itself or alongside N7. A5 lands together with whatever new guardrails behavior the smoke probe relies on.

---

## 2. Cross-team / shared blockers

| # | Blocked artifact | Why it's shared | Reference |
|---|------------------|------------------|-----------|
| X1 | **Smoke-E2E full-stack gate enabled in CI** | [.github/workflows/ci.yml](.github/workflows/ci.yml) currently sets `SMOKE_E2E_REQUIRE_FULL_STACK: "0"`. Feature 010 T095 evaluated the flip: H7/H8/H9/N2/N3/N4 are resolved, but the **content isolation probes (P1/P2) still require N1 (CMS → `rag_chunks` indexing)** so the answer carries the tenant's keyword. Flag flip is deferred to the PR that lands N1. The strict-xfail mechanism still forces the flip once N1 lands (XPASS(strict) breaks CI until then). | [DECISIONS.md](DECISIONS.md) §Decision 10 phase-gate flag |
| X2 | **RAG MRR gate end-to-end** | Requires both A4 (add threshold key) **and** N7 (emit `metrics.mrr` from the evaluator). Either alone is a no-op. | [DECISIONS.md](DECISIONS.md) §Decision 9 known gap |

---

## 3. Not blocked, but not completed (this branch)

Items below were in scope or adjacent to scope and **could be done now** — no teammate dependency. They are listed here so a future Amer (or a teammate picking up the demo polish) does not lose track.

| # | Task | Status | Why deferred | Where to pick up |
|---|------|--------|--------------|------------------|
| U1 | **[T009](specs/008-demo-polish/tasks.md) — clean-clone runbook walk** (clone to a fresh dir, follow [RUNBOOK.md](RUNBOOK.md) steps 1–9, run `pytest tests/smoke/`, time it for SC-002) | Skipped by request during implementation. | Local timing pass; the cold-start audit (T015) already proves the stack is healthy, but the wall-clock-to-smoke-pass measurement for SC-002 was not recorded. | Spend 15–30 min before merge in a fresh `git clone` of `008-demo-polish`, follow the runbook top to bottom, record the elapsed minutes in the PR description. |
| U2 | **`make` portability for Windows contributors without `make` on PATH** | Discovered during T011 verification — the Makefile target works in CI (`ubuntu-latest`), but a Windows contributor without `make` (e.g., the one I ran the verifications on) has to invoke `bash scripts/check_lean_images.sh` directly. | This is a docs-only nit, not a blocker for the demo or CI. | Add one line under "Run smoke test" in [RUNBOOK.md](RUNBOOK.md), or under [README.md](README.md)'s "Embed the widget" section's neighborhood, noting that contributors without `make` can run `bash scripts/check_lean_images.sh` directly. |
| U3 | **Branch protection: require `lean-image-audit` as a required check** | Out of repo scope — this is GitHub repo-admin configuration, not a file change. The [contract](specs/008-demo-polish/contracts/lean-image-audit-cli.md) §7 explicitly defers this. | Repo-admin setting, not a code change. | Open the GitHub repo settings → Branches → main → Require status checks; add `lean-image-audit` to the list alongside the existing required checks. |

---

## Index — files that contain pending-handoff markers

A single `grep` across the repo surfaces every blocked-on-teammate seam:

```bash
grep -rn "TODO(hiba-handoff)\|TODO(nasser-handoff)\|TODO(ayoub-handoff)\|TEMPORARY MOCK\|_StubAuditLogger\|InMemoryWidgetRepository\|@require_full_stack" \
  app/ admin/ evals/ tests/ scripts/ .github/
```

When a handoff lands, its TODO line / mock file / strict-xfail decorator disappears in the same PR. If a grep result outlives the PR that was supposed to remove it, the corresponding row in this file is wrong — fix it.
