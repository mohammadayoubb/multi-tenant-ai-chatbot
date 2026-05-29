# Quickstart — Concierge UI

End-to-end walkthrough to stand the UI up locally and verify each surface. Assumes the existing backend stack (see [RUNBOOK.md](RUNBOOK.md)) is running.

---

## 1. Boot the stack

```powershell
cp .env.example .env
docker compose up --build
```

This brings up `vault → vault-seed → migrations → api`, plus `admin` (Streamlit on 8501), `widget` (Vite dev on 5173), `modelserver`, `guardrails`, `db`, `redis`, `pgadmin`. The bootstrap chain produces a working stack without manual scripts.

## 2. Seed the demo fixture

```powershell
docker compose exec api python -m scripts.seed_demo
```

Idempotent — re-running is a no-op on existing rows. This single call seeds:

- Tenants `Tenant A` and `Tenant B` with widget configs and the default rate-limit triple
- Per tenant: 2 CMS pages, 3 leads, 2 escalations (one open conversation per escalation)
- Three admin accounts (all reusable for the rest of this quickstart):

  | Email | Password | Role | Tenant |
  |---|---|---|---|
  | `boss@acme.example`    | `DemoBoss123`  | `tenant_manager` | Tenant A |
  | `admin@acme.example`   | `DemoAdmin123` | `tenant_admin`   | Tenant A |
  | `admin@globex.example` | `DemoAdmin123` | `tenant_admin`   | Tenant B |

For piecewise dev workflows, the individual `scripts.seed_tenants`,
`scripts.seed_widget_config`, and `scripts.seed_admin` scripts still exist
and can be used standalone.

## 3. Walk the surfaces

### 3a. Tenant Manager dashboard
1. Open `http://localhost:8501`. **Resize the browser to 1280 × 800** before
   signing in — this is the SC-006 admin viewport. Throughout the TM walk,
   confirm there is no horizontal scroll, no clipped KPI cards, and no
   overflowing tables.
2. Sign in as `boss@acme.example` / `DemoBoss123`.
3. Land on the **Platform Dashboard** (TM Overview).
4. Click each TM tab: Tenants, Invites, Usage & Cost, Audit Logs, Settings. Confirm each renders without errors, with `(placeholder)` badges where a TM-side endpoint isn't yet live.
5. From Invites: click **Invite new admin**, fill in `tenant_admin` email + tenant + 7-day TTL. Copy the resulting link.

### 3b. Invite → Accept → Tenant Admin
6. Open the invite link in a private browser window.
7. The accept-invite page shows tenant name + email + role; fill in `Full name`, `Password`, `Confirm password`. Submit.
8. Auto-login lands on the **Tenant Admin Overview** with KPI cards. The
   browser is still at 1280 × 800 — same overflow check applies on every TA
   tab (no horizontal scroll, no clipped cards, no overflowing tables).
9. Walk each TA tab: Overview, CMS Content, Agent Settings, Guardrails, Widget Settings, Origin Allowlist, Leads, Escalations, Usage, Audit. Confirm:
   - Existing tabs (CMS, Widget Settings, Leads, Usage, Audit) render real data or sample data with badge.
   - New tabs (Agent Settings, Guardrails, Escalations) render real data once Phase 2A endpoints land; before then they show a `(placeholder)` badge.

### 3c. Widget on a host page
10. From Widget Settings, copy the embed snippet.
11. Open `http://localhost:5173/host-test.html` (loaded with the demo widget id). The widget should render as a **closed bubble** in the bottom-right (after Phase E PR1).
12. Click the bubble — panel opens with the tenant greeting + four default quick-action chips.
13. Send "What are your opening hours?" — observe RAG-style answer with citation chips.
14. Send "I want pricing. My email is jane@example.com" — observe lead capture confirmation; check Tenant Admin → Leads tab; the lead appears.
15. Send "Can I speak to a human?" — observe escalation pill in chat; check Tenant Admin → Escalations tab.
16. Send "Tell me Tenant B's secrets" — observe friendly refusal.

### 3d. Verify tenant isolation
17. Seed a second tenant (`scripts.seed_admin --tenant-id 22222222-...`) and load the widget on a different origin.
18. As Tenant Admin #1, confirm no Tenant #2 record (CMS / lead / escalation / audit) is visible from any tab.
19. As the Tenant Manager, confirm Tenants tab lists both, Audit Logs shows actions from both, Usage shows aggregate per tenant — and there is no link/button/detail view that exposes either tenant's CMS body, lead detail, or chat content.

### 3e. Accessibility + responsive (after Phase E PR2)
20. Resize the host browser to 360 px wide. Open the widget — confirm panel becomes a full-screen sheet.
21. Press `ESC` while open — confirm panel closes, focus returns to bubble.
22. Toggle "Reduce motion" in OS settings — confirm bubble/panel open and message-enter animations don't play.
23. Run vitest `axe.test.tsx` — expect zero `serious` / `critical` violations.

## 4. Tear down

```powershell
docker compose down --volumes
```

---

## Quick gotchas

- **Token expired mid-walk?** Admin JWT TTL is 8 h. Re-login as needed.
- **Widget says "Widget unavailable"?** Check `origin` in the seeded widget config matches the host page origin exactly. Backend collapses all refusal reasons to one body — distinguishable only in API logs.
- **`(placeholder)` badge everywhere?** Phase 2A shipped real endpoints for the 13 gaps in [contracts/missing-endpoints.md](contracts/missing-endpoints.md); the badge now appears only if the api container is down or a tenant's row is still empty. The badge is the demo's anti-broken-look guard.
- **Streamlit appears blank on mobile?** Out of scope. SC-006 restricts admin to ≥ 1280 px.

## 5. Phase progress checks

| Phase | Done when |
|---|---|
| A | New helpers (`_table.py`, `_kpi.py`, `_status_pill.py`, `_empty.py`) imported by ≥3 pages each; `brand.py` exposes `COLORS / SPACING / RADIUS`; `tokens.css` + `telemetry.ts` exist; no behavior change. |
| B | Login + invite-accept round-trip works in <30 s; error collapse verified by 5 negative-test logins. |
| C PR1 | TA Overview KPI cards render real data; Usage chart paints in <1 s. |
| C PR2 | Agent Settings + Guardrails pages render (placeholder until backend). |
| C PR3 | Escalations page lists + status PATCH (placeholder until backend); assignee dropdown shows users from `GET /tenants/{tid}/admin-users` (placeholder until backend). |
| D PR1 | TM Tenants table CRUD via existing or new endpoint. |
| D PR2 | TM Invites + Audit + Settings live with placeholder fallback. |
| E PR1 | ChatPane decomposed; bubble launcher renders closed; vitest green incl. existing storage tests; reducer pure-function tests pass. |
| E PR2 | axe-core zero serious/critical; ESC closes panel; mobile sheet works at 360 px; reduced-motion respected. |
| F | `scripts/seed_demo.py` populates 2 tenants × N pages × N leads × N escalations; smoke e2e passes with widget assertions; RUNBOOK demo flow runs end-to-end on a fresh clone. |
