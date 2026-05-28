# Phase 0 Research: Tenant Admin Widget Configuration

**Feature**: 004-widget-admin-config
**Date**: 2026-05-27
**Status**: Complete — no `NEEDS CLARIFICATION` markers remain in [spec.md](./spec.md).

This document records the design decisions whose alternatives were considered and rejected during planning. The 3 spec-level ambiguities were already resolved in the `/speckit-clarify` session on 2026-05-27 (see `## Clarifications` in [spec.md](./spec.md)). This file captures the remaining planning-level decisions.

---

## R1. How is the `tenant_admin` role dependency mocked until Hiba's lands?

**Decision**: Add a single function `require_tenant_admin()` in [app/api/deps.py](../../app/api/deps.py) that:
1. Reads `X-Concierge-Role` and `X-Concierge-Tenant-Id` request headers.
2. Returns a `TenantAdminContext` dataclass with fields `tenant_id: UUID` and `actor_id: str | None` (room for "who" the admin is).
3. Raises `HTTPException(403, ...)` if the role header is missing or not `"tenant_admin"`.
4. Raises `HTTPException(500, "role-dep mock disabled in non-dev environments")` if `settings.environment != "dev"` so that this mock cannot accidentally ship to staging or production.

The route uses it as `Depends(require_tenant_admin)`. When Hiba's real dep lands, the import in the route's `Depends(...)` swaps and the rest of the code is unchanged — the returned `TenantAdminContext` shape is contractually identical.

**Rationale**:
- Mocking via FastAPI `Depends(...)` keeps the swap to a one-line change. Mocking via the test client's auth override (e.g. `app.dependency_overrides`) would work for tests but not for live exploratory `curl`s during development.
- Hard-failing in non-dev environments protects against accidental promotion of a header-driven authentication scheme.
- Using headers rather than query parameters keeps the values out of access-log query strings.

**Alternatives considered**:
- *Read `tenant_id` from the request body.* **Rejected** — Constitution Principle I forbids tenant_id from request bodies, even in mocks. Headers are no better than bodies for security but the convention is to treat headers as "ambient" trust, which lets reviewers see "yep, server context" at the route level.
- *Use a pytest-only fixture and have the route be auth-free until Hiba's dep lands.* **Rejected** — Streamlit integration tests and exploratory `curl` use need to exercise the gate too. A no-op gate hides bugs.

---

## R2. How does `add_audit_log` fit into the PUT transaction (FR-013 fail-closed)?

**Decision**: Both the `widget_configs` UPDATE and any `audit_logs` INSERTs are performed inside a single async SQLAlchemy session transaction (`async with session.begin():`). The audit log call uses Hiba's `TenantRepository.add_audit_log(...)` documented in CONTRACT.md §line 190; the implementation is assumed to accept either the current session or to participate in the unit of work transparently (the standard SQLAlchemy 2 pattern is for repositories to share a session passed via dependency injection).

If `add_audit_log` raises, the transaction rolls back and the widget update is discarded. The route catches `HTTPException` and re-raises; any other exception becomes a 500 (via the existing exception middleware), with the row unchanged.

For the contract test, the audit log function is mocked via a fake `AuditLogger` Protocol implementation injected into `WidgetConfigService` (see plan.md / tasks.md T004 for the Protocol definition). The assertion is "called exactly once per net add/remove". For the integration test, the same fake `AuditLogger` is registered via FastAPI's `app.dependency_overrides`. We don't depend on Hiba's real `TenantRepository.add_audit_log` implementation in any test because it's another owner's territory; the `AuditLogger` Protocol formalizes the contract surface.

**Rationale**:
- A single transaction is the cleanest way to satisfy FR-013's "fail-closed" requirement. Alternative compensation patterns (write audit first, then write config, then "undo" audit on failure) add complexity and create races. The standard "atomic transaction" pattern is well-understood and matches SQLAlchemy idioms.
- Asserting the audit call shape at the service-call site (not inside the database) keeps the test focused on this feature's contract and decouples it from Hiba's implementation.
- The InMemoryWidgetRepository simulates the transactional behavior via a try/except around the update + audit calls; it doesn't have real transactions but the observable behavior matches.

**Alternatives considered**:
- *Write the audit log entry first, then the widget config update.* **Rejected** — if the widget update fails, the audit log records a change that never happened. Auditors trust the audit log; orphan entries are worse than no entry.
- *Two-phase commit using outbox pattern.* **Rejected** — overbuilt for a single tenant-admin write path. No multi-service consistency need exists here.

---

## R3. Origin normalization — what gets stored, what gets compared?

**Decision**: Each origin string entered by the admin is normalized at save time to `scheme://host[:port]` form, with:
- Scheme lowercased (`HTTPS` → `https`).
- Host lowercased and IDN-encoded as ASCII via `idna.encode` if Python's `idna` package is available (it is, transitively via httpx). Falls back to literal host bytes for ASCII-only hosts.
- Default ports (`:80` for http, `:443` for https) stripped — relies on the existing `_DEFAULT_PORTS` constant in [app/services/widget_service.py:35](../../app/services/widget_service.py#L35) for symmetry with the token endpoint's origin canonicalization.
- Path, query, fragment, userinfo all stripped. If any of these are non-empty on input, the input is logged as "stripped" but the save succeeds with the normalized form.
- Trailing slash stripped (handled by stripping the path component to "").

Origin **comparison** (for diff between previous and new lists, for de-duplication, and for downstream allowlist matching in the token endpoint) is done on the normalized form only. The diff uses set semantics on normalized strings.

**Rationale**:
- Matches the token endpoint's existing canonicalization (`_DEFAULT_PORTS` + `urlsplit` in `widget_service.py`). The two code paths MUST agree or the allowlist becomes a footgun.
- IDN support handles the homograph edge case the spec deliberately deferred (per /clarify session — flagged as low-impact). Adding it now is a 3-line cost via Python's standard library.
- Stripping path and userinfo silently is friendlier than rejecting; the admin's intent is clear and the loaded value matches what the browser will send.

**Alternatives considered**:
- *Reject anything other than `scheme://host[:port]` exact form.* **Rejected** — surfaces a frustrating per-character validation experience. Tenants paste from address bars.
- *Store input as-is, normalize only at compare time.* **Rejected** — leads to subtle bugs where the stored list contains semantically-duplicate entries and the audit log records "added X" twice. Normalization at save time is one place for the rule.

---

## R4. Streamlit page state model

**Decision**: [admin/widget_page.py](../../admin/widget_page.py) holds **draft state** in Streamlit's `st.session_state` keyed by the canonical config row id. On first render, the page calls `GET /widgets/config` and seeds the draft. The user's edits mutate the draft only. The Save button issues a `PUT /widgets/config` with the full draft and replaces the draft with the server's response on success.

Per-field validation (URL format, JSON parse, greeting length) runs on every render against the **draft**. The Save button is disabled when any field has a validation error.

The theme preview pane is an `<iframe>` with `srcdoc` containing a minimal HTML page that mounts the widget runtime against the current draft theme — or, if a live preview is infeasible in the Streamlit environment (no Vite dev server, mixed-origin issues), shows a `placeholder` graphic stating "Preview unavailable in admin (theme applies on next visitor mount)". Live preview is **a stretch goal**, not a US3 acceptance requirement.

**Rationale**:
- Streamlit re-runs the whole script on every interaction. `st.session_state` is the only sane place to keep draft state across reruns.
- Validating against the draft means errors surface as the user types, not only on Save (FR-017).
- The single PUT (rather than per-field PUTs) matches the user input requirement "Save button submits a **single** PUT".

**Alternatives considered**:
- *Per-field auto-save on blur.* **Rejected** — produces audit-log churn (every origin keystroke leaves the field with a different "added" event). Single Save batches the diff.
- *Optimistic concurrency via row version.* **Rejected** — overbuilt for current scale (single-digit admins per tenant). The spec accepts last-write-wins.

---

## R5. Test surface and mocking strategy

**Decision**: Three test layers:

1. **Unit (`tests/unit/test_widget_config_service.py`)** — tests `WidgetConfigService.update_widget_config` with the audit-log function mocked. Covers diff logic, normalization, validation, audit-call counting, fail-closed rollback.
2. **Security/contract (`tests/security/test_widget_admin_config.py`)** — tests the HTTP layer with `httpx.AsyncClient` against the FastAPI app, with `app.dependency_overrides` swapping `require_tenant_admin` to controlled mocks. Covers happy-path GET/PUT, 403 for non-admin, 403 for cross-tenant access (tenant A's admin tries to read tenant B's config), 422 for invalid URL, 422 for empty-list-while-enabled.
3. **Integration (`tests/integration/test_admin_widget_page.py`)** — uses `streamlit.testing.v1.AppTest` to render the admin page, simulate add/remove/save, and assert state transitions. The backend is replaced by a fake `httpx` client that returns canned `GET` and accepts the `PUT`, so this test does not depend on a running FastAPI server.

**Rationale**:
- Three layers map to the spec's three test concerns from the user input: service behavior, HTTP contract + auth, frontend behavior.
- Streamlit's testing harness (`streamlit.testing.v1.AppTest`) is the idiomatic way to test Streamlit apps without spinning up a browser; it's available in Streamlit ≥ 1.28 (project pins ≥ 1.32).
- Mocking the audit log function at the service-call site (not at the database) keeps the tests focused on this feature's contract and decoupled from Hiba's eventual implementation.

**Alternatives considered**:
- *Playwright against a running Streamlit + FastAPI stack.* **Rejected** — adds a tool dependency and slows CI; the AppTest harness is sufficient for the round-trip assertions in the spec.
- *Single test layer (HTTP only).* **Rejected** — the service layer's diff and normalization logic is complex enough to deserve unit coverage independent of HTTP wiring.
