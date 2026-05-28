# Contract: Audit Log Consumption

**Feature**: 004-widget-admin-config
**Owner**: Amer (consumer); function owner is Hiba ([CONTRACT.md:190](../../../CONTRACT.md#L190))

This document specifies how this feature uses the platform audit log function and what calls it MUST make. It is read by both Amer (implementer) and Hiba (function owner, audit-section reviewer).

---

## A1. Function being consumed

Per [CONTRACT.md:190-197](../../../CONTRACT.md#L190-L197):

```python
TenantRepository.add_audit_log(
    tenant_id: UUID,
    actor_role: str,
    action: str,
    actor_id: str | None = None,
    metadata: dict | None = None,
) -> AuditLog
```

**Assumed contract** (to be confirmed with Hiba at implementation time):
- Async function (consistent with the rest of `TenantRepository`).
- Participates in the calling session's transaction (uses `INSERT INTO audit_logs ...` via the session passed in, not a separate connection).
- Raises on failure; does not swallow exceptions.

If any of these assumptions don't hold, the integration plan changes — flagged for verification in the implementation PR.

---

## A2. When this feature MUST call `add_audit_log`

For each `PUT /widgets/config` request that successfully passes validation:

1. Compute `previous_origins` = the set of origins currently persisted for the caller's tenant (after normalization).
2. Compute `new_origins` = the set of origins in the request body (after normalization).
3. For each origin in `new_origins − previous_origins` (sorted for deterministic order in tests):
   - Call `add_audit_log(tenant_id=..., actor_role="tenant_admin", action="widget.origin_added", actor_id=..., metadata={"origin": <origin>, "widget_id": <widget_id>})`.
4. For each origin in `previous_origins − new_origins` (sorted):
   - Call `add_audit_log(tenant_id=..., actor_role="tenant_admin", action="widget.origin_removed", actor_id=..., metadata={"origin": <origin>, "widget_id": <widget_id>})`.

**No-op saves** (`new_origins == previous_origins`) produce zero calls.

**Other field changes** (`enabled`, `greeting`, `theme_json`) are NOT audited by this feature. If Hiba's policy later requires auditing them, that's a follow-up.

---

## A3. When this feature MUST NOT call `add_audit_log`

- Any failed validation (HTTP 422). Audit log calls happen only after the request passes Pydantic + service-level validation.
- Any failed role check (HTTP 403).
- A no-op origin diff (FR-012).
- Changes to `enabled`, `greeting`, or `theme_json` that do not coincide with origin changes.

---

## A4. Transactional behavior

The widget config UPDATE and the audit log INSERTs MUST execute within a single async database transaction:

```python
async with session.begin():
    await widget_repo.update_by_tenant_id(...)
    for added in sorted(new - previous):
        await tenant_repo.add_audit_log(..., action="widget.origin_added", ...)
    for removed in sorted(previous - new):
        await tenant_repo.add_audit_log(..., action="widget.origin_removed", ...)
```

If any `add_audit_log` call raises, the transaction rolls back. The widget config row remains in its pre-call state. The endpoint returns HTTP 500 (per E2).

**Why a single transaction**: matches FR-013 ("If the audit log call fails, the widget configuration update MUST also fail and roll back"). Compensation patterns (write audit first, undo on failure) were rejected in [research.md §R2](../research.md).

---

## A5. New action-vocabulary registration

Two new action strings are introduced by this feature:

- `widget.origin_added`
- `widget.origin_removed`

These join the existing audit-log action vocabulary documented in [CONTRACT.md](../../../CONTRACT.md). The implementation PR adds them to the documented vocabulary in the same commit that ships the call sites. Hiba reviews the doc change as part of the audit-section ownership.

**Naming convention**: `<domain>.<verb_object>`, snake_case verbs, lower-case throughout. Matches the existing `tenant.provisioned` / `tenant.suspended` / `tenant.erased` style.

---

## A6. Test mocking strategy

**Unit tests** mock the `AuditLogger` Protocol passed into the `WidgetConfigService` constructor (see plan.md / tasks.md T004 for the Protocol definition):

```python
from unittest.mock import AsyncMock
fake_audit_logger = AsyncMock()
service = WidgetConfigService(repo=fake_repo, audit_logger=fake_audit_logger)
# After exercising the service, assert:
fake_audit_logger.add_audit_log.assert_awaited_with(
    tenant_id=..., actor_role="tenant_admin",
    action="widget.origin_added",
    actor_id=..., metadata={"origin": ..., "widget_id": ...},
)
```

Tests assert `fake_audit_logger.add_audit_log.call_count` and inspect `call_args_list` for the metadata payload.

**HTTP/contract tests** use FastAPI's `app.dependency_overrides` to inject a fake `AuditLogger` whose `add_audit_log` is an `AsyncMock`. The real Hiba-owned `TenantRepository` implements the `AuditLogger` Protocol incidentally, but tests don't depend on it.

**Integration tests** (Streamlit) do not exercise the audit path directly; they use a fake HTTP client that records the PUT body, and the audit assertions stay in the backend layer.

The real Hiba-owned `add_audit_log` implementation is **not** called from any of this feature's tests. We treat it as an external dependency and test against its documented contract only.
