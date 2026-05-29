# Concierge — Frontend / Backend Integration Specification

**Version:** 1.0
**Date:** 2026-05-29
**Branch baseline:** [009-concierge-ui](specs/009-concierge-ui/)
**Scope locked with stakeholder:** *Retrofit existing repo* (not a rebuild). Two scope tracks:

- **Track 1 — Integration retrofit:** close the 13 missing endpoints from [specs/009-concierge-ui/contracts/missing-endpoints.md](specs/009-concierge-ui/contracts/missing-endpoints.md) + wire the admin/widget UI to them.
- **Track 2 — Agent retrofit:** graduate the stub router + stub agent + three tools to the production shape mandated by [Concierge_Backend_Blueprint.md](Concierge_Backend_Blueprint.md): the router uses the real ONNX classifier with a confidence threshold; only **ambiguous or multi-step** turns reach the agent; the agent is a **single tool-calling LLM** (not a fixed graph) with hard loop bounds; the three tools (`rag_search`, `capture_lead`, `escalate`) are real, schema-validated, tenant-scoped, and rate-limited at the tool boundary; session memory in Redis with a justified TTL; prompts version-controlled under [app/prompts/](app/prompts/) with tenant persona injected at runtime from `tenant_agent_configs`, never hardcoded.

**Still out of scope** (Phase 4/5/9 owner work tracked in [BLOCKED.md](BLOCKED.md)): pgvector ANN retrieval (rag_search keeps the lexical baseline this feature ships against; pgvector wiring is N1 follow-on), `messages` table durable persistence (Redis short-term memory is the durable surface for this feature per blueprint), `traces` table writes (out — `widget_logging` continues stdout-only), background job runner, WebSockets/SSE, tenant erasure walk-through.

**Authoritative source for the target state:** [Concierge_Backend_Blueprint.md](Concierge_Backend_Blueprint.md), [CONTRACT.md](CONTRACT.md) §2.5–§2.9 + §8.1, [specs/009-concierge-ui/contracts/missing-endpoints.md](specs/009-concierge-ui/contracts/missing-endpoints.md).

---

## §1 System Overview

### 1.1 Architecture

```
                                  Visitor browser
                                        │
                                        ▼
   ┌────────────────────────────────────────────────────────────────┐
   │  Embeddable widget (React 18 / Vite iframe)                    │
   │  - frontend/widget/public/widget.js  ES2019 hand-authored      │
   │  - frontend/widget/src/  React app served from /widget         │
   │  - Token in module scope only (Constitution IV)                │
   └────────────────────────────────────────────────────────────────┘
                                        │  HTTPS / Bearer widget JWT
                                        ▼
                              ┌──────────────────┐
   Tenant ops (1280px desk)   │   FastAPI API    │   ◄── HS256 admin JWT
   ┌──────────────────┐       │   app/main.py    │
   │ Streamlit admin  │──────▶│   port 8000      │
   │ admin/  (8501)   │       └──────┬───────────┘
   └──────────────────┘              │ async SQLAlchemy
                                     │ + Redis client
                                     │ + service-auth bearer
                                     ▼
   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌────────────┐
   │ Postgres +   │   │  Redis       │   │ Modelserver  │   │ Guardrails │
   │ pgvector     │   │  session     │   │  ONNX (8010) │   │ sidecar    │
   │ 19 tables    │   │  memory      │   │  /predict    │   │ (8020)     │
   │ RLS forced   │   │  TTL 1800s   │   │              │   │ /check     │
   └──────────────┘   └──────────────┘   └──────────────┘   └────────────┘
              ▲
              │ Vault bootstrap (app/infra/vault.py)
              └─────────────── HashiCorp Vault (8200) — all runtime secrets
```

Compose graph in [docker-compose.yml](docker-compose.yml) wires two bootstrap services (`vault-seed`, `migrations`) that run once and exit before `api` boots.

### 1.2 Responsibility Split

| Concern | Frontend | Backend |
|---|---|---|
| Tenant identity | **NEVER decides** — reads from JWT response | Sole authority — derives from signed token, never from request body |
| Role gating (TA/TM/visitor) | Reads `auth_state.role` to pick dispatcher | Enforced in every dep (`require_tenant_admin`, `require_admin_session`) |
| Auth credential storage | Memory-only: widget = module scope; admin = `st.session_state` | Mints HS256 JWTs (widget: 15 min, admin: 8 h) |
| Session memory | None (widget redraws from in-page state; admin re-renders per interaction) | Redis `session:{tenant_id}:{session_id}` TTL 1800 s, redacted |
| Validation | Soft UX only (counter, contrast warning) | Pydantic `extra=forbid`, server-side allowlists, RLS |
| Rate limiting | None | Per-IP + per-widget at `/widgets/token`; per-tenant elsewhere |
| Redaction | No PII in telemetry (currently a no-op stub) | All persisted text → `app/infra/redaction.py` before write |
| Errors | Single fallback path (`(placeholder)` + canned sample) | Uniform 401/403 byte-bodies (refusal symmetry) |

### 1.3 Data-flow walkthroughs

**(a) Visitor message round-trip:**
1. `widget.js` iframe loads; `postMessage` sends host origin to React app (`main.tsx`).
2. React calls `POST /widgets/token` with `{widget_id}` ([api.ts:29-46](frontend/widget/src/api.ts#L29-L46)).
3. Server validates `widget_id` against `widget_configs` (RLS-scoped via `WidgetRepository`), validates `origin` against `allowed_origins_json`, mints HS256 JWT carrying `{tenant_id, widget_id, exp}`; refusal collapses to byte-identical 403 (Decision 4).
4. Token stored in `_token` module variable. React fetches `GET /tenants/{tid}/agent-config` for chips+greeting; falls back to hard-coded English defaults on 404/501/5xx ([api.ts:143-147](frontend/widget/src/api.ts#L143-L147)).
5. User types → `POST /chat` with `Authorization: Bearer <jwt>` and `{message, session_id}`.
6. `chat.py` route → `ChatService.handle_message()` → redact → Redis append → `route_message_decision()` (lexical stub) → tool dispatch (`rag_search` / `capture_lead` / `escalate`) → Redis append assistant turn → `ChatResponse`.
7. On 401 → terminal "Session expired, please reload" banner ([api.ts:122-124](frontend/widget/src/api.ts#L122-L124)); on other non-2xx or transport → retryable "Couldn't reach the assistant".

**(b) Admin save round-trip (widget config example):**
1. Streamlit page in `widget_page.py` renders draft state seeded from `GET /widgets/config`.
2. User edits theme via 3 color pickers; client-side WCAG check warns but does not block.
3. On Save → `_admin_http.http_client()` attaches `Authorization: Bearer <admin_jwt>` from `st.session_state["admin_token"]` → `PUT /widgets/config`.
4. Route uses `require_tenant_admin` ([app/api/deps.py:159-209](app/api/deps.py#L159-L209)) → validates body with Pydantic + theme key allowlist → `WidgetConfigService.update_config()` → audit log via `TenantRepository.add_audit_log()` (action `widget.origin_added` / `widget.origin_removed`) → commit.
5. Streamlit reruns; non-2xx collapses to a `(placeholder)` notice or canonical error toast.

### 1.4 Authentication & Session Flow

- **Widget JWT** — HS256, signed with `WIDGET_JWT_SECRET` (Vault-resolved); 15 min; payload `{tenant_id: uuid, widget_id: uuid, exp}`; verified by `get_tenant_id_from_widget_token` ([app/api/deps.py:32-62](app/api/deps.py#L32-L62)); failure path collapses to a single 401 byte-body so callers cannot distinguish "no token" / "bad token" / "expired token".
- **Admin JWT** — HS256, signed with `ADMIN_JWT_SECRET`; 8 h, no refresh (DECISION 12); payload `{tenant_id, actor_id, role}` where role ∈ {`tenant_admin`, `tenant_manager`}; verified by `require_admin_session` / `require_tenant_admin`; dev-header fallback (`X-Concierge-Role` / `X-Concierge-Tenant-Id` / `X-Concierge-Actor-Id`) honored only when `CONCIERGE_ENV=dev` ([app/api/deps.py:142-156](app/api/deps.py#L142-L156)).
- **Platform actor** — `X-Actor-ID` / `X-Actor-Role` headers via `get_platform_actor` ([app/api/deps.py:65-76](app/api/deps.py#L65-L76)). Used by legacy `POST /tenants` provisioning route; phase-out planned for TM-scope admin-JWT endpoints (#13 in §4.2).
- **Service-to-service** — Bearer `MODELSERVER_SERVICE_TOKEN` and guardrails service token; internal-network only.

### 1.5 API Communication Patterns

- **Transport:** REST/JSON over HTTPS, async FastAPI.
- **Auth carrier:** `Authorization: Bearer <jwt>` on every authenticated route. No cookies, no localStorage.
- **Polling only:** Streamlit reruns on every interaction; widget polls only on user action. **No WebSockets, no SSE** (explicitly out of scope — §5.9).
- **Placeholder fallback (Decision 8):** every admin read collapses non-2xx / 2xx-with-missing-field / transport error to one canned-sample render with a visible `(placeholder)` caption. Only two render paths exist per page.
- **Refusal symmetry (Decision 4, FR-017):** widget refusals collapse to identical 403 bodies; admin auth failures collapse to identical 401 bodies; a dummy bcrypt verify runs on email-miss to keep timing constant.

---

## §2 Frontend Analysis

### 2.1 Page Inventory

**Widget (visitor)** — `frontend/widget/src/`:

| Component | File | Role |
|---|---|---|
| Loader | [public/widget.js](frontend/widget/public/widget.js) | ES2019 hand-authored; idempotent iframe injection; postMessage handshake |
| Orchestrator | [src/ChatWidget.tsx](frontend/widget/src/ChatWidget.tsx) | Bubble ↔ Panel toggle, consumes `useChatReducer` |
| Bubble | `src/components/Bubble.tsx` | 80×80 launcher; accepts `themeColor` |
| Panel | `src/components/Panel.tsx` | Focus-trapped message surface |
| Message | `src/components/Message.tsx` | User/assistant bubbles, citation chips, ticket pill |
| Input | `src/components/ChatInput.tsx` | Enter-to-send, 2000-char cap, counter ≥1800 |
| Quick actions | `src/components/QuickActions.tsx` | 0–6 chips from agent config; hides if empty |
| Empty state | `src/components/EmptyState.tsx` | First-open greeting card; `(sample greeting)` when placeholder |
| Status banner | `src/components/StatusBanner.tsx` | "Session expired" (terminal) / "Couldn't reach" (retry) |
| Focus trap | `src/a11y/FocusTrap.tsx` | Tab wrap, ESC binding |

**Admin tenant_admin (9 tabs)** — `admin/tenant_dashboard.py:30-40` radio dispatcher:

| Tab | Page module | Endpoint(s) consumed |
|---|---|---|
| Overview | `admin/overview_page.py` | `/widgets/config`, `/tenants/{tid}/usage`, `/leads`, `/escalations`, `/tenants/{tid}/conversations` |
| CMS | `admin/cms_page.py` | `GET /cms/pages` (live), `POST /cms/pages` (live), **PUT/PATCH/DELETE pending** |
| Agent | `admin/agent_settings_page.py` | **`GET/PUT /tenants/{tid}/agent-config` pending** |
| Guardrails | `admin/guardrails_page.py` | **`GET /tenants/{tid}/platform-guardrails` pending** |
| Widget | `admin/widget_page.py` | `GET/PUT /widgets/config` (live) |
| Leads | `admin/leads_page.py` | `GET /leads` (live, read-only) |
| Escalations | `admin/escalations_page.py` | **`GET /escalations`, `PATCH /escalations/{id}`, `GET /tenants/{tid}/admin-users` pending** |
| Usage | `admin/usage_page.py` | `GET /tenants/{tid}/usage` (live) |
| Audit | `admin/audit_page.py` | `GET /tenants/{tid}/audit-logs` (live) |

**Admin tenant_manager (6 tabs)** — `admin/streamlit_app.py:35-72` sidebar radio:

| Tab | Page module | Endpoint(s) consumed |
|---|---|---|
| Overview | `admin/platform_dashboard_page.py` | aggregate over `/tenants` + `/admin/audit-logs` |
| Tenants | `admin/tenants_page.py` | **`GET /tenants` (TM-scope) pending**; `POST /tenants/{tid}/suspend` (live) |
| Invites | `admin/invites_page.py` | `POST /admin/invites` (live), **revoke/resend pending** |
| Usage & Cost | `admin/usage_page.py` | per-tenant rollup |
| Audit Logs | `admin/audit_page.py` | **`GET /admin/audit-logs` (TM-scope) pending** |
| Settings | `admin/settings_page.py` | **`PUT /tenants/{tid}/settings` pending** |

Public surfaces (no auth): `admin/login_page.py`, `admin/accept_invite_page.py`, `admin/access_denied_page.py`. Dispatched by query param `?page=accept-invite` in `streamlit_app.py:76-93`.

### 2.2 State Management

- **Widget reducer** — pure in [src/state/useChatReducer.ts](frontend/widget/src/state/useChatReducer.ts). State `{open, messages[], status, pendingPrompt, errorKind}`. Actions: `OPEN`, `CLOSE`, `SEND_START`, `SEND_OK`, `SEND_ERROR`, `SESSION_EXPIRED`, `RETRY_LAST`, `RESET`. `SEND_START` ignored while `status ∈ {"sending","expired"}` (single-in-flight guard). Hook wraps reducer with impure `send/retry` calling `api.ts`. The orchestrator (`main.tsx`) is the only file that knows both visual layout and dispatcher (DECISION 16).
- **Widget API store** — module-scope closure `_token / _sessionId / _expiresAt` in [api.ts:16-18](frontend/widget/src/api.ts#L16-L18). `__debugSetToken` / `__debugTokenStoreSnapshot` are test seams. Never browser storage (Constitution IV).
- **Admin session** — `auth_state.py` writes 5 keys to `st.session_state` on login: `admin_token`, `admin_actor_id`, `admin_tenant_id`, `admin_role`, `admin_full_name`. `clear_session()` wipes all on logout. No keys are user-editable.
- **Per-page draft state** (canonical pattern in `widget_page.py:176-194`): three independent init guards — `*_saved` (server snapshot), `*_draft` (working copy), `*_text` (raw textarea). Unsaved-changes indicator blocks Save when dirty. New pages from §4.2 MUST adopt this pattern.

### 2.3 Reusable UI Helpers

| Helper | Used by | Purpose |
|---|---|---|
| `admin/_admin_http.py` | every authenticated page | `http_client()` injects `Authorization: Bearer <admin_token>`; centralizes `_DEV_HEADERS` (removed in DECISION 12) |
| `admin/brand.py` | login + accept-invite | centered card CSS, COLORS/SPACING/RADIUS dicts |
| `admin/_kpi.py` | overview pages | `render_kpi_row()` wrap `st.metric` columns |
| `admin/_status_pill.py` | tenants / leads / tickets / invites | inline `<span>` badges with kind-aware palette |
| `admin/_table.py` | every list page | `render_table()` with filters + empty_state |
| `admin/_empty.py` | every list page | placeholder render |

### 2.4 Missing API Integrations (mapped to §4.2 contracts)

Every admin page currently renders `(placeholder)` when its endpoint is unreachable. The 13 missing endpoints map 1-to-1 to these placeholder captions:

| Page | Caption location | Missing endpoint (§4.2 #) |
|---|---|---|
| `overview_page.py:142-147` | Overview KPI section | composite — needs #1, #4, #5 |
| `agent_settings_page.py:100-102` | "Agent config" section | #1, #2 |
| `guardrails_page.py:206-208` | "Platform rules" section | #3 |
| `escalations_page.py:220-221` | "Escalations" + assignee dropdown | #4, #5, #6 |
| `cms_page.py:281-283 + 330-331` | CMS list + mutating controls | #10, #11, #12 |
| `settings_page.py` | Settings form save | #7 |
| `invites_page.py` | Revoke / Resend buttons | #8, #9 |
| `tenants_page.py` | TM tenants table | #13a |
| `audit_page.py` (TM mode) | TM audit feed | #13b |

### 2.5 Hardcoded / Mock Data

| Location | Constant | Should be replaced by |
|---|---|---|
| [api.ts:143-147](frontend/widget/src/api.ts#L143-L147) | `AGENT_CONFIG_PLACEHOLDER` (English defaults) | response from `GET /tenants/{tid}/agent-config` (#2) |
| `escalations_page.py:35-44` | `_SAMPLE_TICKETS` | response from `GET /escalations` (#5) |
| `_admin_http.py:26` | hardcoded `TENANT_ID = "11111111-1111-1111-1111-111111111111"` | JWT-derived tenant_id |
| `agent_settings_page.py` sample dict | persona/tone/chips | response from `GET /tenants/{tid}/agent-config` (#2) |
| `guardrails_page.py` sample rules | 4 hard-coded rules | response from `GET /tenants/{tid}/platform-guardrails` (#3) |

### 2.6 Loading & Error States — what's already there

- Widget — `StatusBanner.tsx:17-49` renders terminal "Session expired" (no retry) for `status="expired"`, retryable "Couldn't reach" for `status="error"`. Input/chips disabled when `status ∈ {"sending","expired"}`.
- Admin — `_get_json(path) → (body, ok)` collapse pattern in every page; non-2xx returns `(None, False)` and triggers the `(placeholder)` render.
- **What's missing** (§4.4): spinner-then-toast on every write (PUT/PATCH/DELETE) is inconsistent; some pages no-op silently. Confirm-dialog on destructive actions (CMS delete, invite revoke) is missing from the no-op-stub flows.

---

## §3 Backend Analysis

### 3.1 Route Inventory

Routes registered in [app/main.py](app/main.py).

| Method | Path | Auth dep | Service | Status |
|---|---|---|---|---|
| POST | `/admin/login` | none | `AdminAuthService.authenticate` | ✅ live |
| POST | `/admin/invites` | `require_admin_session` | `AdminInviteService.send_invite` | ✅ live |
| GET | `/admin/invites/{token}` | none | `AdminInviteService.get_by_token` | ✅ live |
| POST | `/admin/invites/{token}/accept` | none | `AdminInviteService.accept_invite` | ✅ live |
| POST | `/admin/invites/{token}/revoke` | `require_admin_session` | — | ❌ **missing (#8)** |
| POST | `/admin/invites/{token}/resend` | `require_admin_session` | — | ❌ **missing (#9)** |
| POST | `/widgets/token` | none + IP/widget rate limiter | `WidgetTokenService.issue_token` | ✅ live |
| GET | `/widgets/config` | `require_tenant_admin` | `WidgetConfigService.get_config` | ✅ live |
| PUT | `/widgets/config` | `require_tenant_admin` | `WidgetConfigService.update_config` | ✅ live |
| POST | `/chat` | `get_tenant_id_from_widget_token` | `ChatService.handle_message` | ⚠️ Track 2 upgrade — real router + real agent + real escalate tool DB write |
| GET | `/cms/pages` | `require_admin_session` | `CmsRepository.list_pages` | ✅ live |
| POST | `/cms/pages` | `require_admin_session` | `CmsRepository.create` | ✅ live |
| PUT | `/cms/pages/{id}` | `require_tenant_admin` | `CmsPageService.update` | ❌ **missing (#10)** |
| PATCH | `/cms/pages/{id}/status` | `require_tenant_admin` | `CmsPageService.set_status` | ❌ **missing (#11)** |
| DELETE | `/cms/pages/{id}` | `require_tenant_admin` | `CmsPageService.delete` | ❌ **missing (#12)** |
| GET | `/leads` | `require_admin_session` | `LeadRepository.list_by_tenant` | ✅ live |
| GET | `/escalations` | `require_admin_session` | `EscalationService.list_for_tenant` | ❌ **missing (#5)** |
| PATCH | `/escalations/{id}` | `require_admin_session` | `EscalationService.patch` | ❌ **missing (#4)** |
| POST | `/tenants` | `get_platform_actor` | `TenantService.provision_tenant` | ✅ live (legacy) |
| GET | `/tenants` (TM-scope) | `require_admin_session` (TM only) | `TenantService.list_for_manager` | ❌ **missing (#13a)** |
| GET | `/tenants/{id}` | `get_platform_actor` | `TenantService.get_tenant` | ✅ live |
| POST | `/tenants/{id}/suspend` | `get_platform_actor` | `TenantService.suspend_tenant` | ✅ live |
| GET | `/tenants/{id}/audit-logs` | `require_admin_session` | `TenantRepository.list_audit_logs` | ✅ live |
| GET | `/tenants/{id}/usage` | `require_admin_session` | `TenantRepository.usage_rollup` | ✅ live |
| GET | `/tenants/{id}/agent-config` | `require_tenant_admin` or widget JWT | `AgentConfigService.get` | ❌ **missing (#2)** |
| PUT | `/tenants/{id}/agent-config` | `require_tenant_admin` | `AgentConfigService.put` | ❌ **missing (#1)** |
| GET | `/tenants/{id}/platform-guardrails` | `require_tenant_admin` | `PlatformGuardrailsService.read` | ❌ **missing (#3)** |
| GET | `/tenants/{id}/admin-users` | `require_admin_session` | `AdminUserRepository.list_by_tenant` | ❌ **missing (#6)** |
| PUT | `/tenants/{id}/settings` | `require_admin_session` (TM only) | `TenantSettingsService.upsert` | ❌ **missing (#7)** |
| GET | `/audit-logs` (TM-scope) | `require_admin_session` (TM only) | `TenantRepository.list_all_audit_logs` | ❌ **missing (#13b)** |

### 3.2 Services Inventory

| Service | File | Status |
|---|---|---|
| `AdminAuthService` | `app/services/admin_auth.py` | ✅ complete (bcrypt + JWT mint + verify) |
| `AdminInviteService` | `app/services/admin_invite.py` | ⚠️ needs `revoke()` + `resend()` methods (§5.4) |
| `AdminSettingsService` | `app/services/admin_settings.py` | 🪦 **dead stub** (replaced by `tenant_settings.py`) — delete in §6 |
| `AgentConfigService` | `app/services/agent_config.py` | 🪦 **dead stub** — implement GET/PUT in §5.4 |
| `ChatService` | `app/services/chat_service.py` | ⚠️ deterministic stub router/agent; **tenant_id type bug at L48** — §6 |
| `CmsPagesService` | `app/services/cms_pages.py` | ⚠️ `update`/`delete`/`set_status` exist; need route wiring — §5.4 |
| `CmsService` | `app/services/cms_service.py` | 🪦 **dead stub** — delete in §6 |
| `EscalationService` | `app/services/escalation.py` | ⚠️ `list_for_tenant` + `patch` exist; need route wiring + audit-log call — §5.4 |
| `PlatformGuardrailsService` | `app/services/platform_guardrails.py` | ⚠️ `evaluate_platform_rails` complete; needs `read()` for admin UI — §5.4 |
| `RateLimiterService` | `app/services/rate_limiter.py` | ✅ complete (token-bucket) |
| `TenantService` | `app/services/tenant_service.py` | ⚠️ needs `list_for_manager()` — §5.4 |
| `TenantSettingsService` | `app/services/tenant_settings.py` | ⚠️ `get`/`upsert` exist; need route wiring — §5.4 |
| `WidgetLoggingService` | `app/services/widget_logging.py` | ✅ stdout (writing to `traces` table deferred — out of scope) |
| `WidgetConfigService` / `WidgetTokenService` | `app/services/widget_service.py` | ✅ complete |
| `WidgetSettingsService` | `app/services/widget_settings.py` | ✅ complete (Vault-aware) |

### 3.3 Repositories — Tenant-Scoping Audit

| Repo | Tenant-scope mechanism | Notes |
|---|---|---|
| `AdminInviteRepository` | tenant_id FK + WHERE | needs `mark_revoked()` for #8 |
| `AdminUserRepository` | tenant_id FK + WHERE | needs `list_by_tenant()` for #6 |
| `AgentConfigRepository` | tenant_id FK + WHERE | needs `get_by_tenant()` / `upsert()` for #1, #2 |
| `CmsRepository` | explicit WHERE every query | already supports update/delete (service callable) |
| `EscalationRepository` | WHERE in `list_by_tenant` | already supports `update_status_and_assignee` |
| `LeadRepository` | WHERE tenant_id in `create` + `list_by_tenant` | ✅ live |
| `TenantRepository` | `@asynccontextmanager _tenant_context(tenant_id)` sets `app.tenant_id` for RLS | needs `list_for_manager()`, `list_all_audit_logs()` for #13a/#13b |
| `TenantSettingsRepository` | tenant_id FK + WHERE | already supports `upsert()` |
| `WidgetRepository` | Protocol; `SqlWidgetRepository` uses tenant_id FK | ✅ live |

**No repositories exist for `Message`, `RagChunk`, `Trace`, `EscalationTicket` (the latter needs one to graduate from synthetic ticket_id to a real DB row).** EscalationTicket repo addition is in-scope as part of #4. The other three remain out of scope (§5.9).

### 3.4 Models & Migrations

[app/db/models.py](app/db/models.py) (724 lines) mirrors 19 tables; migrations 0001–0006 in [app/db/migrations/versions/](app/db/migrations/versions/):

| Migration | Adds |
|---|---|
| `0001_hiba_platform_schema_rls.py` | 8 tables: tenants, admin_users, audit_logs, tenant_usage, tenant_rate_limit, erasure_jobs, cms_pages, leads, conversations + RLS forced |
| `0002_admin_users.py` | (kept for legacy) |
| `0003_admin_invites.py` | admin_invites + RLS |
| `0004_contract_schema_parity.py` | **+8 tables**: users, tenant_memberships, widget_configs, tenant_agent_configs, **rag_chunks (vector 1536d)**, **messages**, **escalation_tickets**, **traces** — all RLS-enabled. Extends 4 tables. |
| `0005_admin_invites_revoked_at.py` | adds `revoked_at` column — **needed by #8** |
| `0006_tenant_settings.py` | adds `tenant_settings` table — **needed by #7** |

**Phantom tables (created in 0004, written by zero code, status quo):** `rag_chunks`, `messages`, `escalation_tickets`, `traces`. The first three carry intentional out-of-scope status (§5.9); the fourth (`escalation_tickets`) is brought into scope by #4 via a new `EscalationRepository.create()` path.

### 3.5 Deps & Middleware

[app/api/deps.py](app/api/deps.py):

- `get_tenant_id_from_widget_token` (L32-62) — JWT HS256 verify, all failures → 401.
- `get_platform_actor` (L65-76) — `X-Actor-ID` / `X-Actor-Role` headers, legacy provisioning path.
- `require_admin_session` (L109-156) — admin JWT OR dev-headers; accepts `tenant_admin` OR `tenant_manager`. **Use for new routes #4, #5, #6, #7, #8, #9, #13a, #13b** (§5.4).
- `require_tenant_admin` (L159-209) — admin JWT OR dev-headers; **only `tenant_admin`** (rejects TM). **Use for new routes #1, #2, #3, #10, #11, #12.**
- Dev-header fallback active only when `CONCIERGE_ENV=dev` (L142, L195). Production = JWT-only.

**Bug spotted** (out of integration scope but worth fixing in §6): [app/api/deps.py:91](app/api/deps.py#L91) has a dead `return 1` after the `return TenantService(repo)` line.

### 3.6 Infra Layer

[app/infra/](app/infra/) — `vault.py` (secret resolution), `redaction.py` (PII/secret stripping), `modelserver.py` (ONNX client), `guardrails.py` (sidecar client), `cache.py` (Redis SessionMemory with graceful fallback), `password.py` (bcrypt), `tracing.py` (stdout — `traces` table writes deferred).

### 3.7 Agent / RAG — current state and Track-2 gaps

`POST /chat` orchestration today ([app/services/chat_service.py](app/services/chat_service.py)):

```
ChatService.handle_message(tenant_id, message, session_id)
  ├─ redact(message)
  ├─ SessionMemory.append (Redis, session:{tenant_id}:{session_id}, TTL 1800s)
  ├─ route_message_decision(message)      ← stub: lexical match, NOT the ONNX classifier
  ├─ dispatch:
  │   - "blocked"      → canned refusal
  │   - "rag_search"   → retrieve_chunks (lexical on cms_pages.body, NOT pgvector)
  │   - "capture_lead" → LeadRepository.create  ✅ real DB row
  │   - "escalate"     → return synthetic ticket_id  ⚠️ NO DB row
  │   - default        → run_agent()  ← stub deterministic plan
  └─ SessionMemory.append (assistant turn)
```

**Track-2 gaps (now in scope):**

| Component | Current | Target (per blueprint) | Reference |
|---|---|---|---|
| Router | Lexical stub in [app/agent/router.py](app/agent/router.py) | Real ONNX classifier via `modelserver /predict`; emits `(label, confidence)`; **low-confidence (≤ threshold) OR `ambiguous` label → agent** | DECISION §C; CONTRACT.md §2.4 |
| Workflow paths | Deterministic dispatch on confident labels | Unchanged for high-confidence FAQ / sales / human-request / spam | — |
| Agent | Deterministic plan in [app/agent/agent.py](app/agent/agent.py) | Single tool-calling LLM (function-calling), picks among 3 tools under uncertainty, NOT a fixed graph | Blueprint "The Agent & its three tools" |
| Loop bounds | constants exist | Hard cap: `MAX_AGENT_ITERATIONS=5`, `MAX_AGENT_TOKENS_PER_TURN=4000`; agent halts on cap with safe-fallback "I'm not able to help with that — escalating" + emits `agent.iteration_cap_hit` audit log | CLAUDE.md Agent Rules; DECISION §Agent |
| `rag_search` | Lexical retrieve_chunks ([app/rag/retriever.py](app/rag/retriever.py)) tenant-scoped | **No change in this feature** — lexical baseline ships; pgvector indexing is N1 (Nasser) follow-on | BLOCKED.md N1 |
| `capture_lead` | Real `LeadRepository.create` write, tenant-scoped, redacted intent | Add tool-argument Pydantic schema validation, **per-session rate limit** (5 writes/session default), explicit tenant_id-from-trusted-context-only invariant (already true, must stay) | Blueprint "capture_lead is an unauthenticated, LLM-triggered write" |
| `escalate` | Returns synthetic `ticket_id`, no DB write | Real `EscalationRepository.create()` insert into `escalation_tickets` (table already in migration 0004); emits `escalation.created` audit log; ticket then surfaces in #4/#5 admin UI | Blueprint "escalate ... open a ticket row" |
| Redis memory | `session:{tenant_id}:{session_id}`, TTL 1800 s ([app/infra/cache.py](app/infra/cache.py)) | Unchanged. TTL justification documented in §5.10. | DECISION §Memory |
| Prompts | [app/prompts/system_prompt.md](app/prompts/system_prompt.md) (single file) | Split into platform-locked system prompt + tenant persona block injected at runtime from `tenant_agent_configs.persona_name + tone + business_rules` (consumed via #1/#2). Never hardcoded per tenant. | Blueprint "prompts live in prompts/, version-controlled. Tenant persona is injected at runtime from config" |

The escalate-tool DB write is also the prerequisite for #4 `PATCH /escalations/{id}` to have rows to operate on — Track 1 and Track 2 dovetail at `EscalationRepository.create()`.

### 3.8 Architecture Problems (in-scope for §6)

- **Dead stubs**: `app/services/cms_service.py`, `app/services/admin_settings.py`, `app/services/agent_config.py` — first two are replaceable by `cms_pages.py` and `tenant_settings.py`; the third needs to be filled per #1/#2.
- **Type bug**: `chat_service.py:48` types `tenant_id: int` — widget JWT returns `UUID`. Silent because no static checker covers this path. Fix in §6.
- **Dead return**: `app/api/deps.py:91` — unreachable `return 1` after `return TenantService(repo)`.
- **Placeholder helper duplication**: `_PLACEHOLDER = "—"` and the `(placeholder)` caption helper are inlined in every admin page; should be promoted into `admin/_admin_http.py`.

---

## §4 Integration Analysis

### 4.1 Feature → Endpoint Map

| UI surface | Displayed data | Current source | Target endpoint | Status |
|---|---|---|---|---|
| Widget panel greeting + chips | greeting, chips[0..6] | Hardcoded English defaults ([api.ts:143-147](frontend/widget/src/api.ts#L143-L147)) | `GET /tenants/{tid}/agent-config` | ❌ #2 |
| Widget chat answers | answer + route + citations + ticket_id | `POST /chat` (live; router/agent stubs become real in Track 2) | unchanged endpoint, upgraded internals | ⚠️ Track 2 (§5.10) |
| TA Overview KPIs | widget enabled, leads, escalations, usage | `GET /widgets/config`, `GET /leads`, `GET /escalations`, `GET /tenants/{tid}/usage` | unchanged | ⚠️ partial (#5) |
| TA CMS list | id, title, slug, body, status, updated_at | `GET /cms/pages` (live) | unchanged | ✅ |
| TA CMS edit/publish/delete | n/a | disabled with `(placeholder)` | `PUT /cms/pages/{id}`, `PATCH /cms/pages/{id}/status`, `DELETE /cms/pages/{id}` | ❌ #10, #11, #12 |
| TA Agent settings | persona, tone, language, chips, rules | sample dict (`agent_settings_page.py`) | `GET/PUT /tenants/{tid}/agent-config` | ❌ #1, #2 |
| TA Guardrails | platform rules + tenant overrides | 4 hardcoded sample rules | `GET /tenants/{tid}/platform-guardrails` | ❌ #3 |
| TA Widget config | theme, greeting, allowed_origins, enabled | `GET/PUT /widgets/config` (live) | unchanged | ✅ |
| TA Leads | id, name, contact, status, quality_score | `GET /leads` (live, read-only) | unchanged | ✅ |
| TA Escalations | tickets + assignee + admin dropdown | `_SAMPLE_TICKETS` ([escalations_page.py:35-44](admin/escalations_page.py#L35-L44)) | `GET /escalations`, `PATCH /escalations/{id}`, `GET /tenants/{tid}/admin-users` | ❌ #4, #5, #6 |
| TA Usage | totals + by-feature + daily_cost | `GET /tenants/{tid}/usage` (live) | unchanged | ✅ |
| TA Audit | actor / action / metadata feed | `GET /tenants/{tid}/audit-logs` (live) | unchanged | ✅ |
| TM Overview | aggregate KPIs | sample dict | derived from #13a + #13b | ❌ |
| TM Tenants | id, name, status, created_at, plan | sample 4 rows | `GET /tenants` (TM-scope) | ❌ #13a |
| TM Invites | issue / revoke / resend | issue live; rest no-op | `POST /admin/invites/{token}/revoke`, `POST /admin/invites/{token}/resend` | ❌ #8, #9 |
| TM Usage & Cost | per-tenant rollup | sample | aggregate of `/tenants/{tid}/usage` (live) | ⚠️ needs TM aggregation route |
| TM Audit Logs | platform-wide feed | sample | `GET /audit-logs` (TM-scope) | ❌ #13b |
| TM Settings | TTL + rate-limit caps | form no-ops | `PUT /tenants/{tid}/settings` | ❌ #7 |

### 4.2 Authoritative Contract for the 13 Missing Endpoints

Source: [specs/009-concierge-ui/contracts/missing-endpoints.md](specs/009-concierge-ui/contracts/missing-endpoints.md). Below is the canonical summary.

#### #1 `PUT /tenants/{tid}/agent-config`
- **Auth:** `require_tenant_admin`; route rejects if path-`tid` ≠ JWT tenant_id (403 byte-uniform).
- **Body:** `{persona_name, greeting, tone, language, business_rules, chips: string[0..6 each 1..40 chars]}`; `extra=forbid`.
- **Service:** `AgentConfigService.put(tenant_id, body)` → `AgentConfigRepository.upsert()`.
- **Audit:** `tenant.agent_config_updated` (new vocab entry — add to `audit_logs` vocabulary).
- **Response 200:** echoed persisted shape.

#### #2 `GET /tenants/{tid}/agent-config`
- **Auth:** `require_tenant_admin` OR widget JWT for `tid == jwt.tenant_id` (widget needs chips on panel open).
- **Service:** `AgentConfigService.get(tenant_id)` → repo. 404 if absent (widget falls back to defaults).
- **Response 200:** same shape as #1 body.

#### #3 `GET /tenants/{tid}/platform-guardrails`
- **Auth:** `require_tenant_admin`.
- **Service:** `PlatformGuardrailsService.read(tenant_id)` reads locked platform rules from `app/services/platform_guardrails.py` + tenant overrides from `tenant_agent_configs` extension.
- **Response 200:** `{platform_rules: [{id, name, locked: true}], tenant_blocked_topics: [...], tenant_refusal_tone: "polite"}`.

#### #4 `PATCH /escalations/{id}`
- **Auth:** `require_admin_session`; route enforces `escalation.tenant_id == jwt.tenant_id` (403 byte-uniform).
- **Body:** `{status: "pending"|"in_progress"|"resolved", assignee_id: uuid|null}`; `extra=forbid`. `assignee_id` MUST be an `admin_users` row of the same tenant (422 if cross-tenant).
- **Service:** `EscalationService.patch(ticket_id, body, actor_id)` → `EscalationRepository.update_status_and_assignee()`. **Each delta (status or assignee) emits a separate audit-log entry**: `escalation.status_changed`, `escalation.assignee_changed`.
- **Response 200:** updated ticket.

#### #5 `GET /escalations?tenant_id={tid}`
- **Auth:** `require_admin_session`; query `tenant_id` accepted only when `jwt.role == "tenant_manager"`, otherwise scoped to JWT tenant.
- **Service:** `EscalationService.list_for_tenant(tenant_id)` (already exists).
- **Response 200:** `[{ticket_id, opened_at, last_message_excerpt, status, assignee_id, assignee_name}]`.

#### #6 `GET /tenants/{tid}/admin-users`
- **Auth:** `require_admin_session`; `tid` MUST equal JWT tenant_id (no cross-tenant read).
- **Service:** `AdminUserRepository.list_by_tenant()` (new method).
- **Response 200:** `[{actor_id, full_name, email, role, status}]`. **Used exclusively** for the Escalations assignee dropdown.

#### #7 `PUT /tenants/{tid}/settings`
- **Auth:** `require_admin_session`, then service rejects if `role != "tenant_manager"` (403).
- **Body:** `{default_invite_ttl_seconds, rate_limit_chat_per_minute, rate_limit_token_per_minute}`; `extra=forbid`; values clamped to published min/max.
- **Service:** `TenantSettingsService.upsert(tenant_id, body)`.
- **Audit:** `tenant.settings_updated` (new vocab).

#### #8 `POST /admin/invites/{token}/revoke`
- **Auth:** `require_admin_session`; service rejects if invite belongs to other tenant (403) or if `used_at` set (409).
- **Service:** `AdminInviteService.revoke(token, actor_id)` → `AdminInviteRepository.mark_revoked()` (sets `revoked_at` from migration 0005).
- **Audit:** `admin.invite_revoked`.
- **Response 200:** `{ok: true, revoked_at}`.

#### #9 `POST /admin/invites/{token}/resend`
- **Auth:** `require_admin_session`; reject if invite is `used` or `revoked` (409).
- **Service:** `AdminInviteService.resend(token)` — mints new UUID + extends `expires_at = now() + default_ttl`.
- **Audit:** `admin.invite_resent`.
- **Response 200:** same shape as `POST /admin/invites`.

#### #10 `PUT /cms/pages/{id}`
- **Auth:** `require_tenant_admin`; row tenant_id MUST equal JWT tenant_id.
- **Body:** `{title, slug, body, source_url, status}`; `extra=forbid`.
- **Service:** `CmsPageService.update(id, body, tenant_id)` (exists, needs route wiring).
- **Audit:** `cms.page_updated`.

#### #11 `PATCH /cms/pages/{id}/status`
- **Auth:** `require_tenant_admin`; tenant-scope enforced.
- **Body:** `{status: "draft"|"published"|"archived"}`; `extra=forbid`.
- **Service:** `CmsPageService.set_status(id, status, tenant_id)`.
- **Audit:** `cms.page_published` or `cms.page_unpublished` (new vocab entries).
- **Out of scope:** RAG re-indexing on publish (Nasser owns; route ships without the hook).

#### #12 `DELETE /cms/pages/{id}`
- **Auth:** `require_tenant_admin`; tenant-scope enforced.
- **Service:** `CmsPageService.delete(id, tenant_id)` — **soft delete** (`status=archived`, `deleted_at=now()`).
- **Audit:** `cms.page_deleted`.
- **Response 204:** empty body.

#### #13a `GET /tenants` (TM-scope, admin-JWT)
- **Auth:** `require_admin_session`, then reject if `role != "tenant_manager"`.
- **Service:** `TenantService.list_for_manager()` (new) — returns `[{id, name, slug, plan, status, created_at}]`. Distinct from legacy `POST /tenants` `get_platform_actor` path.

#### #13b `GET /audit-logs` (TM-scope, admin-JWT)
- **Auth:** `require_admin_session`, TM-only.
- **Service:** `TenantRepository.list_all_audit_logs(filters)` (new) — supports `?actor_role`, `?tenant_id`, `?action`, `?since`, `?until` query params; never exposes redacted content.

### 4.3 Mismatched Request / Response Structures

**None flagged.** Because every admin page implements the placeholder fallback uniformly, the readers already match the contract shapes shown in §4.2 — execution simply swaps the canned sample for the real JSON. The two intentional shape changes (#11 audit-vocab additions, #4 split status/assignee events) are additive and the readers ignore unknown fields.

### 4.4 Missing Loading / Error States

- **Spinner-then-toast on writes** — Settings PUT (#7), CMS edit/publish/delete (#10/#11/#12), Escalations PATCH (#4), invite revoke/resend (#8/#9), agent-config PUT (#1) all need: button disabled while inflight → success toast on 2xx → error toast on non-2xx. Currently silent in stub pages.
- **Confirm dialog on destructive actions** — CMS delete (#12), invite revoke (#8). Use `st.dialog` (Decision 15 — no real modal stack).
- **Disabled-while-saving** — Escalations PATCH list (#4) currently allows multi-row click-through; needs row-level inflight tracking.

### 4.5 Pagination / Filtering / Caching

- **Pagination** — `GET /leads` and `GET /tenants/{id}/audit-logs` and `GET /audit-logs` (#13b) — add cursor pagination if list > 200 (currently `limit: int` query param, no cursor). Deferred to follow-on if not in 2A.
- **Filtering** — `#13b` audit-log feed supports the 5 query params listed above; UI passes through Streamlit form widgets.
- **Caching** — None planned. Streamlit reruns are cheap; widget makes 1–2 backend calls per panel-open.

### 4.6 Bottlenecks

- Streamlit reruns the full page on every interaction; mitigated because the `(placeholder)` fallback makes non-2xx cheap. Theme designer (`widget_page.py:269-385`) is the canonical "no backend call until Save" pattern — replicate for any new editor-style page.
- Widget chat round-trip latency dominated by the stub agent path (deterministic — fast) and the lexical RAG (also fast). Real classifier + agent will add ONNX + LLM latency — out of scope, but the placeholder for `(_, ok)` collapse will need adapting once `route_message_decision` becomes the real classifier.

---

## §5 Missing Backend Work (Scoped List)

Strict scope: demo + integration only. Each item is one of: missing endpoint, missing DB change, missing service method, missing validation, missing test.

### 5.1 Missing Endpoints

The 13 endpoints itemized in §4.2. Implementation order recommendation: read endpoints first (#2, #3, #5, #6, #13a, #13b) then writes (#1, #4, #7, #8, #9, #10, #11, #12).

### 5.2 Missing Database Changes

- **Migration `0005_admin_invites_revoked_at.py`** — already drafted in [app/db/migrations/versions/0005_admin_invites_revoked_at.py](app/db/migrations/versions/0005_admin_invites_revoked_at.py); verify alembic upgrade/downgrade works clean.
- **Migration `0006_tenant_settings.py`** — already drafted in [app/db/migrations/versions/0006_tenant_settings.py](app/db/migrations/versions/0006_tenant_settings.py); verify RLS policy + tenant_id FK + idempotent backfill.
- **No new tables required.** `escalation_tickets` (already in 0004) graduates from unused to written-to via #4.

### 5.3 Missing Audit-Log Vocabulary

New entries for [CONTRACT.md](CONTRACT.md) §730–743:

- `tenant.agent_config_updated`
- `tenant.settings_updated`
- `cms.page_published`, `cms.page_unpublished`
- `escalation.created`, `escalation.status_changed`, `escalation.assignee_changed`
- `admin.invite_revoked`, `admin.invite_resent`

All must follow the existing redaction-on-metadata pattern (`TenantRepository.add_audit_log`).

### 5.4 Missing Service Methods

| Service | New / changed methods |
|---|---|
| `AdminInviteService` | `revoke(token, actor_id)`, `resend(token)` |
| `AgentConfigService` | `get(tenant_id)`, `put(tenant_id, body, actor_id)` — implement from the dead stub |
| `PlatformGuardrailsService` | `read(tenant_id)` |
| `EscalationService` | route `patch(ticket_id, body, actor_id)` to emit *separate* audit events per delta |
| `TenantService` | `list_for_manager()` |
| `TenantSettingsService` | route wiring; methods already exist |
| `CmsPageService` | route wiring; methods already exist |
| `TenantRepository` | `list_all_audit_logs(filters)` |
| `AdminUserRepository` | `list_by_tenant(tenant_id)` |
| `AdminInviteRepository` | `mark_revoked(token, actor_id)` |
| `AgentConfigRepository` | `get_by_tenant(tenant_id)`, `upsert(tenant_id, body)` |
| `EscalationRepository` | `create(tenant_id, conversation_id, reason)` (so the `escalate` tool can graduate from synthetic to real — needed for #4 to have rows to PATCH) |

### 5.5 Missing Validation

- Every new request body MUST use Pydantic `model_config = ConfigDict(extra="forbid")` so `tenant_id`, `actor_id`, `role` cannot be smuggled.
- `chips` length 0..6, each chip 1..40 chars (#1).
- `assignee_id` cross-tenant check at the service layer, not just FK constraint (#4) — returns 422.
- `status` enum validation on CMS / escalation patches.
- Theme key allowlist (already in widget UI) mirrored server-side for #1 if `theme_json` exposed there.

### 5.6 Missing Auth Logic

All new endpoints map to existing deps. **No new auth surface is added.**

- `require_tenant_admin`: #1, #2 (TA path), #3, #10, #11, #12.
- `require_admin_session`: #4, #5, #6, #7 (then role-gate to TM), #8, #9, #13a (then role-gate to TM), #13b (then role-gate to TM).
- `get_tenant_id_from_widget_token`: #2 (widget path — same response shape, served behind the same route by checking which dep resolves successfully).
- Cross-tenant rejection MUST emit the same 403 byte body as existing routes (Decision 4 refusal symmetry).

### 5.7 Missing Security

- Rate limit `PUT /widgets/config`, `PUT /tenants/{tid}/agent-config`, `PUT /tenants/{tid}/settings`, `PATCH /cms/pages/{id}/status` — reuse `RateLimiterService` per-tenant bucket (no new bucket type). Default: 60 writes/minute/tenant.
- All persisted free-text fields (CMS `body`, agent-config `business_rules`, settings) pass through `app/infra/redaction.py` before write.
- No new secrets — all signing keys remain in Vault.
- TM endpoints (#7, #13a, #13b) MUST 403 with byte-uniform body for non-TM JWTs.

### 5.8 Missing Tests

For each new endpoint:

- `tests/integration/test_{endpoint}.py` — happy path (200), cross-tenant 403, invalid body 422, unauthorized 401.
- `tests/integration/test_admin_{page}.py` — Streamlit AppTest pattern (existing `_admin_*_page_entry.py` shims).
- One new probe in [tests/smoke/test_cross_tenant_e2e.py](tests/smoke/test_cross_tenant_e2e.py) per **write** endpoint (#4, #7, #8, #9, #10, #11, #12, #1) — verifies cross-tenant rejection in the real Compose stack.
- Audit-log assertion test per write endpoint — verifies the new vocab entries from §5.3 land in `audit_logs` with redacted metadata.

### 5.10 Agent + Tools + Memory + Prompts (Track 2)

Production-shape upgrades to the chat path. No new endpoints; all work is internal to `POST /chat` and `app/agent/` / `app/prompts/`.

#### 5.10.1 Router — real classifier with confidence threshold

- Replace lexical stub in [app/agent/router.py](app/agent/router.py) with a call to `app/infra/modelserver.py` `/predict`.
- Modelserver returns `{label, confidence}` where `label ∈ {spam, faq, sales_or_contact, human_request, ambiguous}`.
- New `RouteDecision` shape: `{route, reason, confidence}`. Decision rule:
  - `confidence ≥ ROUTER_CONFIDENCE_THRESHOLD` (default `0.70`, configurable via env) → workflow path for the predicted label.
  - `confidence < threshold` OR `label == "ambiguous"` → **agent path** (this is the load-bearing handoff per blueprint).
  - `label == "spam"` → blocked regardless of confidence (already-locked platform behavior).
- Service-auth Bearer token to modelserver already in place ([app/infra/modelserver.py](app/infra/modelserver.py)).
- Fail-soft: modelserver 5xx / timeout → fall back to agent path (never silent-route to a destructive tool).

#### 5.10.2 Agent — single tool-calling LLM, bounded

- Replace deterministic plan in [app/agent/agent.py](app/agent/agent.py) with a real LLM tool-calling loop (provider-agnostic; default to Anthropic Claude via `anthropic` SDK or OpenAI function-calling — chosen in research phase of the new feature).
- Tool allowlist (hard-coded, no tenant override): exactly `{rag_search, capture_lead, escalate}`. Blueprint floor: **the agent must genuinely handle multi-tool, ambiguous turns, not just sit behind the router as dead weight.**
- Loop bounds (constants in [app/agent/agent.py](app/agent/agent.py), already declared):
  - `MAX_AGENT_ITERATIONS = 5` — hard cap on tool-call iterations.
  - `MAX_AGENT_TOKENS_PER_TURN = 4000` — hard cap on cumulative tokens (input + output) per visitor turn.
- On cap hit: agent halts, returns `"I'm not able to help with that right now — I've escalated this so a human can follow up."`, calls `escalate` once, emits `agent.iteration_cap_hit` audit log. **No silent loop continuation.**
- `tenant_id` passed only from `ChatService` (which got it from the widget JWT). Tool argument schemas MUST NOT include `tenant_id`. Any LLM-generated argument that includes `tenant_id` is dropped before the tool call.
- LLM prompt assembled from: platform-locked system prompt + tenant persona block ([app/prompts/](app/prompts/), see §5.10.5) + tool schemas (OpenAI-style JSON Schema) + redacted recent memory (last 12 messages from Redis).
- Agent observability: emit `agent.turn_started`, `agent.tool_called`, `agent.turn_completed`, `agent.iteration_cap_hit`, `agent.token_cap_hit` to audit log (no message content — only metadata: tool name, iteration count, token count).

#### 5.10.3 `rag_search` — unchanged retrieval, hardened invariants

- Retrieval stays lexical in this feature (pgvector ANN is N1 follow-on).
- Pydantic tool-arg schema: `RagSearchArgs(query: str, top_k: int = 5)` with `extra=forbid`; `top_k` clamped to 1..10.
- Tenant scoping: existing `WHERE cms_pages.tenant_id = :tenant_id` plus RLS session var set via `TenantRepository._tenant_context()`.
- Citations returned in `ChatResponse.citations`; widget already renders them ([Message.tsx:41-79](frontend/widget/src/components/Message.tsx#L41-L79)).

#### 5.10.4 `capture_lead` — schema, per-session rate limit, tenant-locked

Blueprint quote: *"`capture_lead` is an unauthenticated, LLM-triggered write. Schema-validate the payload, rate-limit writes per visitor/session, and scope the write to the token's tenant."*

- Pydantic tool-arg schema (`extra=forbid`):
  ```
  CaptureLeadArgs(
    name: str | None = None,        # 1..200 chars when present
    contact: str  | None = None,    # email OR phone, validated by regex
    intent: str   = ...,            # 1..1000 chars
  )
  ```
  No `tenant_id`, no `session_id`, no `actor_id`, no `status` — server-supplied only.
- **Per-session rate limit**: new bucket type in `RateLimiterService` keyed `lead:{tenant_id}:{session_id}`, default `5 writes / session / hour`. Configurable per tenant via `tenant_settings.rate_limit_lead_per_session` (extends migration 0006 schema by one column — minor additive change). On cap: tool returns `{status: "rate_limited"}`, agent surfaces a friendly "I've already captured your details — the team will reach out shortly" message, audit `lead.rate_limited`.
- Tenant scoping: `LeadRepository.create()` writes `tenant_id` from `ChatService.handle_message`'s trusted parameter only. Any LLM-supplied `tenant_id` is silently dropped at the Pydantic boundary because the schema forbids the field.
- `intent` redacted via `app/infra/redaction.py` before persist (already implemented; verify still in path).
- Audit: `lead.captured` (already in vocabulary).

#### 5.10.5 `escalate` — real DB write, graduates from synthetic

- Implement `EscalationRepository.create(tenant_id, conversation_id, reason)` against the existing `escalation_tickets` table (migration 0004).
- `escalate` tool returns `{status: "escalated", ticket_id: <real_uuid>, ...}` — wire-compatible with widget reader.
- Audit: new `escalation.created` vocab entry.
- Per-session rate limit: 1 escalation per session (prevents agent + visitor from spamming tickets via prompt injection). Subsequent attempts return the existing ticket_id.
- Defense-in-depth: cross-tenant assertion at INSERT (`tenant_id == ChatService trusted tenant_id`).

#### 5.10.6 Memory — Redis with justified TTL

- Key: `session:{tenant_id}:{session_id}` (already correct).
- TTL: **1800 seconds (30 minutes)**. Justification documented in [DECISIONS.md](DECISIONS.md) addendum to the existing Memory decision: long enough for a typical browsing session ("read 2 CMS pages, ask 3 follow-ups") to retain context; short enough that an anonymous visitor's chat is not stored beyond the immediate purpose. **Privacy posture:** anonymous chat is operational data with a fixed retention window, not durable customer data — visitor never logged in, never identifiable in memory after TTL.
- Max messages per session: 12 (existing). Older messages dropped FIFO before TTL hits.
- Memory writes use `redact_text` before persisting (already in [app/services/chat_service.py:55,81](app/services/chat_service.py#L55) ).
- Fail-soft: Redis unavailable → chat continues without memory; emits `memory.unavailable` once per session.

#### 5.10.7 Prompts — version-controlled, tenant persona injected at runtime

Blueprint quote: *"Prompts live in prompts/, version-controlled. Tenant persona is injected at runtime from config — never hardcoded."*

- Existing: [app/prompts/system_prompt.md](app/prompts/system_prompt.md) — single file. Keep file path stable for diff history.
- Split into structured sections at load time (still one file, parsed into named blocks):
  - `PLATFORM_SYSTEM` — locked platform guardrails / refusal patterns / tool descriptions. **Tenant cannot override.**
  - `TENANT_PERSONA` placeholder — replaced at runtime with `tenant_agent_configs.persona_name + tone + business_rules` from #1/#2.
  - `TOOL_SCHEMAS` — generated from Pydantic models at startup (single source of truth).
- New `app/prompts/loader.py` (≤ 80 lines): reads `system_prompt.md`, fetches tenant agent config (cached per request), produces the final prompt string. Cache invalidated when `PUT /tenants/{tid}/agent-config` (#1) lands.
- Prompt diff history: every change to [app/prompts/system_prompt.md](app/prompts/system_prompt.md) ships in a PR with a `prompt-change` label; CI runs the agent-tool eval (`evals/agent_tool.py`) against the new prompt and refuses to merge if tool-selection accuracy drops below the existing threshold (`agent_tool_selection.accuracy_min` in [eval_thresholds.yaml](eval_thresholds.yaml)).

#### 5.10.8 New audit-log vocabulary (Track 2)

- `agent.turn_started`, `agent.turn_completed`, `agent.tool_called`, `agent.iteration_cap_hit`, `agent.token_cap_hit`
- `escalation.created`
- `lead.rate_limited`, `memory.unavailable`

All metadata fields redacted before persist; no message content stored.

#### 5.10.9 Tests for Track 2

- `tests/unit/test_router.py` — confidence-threshold routing (covers high-conf workflow, low-conf → agent, ambiguous → agent, spam → blocked, modelserver-down → agent fallback).
- `tests/unit/test_agent_loop.py` — loop bounds: stops at iteration 5, stops at token 4000, escalates on cap-hit.
- `tests/unit/test_tool_schemas.py` — Pydantic `extra=forbid` strips LLM-supplied `tenant_id` / `session_id`.
- `tests/integration/test_capture_lead_rate_limit.py` — 5 writes succeed, 6th returns `rate_limited`, audit log captured.
- `tests/integration/test_escalate_real_ticket.py` — real `escalation_tickets` row created; appears in `GET /escalations` (#5).
- `tests/security/test_agent_prompt_injection.py` — adversarial prompts in `intent` field cannot mutate `tenant_id`, cannot bypass tool allowlist, cannot exceed loop bounds.
- `evals/agent_tool.py` — graduate from mock to real evaluator (matches BLOCKED.md N6).

### 5.11 Explicitly Out of Scope (do not re-litigate)

| Item | Owner | Tracked under |
|---|---|---|
| RAG pgvector similarity (`rag_chunks` writes + ANN query) — lexical baseline ships | Nasser | N1 |
| Chat `messages` table durable persistence — Redis short-term memory is the surface | Nasser | N2 |
| Observability `traces` table writes | Ayoub | A5-adjacent |
| Background job runner (RQ / Celery / APScheduler) | — | not assigned |
| WebSocket / SSE realtime for escalations/leads | — | explicitly rejected in scope-lock |
| Widget telemetry implementation (currently no-op stub) | Amer | post-009 |
| Erasure walk-through impl | Hiba | H9 |
| RAG re-index hook on CMS publish/delete (#11/#12) | Nasser | N1 |

---

## §6 Improvements and Refactors

Bounded to ergonomic wins inside the retrofit. None of these block endpoint delivery — they land **after** §5 is done.

1. **Delete dead stubs:**
   - `app/services/cms_service.py` (functionality lives in `cms_pages.py`).
   - `app/services/admin_settings.py` (replaced by `tenant_settings.py`).
2. **Fix type bug:** [app/services/chat_service.py:48](app/services/chat_service.py#L48) — `tenant_id: int` → `tenant_id: UUID`.
3. **Fix dead return:** [app/api/deps.py:91](app/api/deps.py#L91) — remove `return 1` after `return TenantService(repo)`.
4. **Promote placeholder helper:** move `_PLACEHOLDER = "—"` + `(placeholder)` caption into [admin/_admin_http.py](admin/_admin_http.py) as `render_placeholder_caption()` so new pages don't duplicate it.
5. **Typed admin API client:** wrap `_admin_http.http_client()` returns in Pydantic response models so admin pages stop dict-accessing untyped JSON. Optional, low-risk.
6. **OpenAPI → TypeScript types:** add `openapi-typescript` build step in [frontend/widget/](frontend/widget/) so `api.ts` request/response types are generated from the FastAPI OpenAPI doc. Eliminates the `parseAgentConfig` defensive-parse drift risk.
7. **Externalize widget defaults:** replace `AGENT_CONFIG_PLACEHOLDER` ([api.ts:143-147](frontend/widget/src/api.ts#L143-L147)) with a fetch of `/widget/defaults.json` shipped from the loader container — keeps i18n out of the JS bundle.
8. **Lint guardrail:** add a ruff rule banning new imports of `cms_service` / `admin_settings` so the dead stubs stay dead after step 1.

---

## §7 SpecKit `/speckit-specify` prompt

Paste verbatim into a fresh branch (suggested: `010-frontend-backend-integration`).

````
/speckit-specify

Title: Concierge frontend / backend integration retrofit

Context: The Concierge codebase ships ~90% of the Concierge_Backend_Blueprint.md
target. Thirteen endpoints from specs/009-concierge-ui/contracts/missing-endpoints.md
are not yet routed; the corresponding admin pages render `(placeholder)` fallbacks.
This feature closes those gaps and wires the existing UI surfaces to live data
without rebuilding any shipped subsystem.

LOAD-BEARING RULE: The frontend NEVER decides tenant identity or role. Tenant_id
and role come only from the server-issued JWT response. No request body may
carry tenant_id, role, or actor_id; every body uses Pydantic extra=forbid.

Architecture requirements (RETROFIT, not rebuild):
- Stack unchanged: FastAPI async, Postgres + pgvector, Redis, Vault, Streamlit
  admin, React iframe widget, lean ONNX modelserver, guardrails sidecar.
- No new compose service. Lean-image audit (Decision 11) must continue to pass.
- Layered architecture preserved: routes → schemas/domain → services →
  repositories → infra. No new layer.

Frontend requirements:
- Render real data on the 9 tenant_admin tabs, 6 tenant_manager tabs, and the
  widget panel by consuming the 13 new endpoints.
- Remove every `(placeholder)` caption whose endpoint becomes live; keep the
  fallback path as a transport-failure safety net only.
- Widget: token stays in module-scope memory (Constitution Principle IV);
  greeting + chips come from GET /tenants/{tid}/agent-config; hardcoded
  English defaults remain only as fail-soft fallback on 404/501/transport.
- Admin: every save uses spinner-disabled-button → success toast → error toast.
  Destructive actions (CMS delete, invite revoke) gated by st.dialog confirm.
- No mobile admin — 1280px desktop ceiling (Decision 15).
- Widget retains bubble launcher + mobile sheet < 640px + ESC + focus trap +
  reduced-motion (US4 a11y baseline).

Backend requirements:
- Ship 13 endpoints per the §4.2 contract in backend-spec.md.
- Every write emits an audit-log entry; new vocab additions are:
  tenant.agent_config_updated, tenant.settings_updated, cms.page_published,
  cms.page_unpublished, escalation.created, escalation.status_changed,
  escalation.assignee_changed, admin.invite_revoked, admin.invite_resent.
- escalation_tickets table (already in migration 0004) starts receiving real
  INSERTs — the synthetic-ticket path in the escalate tool graduates to a real
  EscalationRepository.create().

API requirements:
- Bearer JWT on every admin route. Widget routes use the existing
  get_tenant_id_from_widget_token dep.
- Every request body has Pydantic ConfigDict(extra="forbid").
- Cross-tenant rejection returns a byte-uniform 403; TM-only routes return a
  byte-uniform 403 for tenant_admin JWTs (Decision 4 refusal symmetry).
- All response shapes match specs/009-concierge-ui/contracts/missing-endpoints.md
  exactly.

Database requirements:
- Only migrations 0005 (admin_invites.revoked_at) and 0006 (tenant_settings)
  are applied. No new tables introduced.
- All existing RLS policies preserved. New routes either set
  app.tenant_id via the TenantRepository._tenant_context() pattern or rely
  on explicit WHERE tenant_id = :tenant_id (defense in depth).
- No code writes to rag_chunks, messages, or traces in this feature.

Authentication requirements:
- Reuse existing deps: require_admin_session (TA + TM), require_tenant_admin
  (TA-only), get_tenant_id_from_widget_token (widget).
- No new dev-header surfaces. Dev-headers remain gated by CONCIERGE_ENV=dev.
- No localStorage / sessionStorage / cookies for any credential.

State management requirements:
- Streamlit auth_state (admin/auth_state.py) unchanged: admin_token,
  admin_actor_id, admin_tenant_id, admin_role, admin_full_name.
- Widget reducer (useChatReducer.ts) unchanged — the 13 endpoints feed
  read-only data, not new dispatched actions.
- New pages adopt the draft-state pattern from widget_page.py:176-194:
  *_saved (server snapshot) + *_draft (working copy) + dirty indicator.

Error handling requirements:
- Reads: single fallback path collapses non-2xx / missing-field / transport
  to one `(placeholder)` rendering (Decision 8).
- Writes: spinner-disabled-button → success toast on 2xx → friendly error
  toast on non-2xx. No raw server text surfaced.
- 401 byte-uniform per failure class. 403 byte-uniform per failure class.

Responsiveness and accessibility:
- Admin: ≥ 1280 px desktop only.
- Widget: bubble launcher at all sizes; full-screen sheet under 640 px;
  ESC closes panel + returns focus to bubble; reduced-motion respected;
  axe-core scan (frontend/widget/src/__tests__/axe.test.tsx) reports zero
  serious/critical violations open AND closed.

Performance requirements:
- Loading indicator visible within 200 ms on every fetch (SC-001).
- PUT/PATCH/DELETE buttons disable while inflight.
- No new caching layer. Streamlit reruns are the model.

Security requirements:
- Every new write route gated by an existing role-checking dep.
- Every persisted free-text field (CMS body, business_rules, settings)
  routed through app/infra/redaction.py before write.
- Rate limit on writes: 60 writes/minute/tenant via existing
  RateLimiterService (no new bucket type).
- No new secrets. WIDGET_JWT_SECRET / ADMIN_JWT_SECRET remain Vault-resolved.

Agent / router / tools / memory / prompts requirements (Track 2):
- Router: real ONNX classifier via modelserver /predict; emits (label,
  confidence). High-confidence label → workflow. Low confidence OR ambiguous
  label → agent (this is the load-bearing handoff per blueprint).
- Agent: single tool-calling LLM (NOT a fixed graph). Tool allowlist hard-coded:
  {rag_search, capture_lead, escalate}. Loop bounds: 5 iterations, 4000 tokens
  per turn. On cap, escalate + emit audit; never silent-loop.
- tenant_id passed only from ChatService (sourced from widget JWT). Pydantic
  tool-arg schemas extra=forbid; LLM-supplied tenant_id is dropped at the
  boundary, never trusted.
- rag_search: lexical baseline; pgvector explicitly deferred.
- capture_lead: Pydantic schema validation; per-session rate limit (default
  5/hour/session); tenant_id from trusted context only; intent redacted before
  persist.
- escalate: real INSERT into escalation_tickets (table already in 0004);
  ticket_id propagated to ChatResponse and visible in #4/#5; 1 escalation per
  session; cross-tenant assertion at INSERT.
- Redis memory: session:{tenant_id}:{session_id}, TTL 1800 s; ≤ 12 messages;
  redacted before store; fail-soft.
- Prompts: app/prompts/system_prompt.md remains source of truth; parsed into
  PLATFORM_SYSTEM (locked) + TENANT_PERSONA placeholder + TOOL_SCHEMAS. Tenant
  persona injected at runtime from tenant_agent_configs via #1/#2 — never
  hardcoded per tenant. CI agent-tool eval gates every prompt change.

Realtime / integration requirements:
- NO WebSockets, NO SSE. Polling-only model.
- Widget chat round-trip remains synchronous request/response.
- Admin pages reflect new data on next Streamlit rerun (user-initiated).

Deployment requirements:
- Same docker-compose.yml topology. No new container.
- Lean-image audit (modelserver, guardrails) must remain green.
- Smoke E2E (tests/smoke/test_cross_tenant_e2e.py) must remain green; one
  new probe per write endpoint added.
- All CI eval gates (classifier, rag, agent-tool, red-team, redaction) must
  remain green — this feature does not touch the agent / classifier path.

Success criteria:
- All 13 endpoints live; matching admin pages render real data.
- Zero `(placeholder)` captions visible when the api container is healthy.
- Cross-tenant probe (forged JWT) returns byte-uniform 403 on every new route.
- No regression in existing live routes.
````

---

## §8 SpecKit `/speckit-plan` prompt

Paste verbatim after `/speckit-specify` produces `spec.md`.

````
/speckit-plan

Plan the implementation of feature 010-frontend-backend-integration per the
spec.md produced by /speckit-specify. Constraints:

- Retrofit only. No rewrite of any shipped subsystem.
- Out of scope: agent loop, message DB persistence, RAG pgvector, traces
  writes, background jobs, WebSockets/SSE. Each is owned per BLOCKED.md and
  must stay untouched in this feature.

PHASES (in order):

Phase A — DB migrations (1 PR)
  - A1. Verify 0005_admin_invites_revoked_at.py upgrade/downgrade clean
        against the seeded demo DB; add a unit test in
        tests/unit/test_migrations.py.
  - A2. Verify 0006_tenant_settings.py: RLS policy enabled, tenant_id FK,
        backfill safe for an already-populated DB; add a unit test.
  - A3. Add one column to tenant_settings: rate_limit_lead_per_session INT
        DEFAULT 5 (needed by Phase B2 capture_lead bucket).

Phase B — Backend endpoints — Track 1 (≈ 4 PRs grouped by ownership domain)
  B1. Read endpoints first: #2, #3, #5, #6, #13a, #13b.
      Note: #4 PATCH /escalations/{id} depends on Track-2 escalate-tool real
      INSERT (Phase B2) producing rows to operate on. Order: ship Phase B2
      first so #4 has data.
  B2. Track-2 prerequisite: EscalationRepository.create() lands here so the
      escalate tool can produce real escalation_tickets rows. Audit-log
      vocab entry escalation.created added.
  B3. Write endpoints by domain:
      - Agent + guardrails: #1, #3 (PUT side). #1/#2 land BEFORE Phase B'
        because the agent prompt-loader depends on tenant_agent_configs.
      - Escalations + admin-users: #4 (now has rows from B2).
      - Invites: #8, #9.
      - CMS edits: #10, #11, #12 (#11/#12 ship without RAG re-index hook).
      - Settings: #7.
  Per-endpoint task triplet:
      (a) route in app/api/routes/*.py with Pydantic extra=forbid body.
      (b) service method in app/services/*.py (most exist; some need wiring).
      (c) repo method in app/repositories/*.py with tenant_id scoping.
      (d) audit-log call via TenantRepository.add_audit_log with new vocab
          entry (cms.page_published, escalation.status_changed, etc.).
      (e) integration test: happy + 403 cross-tenant + 422 invalid body + 401.

Phase B' — Agent + tools + memory + prompts — Track 2 (≈ 3 PRs)
  Ships only after Phase A (migrations) and Phase B endpoints #1/#2 land
  (the agent prompt-loader reads tenant_agent_configs via #2).

  B'1. Router upgrade (1 PR)
      - Replace lexical stub in app/agent/router.py with a real call to
        app/infra/modelserver.py /predict.
      - Return RouteDecision(route, reason, confidence).
      - Decision rule: confidence ≥ ROUTER_CONFIDENCE_THRESHOLD (default 0.70,
        env-tunable) → workflow; else OR label=="ambiguous" → agent;
        spam → blocked always.
      - Fail-soft: modelserver 5xx/timeout → agent path.
      - Tests: tests/unit/test_router.py covers each branch + fail-soft.

  B'2. Tool hardening + escalate real DB write (1 PR)
      - app/agent/tools.py:
          * RagSearchArgs / CaptureLeadArgs / EscalateArgs Pydantic schemas
            with extra=forbid; clamp top_k 1..10; intent ≤ 1000 chars.
          * Drop any LLM-supplied tenant_id/session_id/actor_id BEFORE the
            tool function executes (Pydantic boundary).
          * capture_lead: new bucket in RateLimiterService keyed
            lead:{tenant_id}:{session_id}, default 5/hour/session, configurable
            via tenant_settings.rate_limit_lead_per_session (Phase A3 column).
            On cap → {status: "rate_limited"} + lead.rate_limited audit.
          * escalate: real EscalationRepository.create() insert with
            escalation.created audit; 1 escalation per session; subsequent
            calls return the existing ticket_id.
      - Tests:
          * tests/unit/test_tool_schemas.py
          * tests/integration/test_capture_lead_rate_limit.py
          * tests/integration/test_escalate_real_ticket.py
          * tests/security/test_agent_prompt_injection.py
            (adversarial intent cannot mutate tenant_id / bypass allowlist /
            exceed loop bounds).

  B'3. Real LLM agent loop + prompts (1 PR)
      - Choose LLM provider in /speckit-clarify (recommend Anthropic Claude
        via anthropic SDK; OpenAI function-calling as fallback) — record in
        DECISIONS.md.
      - Replace deterministic plan in app/agent/agent.py with a real
        tool-calling loop. Hard caps:
          MAX_AGENT_ITERATIONS = 5
          MAX_AGENT_TOKENS_PER_TURN = 4000
        On cap: halt, call escalate once, return safe message,
        emit agent.iteration_cap_hit or agent.token_cap_hit audit.
      - app/prompts/loader.py (≤ 80 lines): parse system_prompt.md into
          PLATFORM_SYSTEM (locked) + TENANT_PERSONA placeholder +
          TOOL_SCHEMAS (generated from Pydantic models at startup).
        Inject tenant_agent_configs (persona_name, tone, business_rules) at
        runtime via #2. Cache invalidated when #1 fires.
      - Agent emits: agent.turn_started, agent.tool_called,
        agent.turn_completed, agent.iteration_cap_hit, agent.token_cap_hit.
      - evals/agent_tool.py: graduate from mock (BLOCKED.md N6) to real
        evaluator running the golden set against the live agent path.
      - Tests:
          * tests/unit/test_agent_loop.py — 5-iteration cap, 4000-token cap,
            escalate-on-cap path.
          * tests/integration/test_chat_agent_path.py — ambiguous-message
            turn reaches agent, multi-tool sequence completes, citations +
            ticket_id propagate.

Phase C — Frontend wiring (≈ 3 PRs grouped by page family)
  For each of 10 affected pages:
      (a) Replace canned sample dict with `_get_json` against the new endpoint.
      (b) Remove the `(placeholder)` caption gating once endpoint is wired.
      (c) Add spinner-disabled-button + success/error toast on writes.
      (d) Add st.dialog confirm on destructive actions (#8 revoke, #12 delete).
      (e) Streamlit AppTest in tests/integration/test_admin_{page}.py.
  Special:
      - frontend/widget/src/api.ts: keep AGENT_CONFIG_PLACEHOLDER as fail-soft
        fallback only; do not remove. Fetch from #2 normally.
      - frontend/widget — no other widget changes in this feature.

Phase D — Cross-tenant smoke + flag flip (1 PR)
  - D1. Add 8 new probes (one per write endpoint) to
        tests/smoke/test_cross_tenant_e2e.py with `@require_full_stack`
        decoration where they depend on the agent path (none should, since
        we only test cross-tenant 403 on direct REST calls).
  - D2. Inspect which existing xfailed probes flip to passing because of
        Phase B work; flip SMOKE_E2E_REQUIRE_FULL_STACK in
        .github/workflows/ci.yml from "0" to "1" when appropriate.

Phase E — Refactor + cleanup (1 PR, optional, post-merge of A-D)
  - E1. Delete app/services/cms_service.py + app/services/admin_settings.py.
  - E2. Fix chat_service.py:48 (UUID instead of int).
  - E3. Remove dead `return 1` at deps.py:91.
  - E4. Promote `_PLACEHOLDER` + `(placeholder)` caption helper to
        admin/_admin_http.py.
  - E5. Add openapi-typescript build step in frontend/widget/.
  - E6. Externalize widget defaults to /widget/defaults.json.
  - E7. Add ruff rule banning new cms_service / admin_settings imports.

API implementation order (within Phase B):
  Reads before writes. Agent-config (#1, #2) before guardrails (#3) because
  chips depend on agent_config presence; #1/#2 also gate Phase B' agent
  prompt loader. Escalations (#4, #5) require EscalationRepository.create() —
  land that first (Phase B2) so PATCH has rows to operate on. CMS writes
  (#10, #11, #12) ship without RAG re-index hook — the indexing hook is a
  separate Nasser feature, tracked under N1.

Cross-track dependency: Phase B' (agent + tools) depends on
  - Phase A3 (rate_limit_lead_per_session column),
  - Phase B endpoints #1 + #2 (tenant_agent_configs read/write for the
    prompt loader),
  - Phase B2 (EscalationRepository.create() for the escalate tool).
  Land in that order; Phase B' PRs ship after.

Migration order:
  0005 first (revoke column needed for #8 service method).
  0006 second (tenant_settings table needed for #7).
  A3 (single ADD COLUMN — bundled with 0006 or shipped as 0007).

Testing strategy:
  - Unit: bcrypt / JWT / Pydantic validators per new schema; Phase B' router
    confidence-threshold branches; Phase B' agent loop caps; tool-arg schema
    extra=forbid stripping.
  - Integration (per endpoint): happy + 403 cross-tenant + 422 invalid body
    + 401 missing auth. Use existing tests/integration/conftest.py fixtures.
  - Streamlit AppTest (per page): wired endpoint renders real rows; placeholder
    fallback still triggers on simulated 5xx.
  - Smoke (per write endpoint): cross-tenant 403 via forged JWT in the real
    Compose stack.
  - Track-2 integration: tests/integration/test_chat_agent_path.py covers
    ambiguous-message → agent → multi-tool sequence; capture_lead rate-limit
    test; escalate real-ticket test; prompt-injection security test
    (tests/security/test_agent_prompt_injection.py).
  - Track-2 evals: evals/agent_tool.py graduates from mock to real evaluator
    (closes BLOCKED.md N6); evals/rag.py stays mock (deferred under N5/N7).
  - No widget UI test changes (widget reducer untouched).

Deployment strategy:
  - 1 PR per phase; Phase B may need 2–3 sub-PRs grouped by domain.
  - All phases land behind CONCIERGE_ENV=dev verification first (run
    docker compose up locally, walk RUNBOOK.md §Demo Flow steps 1–7).
  - lean-image-audit + smoke-e2e + all 5 eval gates must stay green on every
    PR. No required-check edits in CI.
  - No new env vars added.

Validation checkpoints:
  - After Phase A: alembic upgrade head + downgrade base + upgrade head, clean.
  - After Phase B: pytest tests/integration -k "endpoint" all green;
    check_threshold.py for every eval gate still green.
  - After Phase C: manually walk RUNBOOK.md §Demo Flow steps 1–9 — no
    `(placeholder)` captions visible against a healthy stack.
  - After Phase D: any XPASS(strict) failure means flip the smoke flag.
  - After Phase E: ruff + mypy + pytest full suite green.

Risks and mitigations:
  - Risk: auth bypass via dev-header in non-dev.
    Mitigation: existing CONCIERGE_ENV=dev guard at deps.py:142,195 — confirm
    no new dev-header surface is added.
  - Risk: cross-tenant leak via missing WHERE in a new repo method.
    Mitigation: every new repo method takes tenant_id explicit + relies on RLS
    as defense in depth. Integration test asserts 403 on cross-tenant.
  - Risk: placeholder UX regression — page goes blank instead of falling back.
    Mitigation: keep the fallback path; only swap render branch on 2xx.
  - Risk: audit-log vocabulary additions land out of CONTRACT.md sync.
    Mitigation: update CONTRACT.md §730–743 in the same PR as the route that
    emits each new action.
  - Risk: escalate tool DB write breaks the existing chat path.
    Mitigation: EscalationRepository.create() is additive; the synthetic
    ticket_id payload shape is preserved on the wire so the widget reader
    is unaffected.
  - Risk (Track 2): prompt injection turns capture_lead into a spam cannon
    or shifts the write into another tenant's table.
    Mitigation: Pydantic extra=forbid strips LLM-supplied tenant_id;
    capture_lead bucket caps writes at 5/session/hour; intent redacted;
    LeadRepository.create takes tenant_id only from ChatService trusted
    parameter, never from tool args. Adversarial test in
    tests/security/test_agent_prompt_injection.py.
  - Risk (Track 2): hostile visitor forces long tool-call chains that drive
    up cost.
    Mitigation: MAX_AGENT_ITERATIONS=5 + MAX_AGENT_TOKENS_PER_TURN=4000 hard
    caps in app/agent/agent.py; cap-hit emits audit and ends the turn with
    a single escalate call. Unit test covers both caps.
  - Risk (Track 2): silent prompt drift — a system_prompt.md edit changes
    tool-selection behavior without anyone noticing.
    Mitigation: every prompt change runs evals/agent_tool.py in CI against
    the agent_tool_selection.accuracy_min threshold; PR is blocked if it
    drops below the floor.
  - Risk (Track 2): modelserver outage silently routes every turn to the
    agent (cost spike).
    Mitigation: monitor agent.turn_started audit-log rate; alert on >50%
    of turns reaching agent (baseline is "ambiguous" share, typically <15%).

Refactor strategy:
  Refactors in Phase E land AFTER all endpoints and pages ship. No refactor
  is on the critical path to unblock a UI surface. Phase E may be deferred
  to a separate cleanup feature if scope is tight.

Done definition:
  - All 13 endpoints respond with the contract shape in §4.2.
  - Zero `(placeholder)` captions in a healthy stack.
  - Cross-tenant probe (forged JWT) rejected uniformly on every new route.
  - 8 Track-1 + 8 Track-2 new audit-log vocab entries appear in the
    audit_logs table during the demo walk.
  - Track 2: a turn with high-confidence FAQ goes through workflow path;
    a turn with confidence < 0.70 OR label "ambiguous" reaches the agent
    and completes a multi-tool sequence (rag_search → capture_lead or
    rag_search → escalate) within the 5-iteration / 4000-token caps;
    capture_lead 6th write in a session is rate_limited; escalate produces
    a real escalation_tickets row visible in #4/#5; agent_tool eval
    accuracy ≥ threshold; prompt-injection test green.
  - All CI gates green; smoke E2E flag flipped if upstream dependencies allow.
````

---

## Appendix — File:line reference index

Documents this spec leans on for accuracy:

- [Concierge_Backend_Blueprint.md](Concierge_Backend_Blueprint.md)
- [Concierge_UI_Blueprint.md](Concierge_UI_Blueprint.md)
- [CONTRACT.md](CONTRACT.md) §2.5–§2.9 + §8.1 + §730–743
- [DECISIONS.md](DECISIONS.md) — 18 numbered decisions (especially 2, 4, 8, 12, 13, 14, 15, 16, 17, 18)
- [BLOCKED.md](BLOCKED.md)
- [specs/009-concierge-ui/spec.md](specs/009-concierge-ui/spec.md)
- [specs/009-concierge-ui/plan.md](specs/009-concierge-ui/plan.md)
- [specs/009-concierge-ui/contracts/missing-endpoints.md](specs/009-concierge-ui/contracts/missing-endpoints.md)
- [specs/009-concierge-ui/data-model.md](specs/009-concierge-ui/data-model.md)
- [app/api/deps.py](app/api/deps.py) — auth deps L32-L209
- [app/db/models.py](app/db/models.py) — 724 lines, all 19 tables
- [app/db/migrations/versions/0001_hiba_platform_schema_rls.py](app/db/migrations/versions/0001_hiba_platform_schema_rls.py) through `0006_tenant_settings.py`
- [app/services/chat_service.py](app/services/chat_service.py) — stub router/agent
- [frontend/widget/src/api.ts](frontend/widget/src/api.ts) — module-scope token store
- [frontend/widget/src/state/useChatReducer.ts](frontend/widget/src/state/useChatReducer.ts) — pure reducer
- [admin/_admin_http.py](admin/_admin_http.py) — admin HTTP client
- [admin/auth_state.py](admin/auth_state.py) — Streamlit session keys
- [admin/widget_page.py](admin/widget_page.py) — draft-state pattern reference
- [app/agent/router.py](app/agent/router.py) — Track-2 router target (lexical stub today)
- [app/agent/agent.py](app/agent/agent.py) — Track-2 agent loop target (deterministic plan today; LLM tool-calling target)
- [app/agent/tools.py](app/agent/tools.py) — three-tool surface (Track-2 hardening: Pydantic schemas, per-session rate limit, escalate real INSERT)
- [app/rag/retriever.py](app/rag/retriever.py) — lexical baseline; rag_search consumes unchanged
- [app/infra/cache.py](app/infra/cache.py) — `SessionMemory` Redis client; TTL 1800 s
- [app/infra/modelserver.py](app/infra/modelserver.py) — ONNX classifier client used by Track-2 router
- [app/prompts/system_prompt.md](app/prompts/system_prompt.md) — single source of truth; Track-2 splits into PLATFORM_SYSTEM + TENANT_PERSONA + TOOL_SCHEMAS at load
- [DECISIONS.md](DECISIONS.md) §Memory + §Agent for TTL + bounded-loop justifications

**End of document.**
