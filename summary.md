# Summary of Implemented Work

This document summarizes the slice of Concierge built across this session:
the admin authentication system, the contract-compliant database schema,
the SQL widget backend, the admin read endpoints, the real eval CLIs, and
the docker-compose bootstrap chain.

Companion docs:
- [AUTH.md](AUTH.md) — auth flows and how to test each role
- [BLOCKED.md](BLOCKED.md) — closed and open handoff items
- [DECISIONS.md](DECISIONS.md) §12–14 — design rationale
- [CONTRACT.md](CONTRACT.md) — team-wide contract this work conforms to

---

## 1. What's in the box

Twelve BLOCKED.md items resolved (full or partial):

| ID | What | Status |
|----|------|:------:|
| H1 | Widget JWT verifier on `/chat` | ✅ |
| H2 | SQL `widget_configs` backend | ✅ |
| H3 | Audit logger wired to `TenantRepository.add_audit_log` | ✅ |
| H4 | Real admin session (login + JWT + role gate) | ✅ |
| H5 | `GET /tenants/{tid}/audit-logs` admin read endpoint | ✅ |
| H6 | `GET /tenants/{tid}/usage` rollup endpoint | ✅ |
| N1 | `POST /cms/pages` (RAG indexing still Nasser's lane) | ⚠ partial |
| N8 | `GET /leads` list endpoint | ✅ |
| N9 | `GET /cms/pages` real listing (replaced placeholder) | ✅ |
| A1 | Real classifier evaluator (ONNX inference, macro_f1 = 0.975) | ✅ |
| A2 | Real red-team evaluator (refusal_rate = 1.0) | ✅ |
| A3 | Real redaction evaluator (secret_leak_count = 0) | ✅ |
| A4 | `rag.mrr_min: 0.50` threshold added | ✅ |

Plus the admin invite flow (a feature on top of H4, not in BLOCKED.md),
the contract schema parity migration (CONTRACT.md §8.1), and the
docker-compose bootstrap chain.

---

## 2. Architecture

### Services (`docker-compose.yml`)

```
                    ┌──────────────┐
                    │   vault      │  (dev, in-memory)
                    └──────┬───────┘
                           │
            ┌──────────────▼────────────┐
            │     vault-seed (one-shot) │   writes app secrets
            └──────────────┬────────────┘
                           │ exit 0
            ┌──────────────▼────────────┐
            │     migrations (one-shot) │   alembic upgrade head
            └──────────────┬────────────┘
                           │ exit 0
   ┌────────┐ ┌────────┐  ┌▼──────┐ ┌──────────┐ ┌────────────┐ ┌──────┐
   │   db   │ │  redis │  │  api  │ │  admin   │ │ modelserver│ │guard │
   │ pg+vec │ │        │  │ FastAPI│ │ Streamlit│ │  (ONNX)    │ │rails │
   └────┬───┘ └────────┘  └────────┘ └────────┘ └────────────┘ └──────┘
        │
   ┌────▼─────┐
   │ pgadmin  │   pre-registered server, dev-only creds
   └──────────┘
```

Bootstrap chain (critical): `vault → vault-seed → migrations → api`. `api` uses
`depends_on: service_completed_successfully` on both one-shots, so a fresh
`docker compose up --build` produces a working stack with zero manual scripts.

### Ports

| Service | Default port |
|---------|--------------|
| api | 8000 |
| admin (Streamlit) | 8501 |
| widget (Vite dev) | 5173 |
| modelserver | 8010 |
| guardrails | 8020 |
| postgres | 5432 |
| redis | 6379 |
| vault | 8200 |
| minio | 9000 / 9001 console |
| pgadmin | 5050 |

---

## 3. Auth surfaces

Three independent auth paths — full details in [AUTH.md](AUTH.md).

| Surface | Token | Verifier | Used by |
|---------|-------|----------|---------|
| **Admin JWT** | `Authorization: Bearer <admin-jwt>` (HS256, 8 h TTL) | `require_tenant_admin` / `require_admin_session` in [app/api/deps.py](app/api/deps.py) | Streamlit admin UI, admin API clients |
| **Widget JWT** | `Authorization: Bearer <widget-jwt>` (HS256, 15 min TTL) | `get_tenant_id_from_widget_token` | Visitor browser via the embedded widget |
| **Platform-actor headers** (legacy) | `X-Actor-ID` + `X-Actor-Role` | `get_platform_actor` | `/tenants/*` legacy CRUD (Hiba's lane) |

The three are deliberately separate: a widget JWT can't reach an admin
route, an admin JWT can't reach `/chat`, the platform-actor path can't read
admin pages. Each uses a different signing secret.

### Roles

```
tenant_manager  — admins the platform; invites other admins, manages tenants
tenant_admin    — admins one tenant; CMS / leads / usage / widget config
member          — placeholder, not wired
visitor         — anonymous chat user (widget JWT only)
```

Only `tenant_admin` and `tenant_manager` can hold an admin JWT
(`_ALLOWED_LOGIN_ROLES` in [app/services/admin_auth.py](app/services/admin_auth.py)).

### Dev-mode shortcut

`require_tenant_admin` and `require_admin_session` accept `X-Concierge-*`
dev headers **only when `CONCIERGE_ENV=dev`**, to keep the existing test
suite running without re-minting JWTs for every fixture. Set
`CONCIERGE_ENV=prod` to close the door — the integration test
`test_admin_call_without_jwt_in_prod_mode_returns_403` proves it works.

---

## 4. Database

19 tables, all tenant-owned ones have RLS with the `tenant_isolation`
policy expression:
```sql
tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
```

### Migrations

| Revision | File | What |
|----------|------|------|
| 0001 | `0001_hiba_platform_schema_rls.py` | Hiba baseline: tenants, audit_logs, tenant_usage, tenant_rate_limits, erasure_jobs, cms_pages, leads, conversations + RLS |
| 0002 | `0002_admin_users.py` | `admin_users` (auth feature) + RLS |
| 0003 | `0003_admin_invites.py` | `admin_invites` + `admin_users.full_name` + `admin_users.status` |
| 0004 | `0004_contract_schema_parity.py` | 8 new tables (users, tenant_memberships, widget_configs, tenant_agent_configs, rag_chunks, messages, escalation_tickets, traces) + 4 column-adds (tenants/cms_pages/conversations/leads) + pgvector extension |

### pgvector

`rag_chunks.embedding vector(1536)` — matches OpenAI text-embedding-3-small.
Dimension lives in one constant (`EMBEDDING_DIM` in the migration) so a
model switch is a one-line change + a follow-up migration.

### RLS bypass note

With `FORCE ROW LEVEL SECURITY`, Postgres still exempts superusers from
policies. The dev `postgres` user is a superuser, so the app reads
everything. This means **RLS is currently a secondary defense**; the primary
isolation guard is the explicit `WHERE tenant_id = …` in every repository
query (CONTRACT.md §7). A future hardening pass will switch the app to a
non-superuser role; documented in [app/repositories/widget_repo.py](app/repositories/widget_repo.py) module docstring.

---

## 5. Admin authentication system

Three files, three flows:

### a. Login — `POST /admin/login`

[app/api/routes/admin_auth.py](app/api/routes/admin_auth.py) → [app/services/admin_auth.py](app/services/admin_auth.py)

1. Body: `{email, password}`
2. Service looks up the `admin_users` row, bcrypt-verifies the hash, refuses
   suspended users + unknown roles
3. Mints an HS256 JWT signed with `ADMIN_JWT_SECRET` (8 h TTL, no refresh)
4. Returns `{token, expires_in, actor_id, tenant_id, role, full_name}` — all
   fields server-issued; the client never picks `role` or `tenant_id`

**Anti-enumeration**: every failure (unknown email, wrong password, suspended,
unknown role, malformed body) collapses to the same `401 {"error":"invalid_credentials"}`
body. A dummy bcrypt verify runs on email-miss to keep timing constant.

### b. Invite flow

[app/api/routes/admin_invites.py](app/api/routes/admin_invites.py) → [app/services/admin_invite.py](app/services/admin_invite.py)

```
authenticated admin                       public visitor (no JWT)
─────────────────────                     ──────────────────────
POST /admin/invites                   →   GET /admin/invites/{token}     (preview)
   ↓ (mints UUID token, persists row)        ↓ (safe metadata only)
returns {token, email, role,              returns {email, role, tenant_name,
         tenant_id, expires_at}                    expires_at, status}
                                              ↓
                                          POST /admin/invites/{token}/accept
                                              ↓ (body: full_name + password)
                                          creates admin_user row using
                                          tenant_id / role / email FROM the
                                          invite row — never from the body
```

**Tenant-isolation invariant**: the inviter's `tenant_id` comes from THEIR
JWT, not from the request body. Even if the body smuggles `tenant_id`, it's
ignored. Asserted by
`test_invite_create_body_cannot_override_tenant_id`.

**Single-use**: `used_at` stamp + status check; second accept → 400.

**Password rules** (in service): min 8 chars, ≥1 letter, ≥1 digit, ≤72 bytes
(bcrypt cap). Mismatch / weak password → `422 {"error":"weak_password",...}`.

### c. Streamlit UI

[admin/streamlit_app.py](admin/streamlit_app.py) is a dispatcher:

```python
page_param = st.query_params.get("page")

if page_param == "accept-invite":
    accept_invite_page.render()  # public
elif not auth_state.is_authenticated():
    login_page.render()           # public
elif role == "tenant_manager":
    platform_dashboard_page.render()
elif role == "tenant_admin":
    tenant_dashboard()            # CMS / Leads / Usage / Widget / Tenant
else:
    access_denied_page.render()
```

JWT lives in `st.session_state["admin_token"]` only — never browser
localStorage / cookies (matches the widget storage discipline). Sign Out
(`auth_state.clear_session`) wipes every `admin_*` key.

Brand chrome (centered card, Concierge AI header, tagline) in
[admin/brand.py](admin/brand.py) shared by login + accept-invite.

---

## 6. Widget chain (end-to-end)

Three steps; no admin involvement at runtime.

```
1.  Tenant host page loads widget.js (loader)
       ↓
    iframe mounts pointing at the API origin (or VITE_BACKEND_URL)
       ↓
2.  iframe POST /widgets/token
       Body: {widget_id}
       Header: Origin (browser-supplied)
       ↓
    WidgetTokenService.issue_token:
      • per-IP + per-widget rate-limit checks (in-process token bucket)
      • SqlWidgetRepository.get_by_widget_id (joins widget_configs ↔ tenants
        to populate tenant_status)
      • origin canonicalization vs allowed_origins_json
      • mints HS256 JWT { tenant_id, widget_id, origin, session_id, iat, exp }
       ↓
3.  iframe POST /chat (Authorization: Bearer <widget-jwt>)
       ↓
    get_tenant_id_from_widget_token verifies signature + exp,
      returns tenant_id as UUID
       ↓
    ChatService.handle_message(tenant_id, message, session_id)
      → Nasser's router/agent/tools (RAG, capture_lead, escalate)
      → returns {answer, route, used_tools}
```

All refusal causes on `/widgets/token` collapse to byte-identical
`403 {"error":"widget_unavailable"}` so attackers can't distinguish
"unknown widget" from "origin not allowlisted" from "rate limited".

### SQL widget backend

[app/repositories/widget_repo.py](app/repositories/widget_repo.py) holds two
interchangeable implementations behind one `WidgetRepository` Protocol:

- `InMemoryWidgetRepository` — module-level singleton seeded with the demo
  fixture. Used when `WIDGET_REPO_BACKEND=memory` (default).
- `SqlWidgetRepository` — backs the `widget_configs` table from migration
  0004. Used when `WIDGET_REPO_BACKEND=sql`.

The factory `get_widget_repository` is a FastAPI dep (takes `AsyncSession`)
so the SQL backend gets the request-scoped session; the in-memory backend
ignores it. Service constructors (`get_widget_token_service`,
`get_widget_config_service`) depend on the factory, rate limiters cached at
module level so their token-bucket state survives across requests.

Demo seed: `python -m scripts.seed_widget_config --tenant-id … --widget-id …
--origin …`.

---

## 7. Admin read endpoints

Five endpoints the Streamlit admin pages depend on, all gated by
`require_admin_session` (both `tenant_admin` and `tenant_manager`):

| Route | Backing repo method | Auth check |
|-------|---------------------|------------|
| `GET /tenants/{tid}/audit-logs` | `TenantRepository.list_audit_logs` | path tenant_id MUST equal JWT tenant_id |
| `GET /tenants/{tid}/usage?days=30` | `TenantRepository.usage_rollup` (group-by feature + day, sum tokens + cost) | same |
| `GET /cms/pages` | `CmsRepository.list_pages(tenant_id)` | tenant scope from JWT |
| `POST /cms/pages` | `CmsRepository.create(...)` | tenant_id from JWT, body has `extra=forbid` so it can't smuggle one |
| `GET /leads?limit=100` | `LeadRepository.list_by_tenant` | tenant scope from JWT |

Usage-rollup response shape exactly matches what `admin/usage_page.py`
expects: `{total_tokens, total_cost_usd, by_feature{feature:{tokens,cost_usd}}, daily_cost_usd[{date,cost_usd}]}`.

Cross-tenant path access → 403 (asserted by
`test_audit_logs_rejects_cross_tenant_path`, `test_usage_rollup_rejects_cross_tenant_path`).

---

## 8. Real eval CLIs

Replaced three mock evaluators with real ones. All conform to
[specs/006-ci-eval-gates/contracts/eval-cli.md](specs/006-ci-eval-gates/contracts/eval-cli.md).

| Gate | What it actually does | Measured |
|------|----------------------|----------|
| `classifier` | Loads the chosen ONNX model via `RouterClassifier` (SHA-verifies all 3 artifacts), replays the training notebook's `random_state=42` stratified test split on the committed CSV, computes macro_f1 + accuracy + per-class F1 | **0.9752** vs 0.80 floor |
| `redaction` | Iterates `evals/redaction/redaction_cases.json`, runs `app.infra.redaction.redact_text` on each input, counts cases where any `must_not_contain` string still appears in the output | **0** leaks of 5 cases |
| `red_team` | Iterates `evals/red_team/red_team_cases.json`, calls `guardrails.main.evaluate_platform_rails` on each message, computes `refusal_rate = blocked / expected_block` | **1.0** (6/6 blocked) |

Determinism: pure regex (redaction), pure rule matching (red_team), ONNX
CPU inference (classifier — same artifact + same split = identical
predictions). No LLM calls, no API dependencies, no random sampling.

The classifier CLI emits `dataset_hash: sha256:…` from the model card for
provenance.

---

## 9. File map

### New files (44)

```
app/
  api/routes/admin_auth.py          POST /admin/login
  api/routes/admin_invites.py       POST/GET admin invite endpoints
  api/routes/leads.py               GET /leads
  domain/admin_auth.py              login req/resp models
  domain/admin_invite.py            invite req/resp models
  db/migrations/versions/
    0002_admin_users.py
    0003_admin_invites.py
    0004_contract_schema_parity.py  8 new tables + 4 alters + pgvector
  infra/password.py                 bcrypt hash/verify (72-byte safe)
  repositories/admin_user_repo.py
  repositories/admin_invite_repo.py
  services/admin_settings.py        ADMIN_JWT_SECRET, TTL
  services/admin_auth.py            authenticate() + verify_admin_token()
  services/admin_invite.py          create/get/accept service logic

admin/
  brand.py                          shared centered-card CSS + product header
  login_page.py                     refactored — branded card, loading state
  accept_invite_page.py             /?page=accept-invite&token=...
  platform_dashboard_page.py        tenant_manager landing (invite form)
  access_denied_page.py             unknown-role fallback
  auth_state.py                     st.session_state helpers (get/set/clear)

evals/
  classifier.py                     REAL — ONNX inference
  redaction.py                      REAL — runs production redact_text
  red_team.py                       REAL — runs guardrails platform rules

scripts/
  seed_admin.py                     CLI: provision an admin row
  seed_widget_config.py             CLI: provision a widget_configs row
  pgadmin/servers.json              auto-register Concierge DB in pgadmin

tests/
  unit/test_admin_auth.py                          11 tests
  unit/test_admin_invite_service.py                11 tests
  integration/test_widget_chat_flow.py              4 tests
  integration/test_admin_login_flow.py              5 tests
  integration/test_admin_invite_flow.py             8 tests
  integration/test_admin_read_endpoints.py         10 tests
  integration/test_sql_widget_repo.py               5 tests (env-gated)

AUTH.md                             role/route matrix, curl walkthroughs
summary.md                          this file
```

### Modified files (key ones)

```
app/api/deps.py                     get_tenant_id_from_widget_token (REAL),
                                    require_admin_session (new),
                                    require_tenant_admin (JWT + dev fallback)
app/api/routes/widgets.py           audit logger → TenantRepository,
                                    repo factory → FastAPI dep
app/api/routes/tenants.py           + GET /audit-logs + GET /usage rollup
app/api/routes/cms.py               replaced placeholder; + POST /cms/pages
app/api/routes/chat.py              (unchanged but now backed by real verifier)
app/api/main.py                     registers admin_auth + admin_invites + leads
app/db/models.py                    + AdminUser, AdminInvite, User,
                                    TenantMembership, WidgetConfig,
                                    TenantAgentConfig, RagChunk, Message,
                                    EscalationTicket, Trace + alters
app/repositories/widget_repo.py     + SqlWidgetRepository + dep factory
app/repositories/cms_repo.py        + create()
app/repositories/lead_repo.py       + list_by_tenant()
app/repositories/tenant_repo.py     + usage_rollup() aggregate query
app/services/widget_service.py      (no change; was already correct)
admin/streamlit_app.py              dispatcher: query params → role-based pages
admin/_admin_http.py                JWT from session_state; helpers
admin/widget_page.py / tenant_page.py / usage_page.py / cms_page.py / leads_page.py
                                    use shared http_client + signed_in_tenant_id()

docker-compose.yml                  + vault-seed, migrations, pgadmin
                                    api waits on service_completed_successfully
                                    admin gets CONCIERGE_BACKEND_URL=http://api:8000
Dockerfile                          + COPY alembic.ini
pyproject.toml                      + bcrypt
.env / .env.example                 + ADMIN_JWT_SECRET, ADMIN_TOKEN_TTL_SECONDS,
                                    CONCIERGE_ENV, CONCIERGE_BACKEND_URL,
                                    WIDGET_REPO_BACKEND, PGADMIN_*
eval_thresholds.yaml                + rag.mrr_min: 0.50
BLOCKED.md                          struck H1/H2/H3/H4/H5/H6/N8/N9/A1/A2/A3/A4;
                                    N1* marked partial
DECISIONS.md                        + Decisions 12, 13, 14
RUNBOOK.md                          documented bootstrap chain + pgadmin
```

---

## 10. Design decisions

Three formal decisions documented in [DECISIONS.md](DECISIONS.md):

### Decision 12 — Admin authentication
- bcrypt directly (passlib 1.7.4 is incompatible with bcrypt 5.x — falls
  back at `__about__` lookup; calling bcrypt removes the version trap)
- 72-byte UTF-8 truncation on hash + verify (bcrypt limit)
- HS256 JWT, separate secret from widget JWT, 8 h TTL, no refresh
- Login failures collapse to one canonical 401 body (no enumeration)
- Dev-headers fallback retained behind `CONCIERGE_ENV=dev` so the existing
  ~150 test fixtures keep working

### Decision 13 — Invite flow + role-based dashboards
- `admin_invites` table: single-use UUID token, RLS-enabled
- Acceptance schema has NO `email`/`role`/`tenant_id` fields — server reads
  all three from the invite row keyed by URL token
- Streamlit dispatcher routes by `st.query_params["page"]` (no real client
  router available); role decides the destination dashboard

### Decision 14 — Schema parity with CONTRACT.md §8.1
- One additive migration closes the gap
- `pgvector` extension, `rag_chunks.embedding vector(1536)`
- Backfill new NOT-NULL string columns deterministically (slug ← name/title
  via regex; plan='starter'; status='published'/'captured')
- Intentionally additive — `admin_users` / `admin_invites` stay; migrating
  auth to `users` + `tenant_memberships` is deferred so the live login flow
  isn't disrupted

---

## 11. How a request flows

### Visitor sends a chat message

```
Browser (widget iframe)
  │ POST /chat
  │ Authorization: Bearer <widget-jwt>
  ▼
FastAPI router (app/api/routes/chat.py)
  │ Depends(get_tenant_id_from_widget_token)
  ▼
app/api/deps.py::get_tenant_id_from_widget_token
  │ • parse Bearer scheme
  │ • jwt.decode(token, WIDGET_JWT_SECRET, HS256)
  │ • verify exp
  │ • extract tenant_id claim → UUID
  ▼
ChatService(session).handle_message(tenant_id, message, session_id)
  │ • redact + persist to Redis memory
  │ • route_message_decision(message)
  │   ↳ ModelserverClient.predict (else fallback rules)
  │ • execute route: rag_search | capture_lead | escalate | agent
  │ • redact + persist assistant turn
  ▼
ChatResponse {answer, route, used_tools}
```

### Admin updates the widget config

```
Streamlit admin page (admin/widget_page.py)
  │ PUT /widgets/config
  │ Authorization: Bearer <admin-jwt> (from st.session_state)
  ▼
app/api/deps.py::require_tenant_admin
  │ • verify admin JWT (different secret)
  │ • role MUST be tenant_admin
  │ • return TenantAdminContext(tenant_id, actor_id)
  ▼
WidgetConfigService.update_widget_config(tenant_id, body, actor_id)
  │ • diff allowed_origins (added / removed)
  │ • snapshot for rollback
  │ • repo.update_by_tenant_id(tenant_id, ...)
  │   ↳ InMemoryWidgetRepository  OR  SqlWidgetRepository
  │ • for each added/removed origin:
  │     audit_logger.add_audit_log(
  │         tenant_id=..., action='widget.origin_added', ...)
  │   ↳ TenantRepository.add_audit_log writes to audit_logs table
  ▼
WidgetConfigResponse (or 500 on audit failure → snapshot restored)
```

### Tenant manager invites a new admin

```
platform_dashboard_page.py form
  │ POST /admin/invites
  │ Authorization: Bearer <tenant_manager-jwt>
  ▼
require_admin_session  (tenant_admin OR tenant_manager — both allowed)
  ▼
create_invite(request, inviter_tenant_id=admin.tenant_id, ...)
  │ • tenant_id comes from the JWT, NEVER from the request body
  │ • UUID token, configurable TTL
  │ • repo.create(token, tenant_id, email, role, invited_by, expires_at)
  ▼
{token, email, role, tenant_id, expires_at}
       │
       │  invite link shared out-of-band
       ▼
Invitee opens /?page=accept-invite&token=<token>
  │ GET /admin/invites/<token>  (public preview)
  ▼
get_invite_details → {email, role, tenant_name, status}
  │  (status: pending / used / expired)
  ▼
POST /admin/invites/<token>/accept
  Body: {full_name, password, confirm_password}    # no email/role/tenant_id
  │
accept_invite:
  │ • password match + strength check
  │ • get invite row; status must be 'pending'
  │ • create admin_user row using tenant_id / role / email FROM the invite
  │ • mark_used(invite, now)
  ▼
streamlit auto-signs the new admin in → role-based dashboard
```

---

## 12. Test coverage

Total: **204 passed, 1 skipped** (unit + integration + security), plus
**5 passing SQL repo integration tests** when run against a live Postgres.

Highlights:
- Login: every failure cause collapses to the same 401 body
- Invite: body cannot override `tenant_id`; single-use enforced; expired /
  used / unknown / weak-password / mismatched-password all distinct
- Widget chain: full token → JWT → chat round-trip with TestClient
- Admin read endpoints: cross-tenant path → 403, no-JWT-in-prod-mode → 403
- SQL widget repo: get / update / unknown-tenant → None
- Classifier eval: exact match to model card (0.9752)
- Redaction / red-team: 0 leaks / 1.0 refusal rate against committed cases

---

## 13. What's still open in BLOCKED.md

These are out of my lane (Amer) or require domain expertise I deferred to
the owner:

| Owner | Item |
|-------|------|
| Nasser | N2 (agent chat path — full integration), N3 (capture_lead audit row), N4 (escalate ticket persistence), N5 (real evals/rag.py), N6 (real evals/agent_tool.py), N7 (emit metrics.mrr) |
| Ayoub | A5 (real guardrails readiness endpoint beyond the current `/openapi.json` probe) |
| Hiba | H7 / H8 / H9 (smoke probes that auto-unblock when N2-N4 land) |
| Cross-team | X1 (flip SMOKE_E2E_REQUIRE_FULL_STACK in CI — auto-fires via strict-xfail when N2-N4 land), X2 (MRR end-to-end pairs A4 + N7) |
| Operational | U1 (clean-clone runbook walk), U2 (make portability), U3 (branch protection) |

The `admin_users` + `admin_invites` → `users` + `tenant_memberships` migration
mentioned in Decision 14 is a deferred follow-up; the live auth keeps working
against the original tables.

---

## 14. Standing the stack up

```bash
# fresh clone
cp .env.example .env
docker compose up --build       # vault-seed → migrations → api auto-chain

# seed a first admin (tenant manager)
docker compose exec api python -m scripts.seed_admin \
  --email boss@acme.example --password 'BossPw123' \
  --tenant-id 11111111-1111-1111-1111-111111111111 --role tenant_manager

# seed the demo widget config (for SQL backend)
docker compose exec api python -m scripts.seed_widget_config \
  --tenant-id 11111111-1111-1111-1111-111111111111 \
  --widget-id 9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d \
  --origin http://localhost:5173

# open the surfaces
#   admin UI       → http://localhost:8501
#   widget host    → http://localhost:5173/host-test.html
#   pgadmin        → http://localhost:5050 (admin@concierge.dev / admin)
#   API docs       → http://localhost:8000/docs

# run the real eval gates
docker compose exec api python -m evals.classifier --output /tmp/c.json
docker compose exec api python -m evals.redaction  --output /tmp/r.json
docker compose exec api python -m evals.red_team   --output /tmp/rt.json
```
