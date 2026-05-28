# Auth — Roles, Tokens, and How to Test

This doc covers every authentication path that exists in the running
Concierge stack today, what each role is allowed to do, and how to exercise
each path end-to-end (curl + Streamlit + widget).

There are **three independent auth surfaces** in the codebase; understanding
which one applies to which route is the only thing you need to internalize
before reading the rest of this file:

| Surface | What it authenticates | Header / token | Where it's enforced |
|---|---|---|---|
| **Admin JWT** | A signed-in human admin (UI or API client) | `Authorization: Bearer <admin-jwt>` | `app/api/deps.py:require_tenant_admin` and `require_admin_session` |
| **Widget JWT** | A visitor's browser, scoped to one tenant via the widget loader | `Authorization: Bearer <widget-jwt>` | `app/api/deps.py:get_tenant_id_from_widget_token` |
| **Platform actor headers** *(legacy)* | An upstream-trusted platform-service caller (CI scripts, the demo seed scripts) | `X-Actor-ID` + `X-Actor-Role` headers | `app/api/deps.py:get_platform_actor` (used only by `/tenants/*` routes) |

The three are deliberately separate. A visitor's widget JWT cannot reach an
admin route; an admin JWT cannot mint a widget token; the platform-actor
header path cannot read admin pages.

---

## 1. Roles

Defined in `app/domain/tenant.py`:

```
tenant_manager  — operates the platform; can invite other admins, can manage tenants
tenant_admin    — manages ONE tenant's widget config, leads, CMS, usage
member          — placeholder, not used by any route yet
visitor         — a widget end-user; never has a password or a login
```

Only `tenant_admin` and `tenant_manager` can hold an admin JWT — login refuses
every other role with the canonical `invalid_credentials` 401 body. See
`app/services/admin_auth.py:_ALLOWED_LOGIN_ROLES`.

`visitor` is implicit: it's the *absence* of an admin JWT, with a widget JWT
issued by `POST /widgets/token`.

---

## 2. Capability matrix

What each role can do today (✓ = allowed, ✗ = refused, — = not applicable):

| Route | tenant_manager | tenant_admin | visitor (widget JWT) | anonymous |
|---|:-:|:-:|:-:|:-:|
| `POST /admin/login` | ✓ | ✓ | — | ✓ (public) |
| `POST /admin/invites` (create invite) | ✓ | ✓ | ✗ | ✗ |
| `GET  /admin/invites/{token}` (preview) | ✓ | ✓ | — | ✓ (public) |
| `POST /admin/invites/{token}/accept` | — | — | — | ✓ (public, single-use) |
| `GET  /widgets/config` | ✗ | ✓ | ✗ | ✗ |
| `PUT  /widgets/config` | ✗ | ✓ | ✗ | ✗ |
| `POST /widgets/token` (visitor exchange) | — | — | — | ✓ (rate-limited) |
| `POST /chat` | ✗ | ✗ | ✓ | ✗ |
| `POST /tenants` (provision) | * | ✗ | ✗ | ✗ |
| `GET  /tenants/{id}` | * | ✓ * | ✗ | ✗ |
| `POST /tenants/{id}/suspend` | * | ✗ | ✗ | ✗ |
| `DELETE /tenants/{id}` (erase) | * | ✗ | ✗ | ✗ |

\* The `/tenants/*` group does **not** read the admin JWT today — it uses
the legacy `X-Actor-ID` + `X-Actor-Role` headers (`get_platform_actor`). The
platform dashboard UI for invoking these routes hasn't landed yet; the
underlying gate already enforces the role check inside `TenantService`.

**Per-role visual flow** (after `POST /admin/login`):

```
tenant_manager  →  Platform dashboard      (admin/platform_dashboard_page.py)
                   • can mint invite tokens for either role
                   • placeholder for future tenant CRUD

tenant_admin    →  Tenant dashboard        (admin/streamlit_app.py sidebar)
                   • CMS / Leads / Usage / Widget / Tenant pages
                   • GET/PUT widget config

unknown role    →  Access denied screen    (admin/access_denied_page.py)
                   • sign-out button only
```

---

## 3. Provisioning an admin (zero → first login)

There is no self-signup. Admins are minted by `scripts/seed_admin.py` or
via an invite from an existing admin.

### Bootstrap the very first admin (no invite available)

Run inside the API container so it can reach `vault` and `db` by their
docker-network names:

```bash
docker compose exec api python -m scripts.seed_admin \
  --email boss@acme.example \
  --password 'BossPw123' \
  --tenant-id 11111111-1111-1111-1111-111111111111 \
  --role tenant_manager
```

Idempotent: re-running with the same email is a no-op and prints the
existing user id. Password may also come from `$ADMIN_SEED_PASSWORD` so it
never lands in shell history.

You can also create a `tenant_admin` the same way (drop `--role` to use the
default):

```bash
docker compose exec api python -m scripts.seed_admin \
  --email amer@acme.example --password 'AdminPw1' \
  --tenant-id 11111111-1111-1111-1111-111111111111
```

---

## 4. Logging in (curl)

```bash
curl -s -X POST http://localhost:8000/admin/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"boss@acme.example","password":"BossPw123"}' | jq
```

Successful response (200):

```json
{
  "token": "eyJhbGciOi...",
  "expires_in": 28800,
  "actor_id": "boss@acme.example",
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "role": "tenant_manager",
  "full_name": null
}
```

`role` and `tenant_id` are **server-issued** — the frontend cannot pick them.
Store `token` only in memory.

Every login failure path collapses to the same response (no enumeration):

```
HTTP/1.1 401 Unauthorized
Content-Type: application/json
{"error":"invalid_credentials"}
```

That single 401 body covers all of:
- unknown email
- wrong password
- suspended user (`admin_users.status != 'active'`)
- unrecognized role
- malformed body / missing fields

---

## 5. Using the admin JWT

Pass it as `Authorization: Bearer <token>` on every admin request:

```bash
TOKEN="eyJhbGciOi..."   # from the login response

# Read your widget config (tenant_admin only)
curl -s http://localhost:8000/widgets/config \
  -H "Authorization: Bearer $TOKEN" | jq

# Update your widget config (tenant_admin only)
curl -s -X PUT http://localhost:8000/widgets/config \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "allowed_origins": ["https://acme.example"],
    "enabled": true,
    "theme_json": null,
    "greeting": "Hi!"
  }' | jq
```

A `tenant_manager` calling `GET /widgets/config` will get `403 forbidden`
because `require_tenant_admin` rejects every role except `tenant_admin`.

Expired tokens: 8h TTL by default (`ADMIN_TOKEN_TTL_SECONDS=28800`). On
expiry the route returns the canonical 403; the UI shows the login form
again. There is no refresh — re-login.

---

## 6. Inviting a new admin (full flow)

A `tenant_manager` or `tenant_admin` can invite another admin into their own
tenant.

### a. Mint an invite (authenticated)

```bash
curl -s -X POST http://localhost:8000/admin/invites \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"email":"newbie@acme.example","role":"tenant_admin","ttl_seconds":86400}' | jq
```

Response (200):
```json
{
  "token": "8e2c…-…-…",
  "email": "newbie@acme.example",
  "role": "tenant_admin",
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "expires_at": "2026-05-29T19:55:00+00:00"
}
```

**Important** (and unit-tested in
`tests/integration/test_admin_invite_flow.py::test_invite_create_body_cannot_override_tenant_id`):
the inviter's `tenant_id` comes from THEIR JWT. Even if the request body
includes a foreign `tenant_id`, it is ignored — the invite is always pinned
to the inviter's tenant.

### b. Preview the invite (public; safe metadata only)

```bash
curl -s http://localhost:8000/admin/invites/<token> | jq
```

```json
{
  "email": "newbie@acme.example",
  "role": "tenant_admin",
  "tenant_name": "Acme Inc.",
  "expires_at": "2026-05-29T19:55:00+00:00",
  "status": "pending"
}
```

`status` may be `pending`, `expired`, or `used`. Notice the response **does
not** include `tenant_id` or `invited_by` — those are platform metadata that
shouldn't leak from a stolen invite link.

### c. Accept the invite (public, single-use)

```bash
curl -s -X POST http://localhost:8000/admin/invites/<token>/accept \
  -H 'Content-Type: application/json' \
  -d '{
    "full_name": "New Bie",
    "password": "hunter2letter",
    "confirm_password": "hunter2letter"
  }'
```

On success: `200`, the new user can log in immediately.

The accept schema has **no** `email`, `role`, or `tenant_id` fields — all
three come from the invite row keyed by the URL token. The visitor cannot
override them.

Failure modes:
- `400 {"error":"invite_unavailable"}` — token unknown, expired, used, or
  passwords don't match
- `422 {"error":"weak_password","message":"..."}` — < 8 chars / missing
  letter / missing digit / > 72 bytes (bcrypt cap)

---

## 7. Streamlit admin UI

```bash
# from docker-compose, admin is already wired
open http://localhost:8501
```

What you'll see, based on which role the JWT carries:

| You land on | Sidebar | Pages |
|---|---|---|
| Login page | — | Email + password + "Have an invite? Accept invite" link |
| Platform dashboard (`tenant_manager`) | Signed-in name + Sign out | Invite-an-admin form |
| Tenant dashboard (`tenant_admin`) | Signed-in name + Sign out + Navigation | Tenant / CMS / Leads / Usage / Widget / Guardrails |
| Access denied (unknown role) | — | Sign-out button only |

**Invite acceptance from the UI**: deep-link to
`http://localhost:8501/?page=accept-invite&token=<token>`. The accept-invite
page reads the token from query params, renders the same email/role/tenant
banner the API exposes, and signs the new admin in automatically on success.

The JWT lives in `st.session_state["admin_token"]` only — never browser
storage, cookies, or localStorage. Sign Out (`auth_state.clear_session`)
wipes every `admin_*` key.

---

## 8. Widget visitor flow (no login)

This is the **public, no-credentials** path. The visitor's browser exchanges
a `widget_id` + the page's `Origin` header for a short-lived widget JWT, then
sends every chat message with that JWT.

```bash
# 1. exchange — public; rate-limited per-IP and per-widget
curl -s -X POST http://localhost:8000/widgets/token \
  -H 'Content-Type: application/json' \
  -H 'Origin: http://localhost:5173' \
  -d '{"widget_id":"9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d"}'
# → {"token":"...","expires_in":900,"session_id":"..."}

# 2. chat — Bearer widget JWT
TOKEN=...
curl -s -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"message":"hi","session_id":"<session_id-from-step-1>"}'
```

Every refusal path on `/widgets/token` returns the byte-identical
`{"error":"widget_unavailable"}` with status 403 — the visitor cannot tell
"unknown widget" from "origin not allowlisted" from "rate limited". See
`specs/001-widget-token-exchange/contracts/widget-token-endpoint.md`.

The widget JWT cannot reach any admin route. The admin JWT cannot reach
`/chat` (different secret + different dep).

---

## 9. Failure paths worth re-testing manually

| What | Expected | Where it's enforced |
|---|---|---|
| Login with wrong password | `401 {"error":"invalid_credentials"}` (same as unknown email — no enumeration) | `app/services/admin_auth.py:authenticate` |
| Login as suspended user | Same canonical 401 | same |
| Admin call with no `Authorization` header in prod (`CONCIERGE_ENV=prod`) | `403 {"error":"forbidden"}` | `app/api/deps.py:require_tenant_admin` |
| Invite create body trying to override `tenant_id` | Server uses inviter's JWT tenant; body is ignored | unit test `test_invite_create_body_cannot_override_tenant_id` |
| Accept invite twice | Second call → `400 {"error":"invite_unavailable"}` | `app/services/admin_invite.py:accept_invite` (single-use via `used_at`) |
| Accept invite with weak password | `422 {"error":"weak_password","message":"..."}` | `_check_password_strength` |
| Accept invite after `expires_at` | `400 {"error":"invite_unavailable"}` | `_invite_status` |
| `tenant_manager` calling `GET /widgets/config` | `403 {"error":"forbidden"}` | `require_tenant_admin` rejects non-tenant_admin |

Run the existing automated coverage:

```bash
pytest tests/unit/test_admin_auth.py        # 11 tests — password + JWT verify + auth logic
pytest tests/unit/test_admin_invite_service.py   # 11 tests — invite create/get/accept
pytest tests/integration/test_admin_login_flow.py   # 5 tests — login → JWT → /widgets/config
pytest tests/integration/test_admin_invite_flow.py  # 8 tests — full HTTP invite flow
pytest tests/integration/test_widget_chat_flow.py   # 4 tests — widget visitor flow
```

---

## 10. Dev mode shortcuts (CONCIERGE_ENV=dev)

For local tests that haven't been ported to mint a real JWT, both admin deps
accept the legacy `X-Concierge-Role` / `X-Concierge-Tenant-Id` /
`X-Concierge-Actor-Id` header trio **only when `CONCIERGE_ENV=dev`**:

```bash
curl -s http://localhost:8000/widgets/config \
  -H 'X-Concierge-Role: tenant_admin' \
  -H 'X-Concierge-Tenant-Id: 11111111-1111-1111-1111-111111111111' \
  -H 'X-Concierge-Actor-Id: amer@example.com'
```

In staging or prod, set `CONCIERGE_ENV=prod` (or anything other than `dev`)
in `.env` to close this door. The JWT path is the only auth that works in
production mode, and the integration test
`tests/integration/test_admin_login_flow.py::test_admin_call_without_jwt_in_prod_mode_returns_403`
proves the fallback is properly gated.

---

## 11. Configuration reference

Variables that affect auth, all in `.env` (defaults shown in
`.env.example`):

| Variable | Default | What it controls |
|---|---|---|
| `ADMIN_JWT_SECRET` | dev-only placeholder | HS256 signing key for admin JWTs. **Rotate before staging/prod.** |
| `ADMIN_TOKEN_TTL_SECONDS` | `28800` (8h) | Admin session lifetime; no refresh, re-login after expiry. |
| `CONCIERGE_ENV` | `dev` | When `!= dev`, the X-Concierge-* dev-headers fallback in admin deps is closed. |
| `WIDGET_JWT_SECRET` | dev-only placeholder | HS256 signing key for widget JWTs (separate from the admin secret). |
| `WIDGET_TOKEN_TTL_SECONDS` | `900` (15 min) | Widget session lifetime. |
| `VAULT_TOKEN` / `VAULT_ADDR` | `root` / `http://vault:8200` | Bootstrap creds for the Vault container (dev). |

Both JWT secrets default to known placeholder values inside the source so
the test suite boots without env wiring — set real values before any
deployment.

---

## See also

- `DECISIONS.md` §12, §13, §14 — design rationale (auth, invites, schema)
- `BLOCKED.md` — H1 / H3 / H4 are resolved; admin auth is the auth surface
- `CONTRACT.md` §2.5 — trusted tenant context rules
- `specs/001-widget-token-exchange/contracts/widget-token-endpoint.md` —
  the visitor-side JWT contract
