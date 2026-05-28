# Test-Side Data Model: Cross-Tenant Smoke E2E

**Scope**: Entities used by `tests/smoke/test_cross_tenant_e2e.py`. None of these are persisted
to PostgreSQL; they exist only inside the pytest process for the duration of one smoke run.

The smoke suite **observes** real persisted entities (Tenant, WidgetConfig, CmsPage, Lead,
EscalationTicket, AuditLog) through their HTTP routes and one read-only DB query, but it does
not define those entities — they are owned by their respective slices (see
[CONTRACT.md](../../CONTRACT.md) §2.6–2.9).

---

## E1 — `SmokeTenantFixture`

A per-tenant bundle the suite assembles during setup and threads through every probe.

| Field           | Type        | Source                                | Notes                                       |
|-----------------|-------------|---------------------------------------|---------------------------------------------|
| `tenant_id`     | `UUID`      | `POST /tenants` response              | Trusted server-issued                       |
| `widget_id`     | `UUID`      | `PUT /widgets/config` response        | Tenant-scoped                               |
| `origin`        | `str`       | Test constant                          | e.g., `https://alpha.example.test`          |
| `allowed_origin`| `str`       | Same as `origin` after registration   | Echo for clarity                            |
| `session_id`    | `str`       | `POST /widgets/token` response        | Per-token                                   |
| `token`         | `str (JWT)` | `POST /widgets/token` response        | HS256, short-lived (`exp ≤ 15 min`)         |
| `seed_keyword`  | `str`       | Test constant                          | `"alpha-cookies"` (A) or `"bravo-pastries"` (B) |
| `cms_page_ids`  | `list[UUID]`| `POST /cms/pages` responses           | Two per tenant                              |

**Invariants:**
- `seed_keyword` for Tenant A is `"alpha-cookies"`; for Tenant B is `"bravo-pastries"`. These
  strings appear nowhere else in the suite or the test data — any cross-tenant leak surfaces
  as a substring match.
- `origin` is unique per tenant. Tenant A's origin is registered only under Tenant A; the
  forged probe (R1) reuses Tenant B's origin in Tenant A's JWT.
- `token` is held in memory only for the test process; never written to disk or env (mirrors
  the production constraint in CONTRACT.md §2.9).

---

## E2 — `ProbeOutcome`

One per scenario in the suite. Aggregates into the `SmokeRunReport`.

| Field         | Type     | Notes                                                            |
|---------------|----------|------------------------------------------------------------------|
| `probe_id`    | `str`    | Stable identifier, e.g., `"P1-cross-tenant-content-A"`            |
| `scenario`    | `str`    | Human description matching the acceptance scenario in spec.md     |
| `tenant`      | `str`    | `"A"`, `"B"`, or `"forged"`                                       |
| `expected`    | `str`    | What the suite expected to observe                                |
| `observed`    | `str`    | What it actually observed (HTTP status, substring match, or row)  |
| `passed`      | `bool`   | Final verdict                                                     |
| `latency_ms`  | `int`    | Wall time for the probe's outermost HTTP call                     |
| `notes`       | `str`    | Free text for failure context; empty on pass                      |

**Probe ID list (locked):**

| Probe ID                       | Maps to spec FR / Scenario                |
|--------------------------------|-------------------------------------------|
| `P1-cross-tenant-content-A`    | FR-004, US1 scenario 1                    |
| `P1-cross-tenant-content-B`    | FR-004, US1 scenario 2                    |
| `P2-forged-origin-403`         | FR-005, US1 scenario 3                    |
| `P3-lead-capture-tenant-A`     | FR-006, US2 scenario 1                    |
| `P3-lead-not-visible-tenant-B` | FR-006 (negative readback)                |
| `P4-escalate-tenant-A`         | FR-007, US2 scenario 2                    |
| `P4-audit-log-entry`           | FR-007 (audit-log readback)               |

---

## E3 — `SmokeRunReport`

Aggregate result, produced at the end of the suite and written as `smoke-report.json` in the
runner workspace (uploaded as a CI artifact on failure only — see R7).

| Field            | Type                  | Notes                                                  |
|------------------|-----------------------|--------------------------------------------------------|
| `run_id`         | `str`                 | ISO 8601 timestamp + git short SHA                      |
| `started_at`     | `datetime`            | UTC                                                     |
| `finished_at`    | `datetime`            | UTC                                                     |
| `stack_up_ms`    | `int`                 | Time spent waiting for healthchecks                     |
| `probes`         | `list[ProbeOutcome]`  | Ordered                                                 |
| `passed`         | `bool`                | `all(p.passed for p in probes)`                         |
| `dependency_phase_xfails` | `list[str]`  | Probe IDs currently xfailed under R6's flag             |

**Rules:**
- The report is never written to a tenant-owned table; it is artifact-only.
- Tokens, secrets, and full chat response bodies are **redacted** before serialization. Only
  the first 200 chars of any chat response and the first 8 chars of any token are written
  (mirrors Principle V's redaction rule for observability artifacts).

---

## Observed entities (not defined here, only referenced)

| Entity                | Owner       | Defined in                           |
|-----------------------|-------------|--------------------------------------|
| `Tenant`              | Hiba        | CONTRACT.md §2.6, Phase-1 spec       |
| `WidgetConfig`        | Amer        | CONTRACT.md §2.9, [specs/004-widget-admin-config/](../004-widget-admin-config/) |
| `CmsPage`             | Nasser      | CONTRACT.md §2.7, Phase-2 spec        |
| `RagChunk`            | Nasser      | CONTRACT.md §2.7                      |
| `Lead`                | Nasser      | CONTRACT.md §2.7 (`capture_lead`)     |
| `EscalationTicket`    | Nasser      | CONTRACT.md §2.7 (`escalate`)         |
| `AuditLog`            | Hiba        | CONTRACT.md §2.6                      |

The smoke suite asserts properties of these entities (existence, `tenant_id` scope, audit
trail) but does not modify them outside the public HTTP routes.
