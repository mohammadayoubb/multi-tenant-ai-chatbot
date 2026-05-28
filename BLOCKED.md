# Owner: Amer
# BLOCKED.md

Single source of truth for work that is **not done** in this repo and **why**. Each entry names the blocked artifact, the swap-replaceable affordance currently in its place (if any), the file(s) where the handoff lands, and the authoritative reference (a `DECISIONS.md` entry or spec section).

This file is committed (it is **not** gitignored). Update it whenever:

- a teammate's slice lands and a blocked item becomes unblocked → strike the entry and move to a "Resolved" log if you want to keep history.
- a new blocking dependency is discovered → add a new entry under the right owner.
- a task in the active spec was not completed and was not blocked → add it under §3.

Last updated: 2026-05-28 (end of feature [008-demo-polish](specs/008-demo-polish/spec.md)).

---

## 1. Blocked on teammate code

### 1.1 Blocked on Hiba (Phase 1 — platform, tenancy, RLS, audit; Phase 9 — erasure)

| # | Blocked artifact | Current affordance | Files | Reference |
|---|------------------|--------------------|-------|-----------|
| H1 | **Authenticated `tenant_admin` role dependency** | Mock `require_tenant_admin` reads `X-Concierge-Role` / `X-Concierge-Tenant-Id` dev headers and refuses outside `CONCIERGE_ENV=dev`. Swap-replaceable by Hiba's real dep with a single import change. | [app/api/deps.py](app/api/deps.py) (TODO marker line 37) | [DECISIONS.md](DECISIONS.md) §Decision 7 |
| H2 | **`widget_configs` migration adding `theme_json JSONB` and `greeting TEXT` columns** | `WidgetConfigDomain` carries the fields with `None` defaults; the SQL adapter raises `NotImplementedError`; `InMemoryWidgetRepository` serves dev. | [app/repositories/widget_repo.py](app/repositories/widget_repo.py) | [DECISIONS.md](DECISIONS.md) §Decision 7 |
| H3 | **`TenantRepository.add_audit_log` implementation** | `AuditLogger` Protocol with a `_StubAuditLogger` no-op; tests inject fakes via `app.dependency_overrides`. Audit-write failures already return 500 per fail-closed contract clause E2. | [app/services/widget_service.py](app/services/widget_service.py), [app/api/routes/widgets.py](app/api/routes/widgets.py) line 68 (TODO marker) | [DECISIONS.md](DECISIONS.md) §Decision 7 |
| H4 | **Real admin session** | Streamlit admin pages send `X-Concierge-Role` / `X-Concierge-Tenant-Id` / `X-Concierge-Actor-Id` dev headers via centralised helper. Single edit to drop dev headers when Hiba's session lands. | [admin/_admin_http.py](admin/_admin_http.py) line 20 (TODO marker), [admin/widget_page.py](admin/widget_page.py) line 21 (TODO marker) | [DECISIONS.md](DECISIONS.md) §Decision 8 |
| H5 | **Live tenant audit-log read endpoint** | `admin/tenant_page.py` falls back to canned-sample render with `(placeholder)` caption on any non-2xx or missing-field response. | [admin/tenant_page.py](admin/tenant_page.py) | [DECISIONS.md](DECISIONS.md) §Decision 8 |
| H6 | **Live tenant usage rollup endpoint** | `admin/usage_page.py` falls back to placeholder. | [admin/usage_page.py](admin/usage_page.py) | [DECISIONS.md](DECISIONS.md) §Decision 8 |
| H7 | **`POST /tenants` + `tenants` table** | Smoke probes that need to create a tenant are wrapped in `@require_full_stack("phase-1+2+5: ...")` → strict-xfail while `SMOKE_E2E_REQUIRE_FULL_STACK=0`. | [tests/smoke/test_cross_tenant_e2e.py](tests/smoke/test_cross_tenant_e2e.py) line 250, 514, 554 | [DECISIONS.md](DECISIONS.md) §Decision 10 |
| H8 | **`audit_logs` table + escalate-side audit row** | Smoke probe wrapped in strict-xfail with reason `phase-1: audit_logs table + escalate-side audit entry`. | [tests/smoke/test_cross_tenant_e2e.py](tests/smoke/test_cross_tenant_e2e.py) line 747 | [DECISIONS.md](DECISIONS.md) §Decision 10 |
| H9 | **RLS / repository tenant-filter on `leads`** | Smoke probe wrapped in strict-xfail with reason `phase-1: RLS / repository tenant filter on leads`. | [tests/smoke/test_cross_tenant_e2e.py](tests/smoke/test_cross_tenant_e2e.py) line 695 | [DECISIONS.md](DECISIONS.md) §Decision 10 |

**Contract for Hiba**: when any of H1–H9 lands, the same PR MUST replace the affordance (delete the TODO comment / drop the stub / drop the in-memory adapter) and, if the change unblocks a smoke probe, flip `SMOKE_E2E_REQUIRE_FULL_STACK` to `"1"` in [.github/workflows/ci.yml](.github/workflows/ci.yml) line 262. The strict-xfail mechanism will fail CI on XPASS until the flag is flipped.

---

### 1.2 Blocked on Nasser (Phase 2 — CMS / RAG; Phase 4 — router; Phase 5 — agent / tools)

| # | Blocked artifact | Current affordance | Files | Reference |
|---|------------------|--------------------|-------|-----------|
| N1 | **`POST /cms/pages` + `cms_pages` table + RAG indexing** | Smoke probes wrapped in strict-xfail with reason `phase-2`. | [tests/smoke/test_cross_tenant_e2e.py](tests/smoke/test_cross_tenant_e2e.py) line 310, 514, 554 | [DECISIONS.md](DECISIONS.md) §Decision 10 |
| N2 | **Agent chat path / agent tool-calling loop** | Smoke probes wrapped in strict-xfail with reason `phase-5`. The classifier-router + agent are Phases 4/5. | [tests/smoke/test_cross_tenant_e2e.py](tests/smoke/test_cross_tenant_e2e.py) line 514, 554, 724 | [DECISIONS.md](DECISIONS.md) §Decision 10 |
| N3 | **`capture_lead` tool + `leads` table writes** | Smoke probe wrapped in strict-xfail with reason `phase-5+1: capture_lead tool + leads table writes`. | [tests/smoke/test_cross_tenant_e2e.py](tests/smoke/test_cross_tenant_e2e.py) line 667 | [DECISIONS.md](DECISIONS.md) §Decision 10 |
| N4 | **`escalate` tool returning `ticket_id`** | Smoke probe wrapped in strict-xfail with reason `phase-5: escalate tool returns ticket_id`. | [tests/smoke/test_cross_tenant_e2e.py](tests/smoke/test_cross_tenant_e2e.py) line 724 | [DECISIONS.md](DECISIONS.md) §Decision 10 |
| N5 | **Real `evals/rag.py` evaluator** | Mock evaluator emits passing JSON with `"_mock": true` and a `MOCK EVALUATOR: rag …` stderr banner. Replaced by a single file swap; no `ci.yml` or threshold-checker change needed. | [evals/rag.py](evals/rag.py) | [DECISIONS.md](DECISIONS.md) §Decision 9 |
| N6 | **Real `evals/agent_tool.py` evaluator** | Mock emits passing JSON; same swap contract as N5. | [evals/agent_tool.py](evals/agent_tool.py) | [DECISIONS.md](DECISIONS.md) §Decision 9 |
| N7 | **Emit `metrics.mrr` from `evals/rag.py`** | Needed to close the RAG MRR gate gap (constitution `## Quality Gates` lists RAG MRR ≥ 0.50 but `eval_thresholds.yaml` has no `rag.mrr_min` key yet). Two-PR move with Ayoub adding the threshold key (see A4). | [evals/rag.py](evals/rag.py), [eval_thresholds.yaml](eval_thresholds.yaml) | [DECISIONS.md](DECISIONS.md) §Decision 9 known gap |
| N8 | **Live `/leads` list endpoint** | `admin/leads_page.py` falls back to placeholder. | [admin/leads_page.py](admin/leads_page.py) | [DECISIONS.md](DECISIONS.md) §Decision 8 |
| N9 | **Live admin tenant CMS list endpoint** | `admin/cms_page.py` falls back to placeholder. | [admin/cms_page.py](admin/cms_page.py) | [DECISIONS.md](DECISIONS.md) §Decision 8 |

**Contract for Nasser**: when any of N1–N4 lands and unblocks a smoke probe, the same PR MUST flip `SMOKE_E2E_REQUIRE_FULL_STACK` to `"1"` in [.github/workflows/ci.yml](.github/workflows/ci.yml). For N5–N7, swap the mock file and verify the new evaluator emits the JSON shape required by [specs/006-ci-eval-gates/contracts/eval-cli.md](specs/006-ci-eval-gates/contracts/eval-cli.md).

---

### 1.3 Blocked on Ayoub (Phase 3 — classifier / modelserver; Phase 6 — guardrails / redaction)

| # | Blocked artifact | Current affordance | Files | Reference |
|---|------------------|--------------------|-------|-----------|
| A1 | **Real `evals/classifier.py` evaluator** | Mock emits passing JSON with `_mock: true` + stderr banner. | [evals/classifier.py](evals/classifier.py) | [DECISIONS.md](DECISIONS.md) §Decision 9 |
| A2 | **Real `evals/red_team.py` evaluator** | Mock emits passing JSON. | [evals/red_team.py](evals/red_team.py) | [DECISIONS.md](DECISIONS.md) §Decision 9 |
| A3 | **Real `evals/redaction.py` evaluator** | Mock emits passing JSON. | [evals/redaction.py](evals/redaction.py) | [DECISIONS.md](DECISIONS.md) §Decision 9 |
| A4 | **Add `rag.mrr_min: 0.50` to `eval_thresholds.yaml`** | The MRR gate is in the constitution but missing from the thresholds file. Pairs with N7 (Nasser emitting MRR). | [eval_thresholds.yaml](eval_thresholds.yaml) | [DECISIONS.md](DECISIONS.md) §Decision 9 known gap |
| A5 | **guardrails real readiness endpoint** | Current healthcheck probes `/openapi.json` (proves the route stack is wired, fine for cold-start gating). Smoke probe still wrapped in strict-xfail with reason `phase-6` for the guardrails-mediated paths. | [guardrails/main.py](guardrails/main.py), [tests/smoke/test_cross_tenant_e2e.py](tests/smoke/test_cross_tenant_e2e.py) | [DECISIONS.md](DECISIONS.md) §Decision 10 |

**Contract for Ayoub**: A1–A3 are single file swaps; the threshold-checker contract at [specs/006-ci-eval-gates/contracts/threshold-checker.md](specs/006-ci-eval-gates/contracts/threshold-checker.md) does not change. A4 lands in a PR by itself or alongside N7. A5 lands together with whatever new guardrails behavior the smoke probe relies on.

---

## 2. Cross-team / shared blockers

| # | Blocked artifact | Why it's shared | Reference |
|---|------------------|------------------|-----------|
| X1 | **Smoke-E2E full-stack gate enabled in CI** | [.github/workflows/ci.yml](.github/workflows/ci.yml) line 262 currently sets `SMOKE_E2E_REQUIRE_FULL_STACK: "0"` so probes that depend on H7/H8/H9/N1/N2/N3/N4/A5 strict-xfail rather than fail. The flag flips to `"1"` automatically by the strict-xfail mechanism: the moment **all** upstream slices land, the next PR's CI is forced to flip the flag (XPASS(strict) fails the build until then). | [DECISIONS.md](DECISIONS.md) §Decision 10 phase-gate flag |
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
