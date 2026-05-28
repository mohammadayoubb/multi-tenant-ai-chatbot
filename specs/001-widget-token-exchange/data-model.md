# Phase 1: Data Model

This feature touches three logical data shapes. Only the first is persisted in PostgreSQL; the other two are in-memory or in-log artifacts.

## 1. Widget Configuration (persisted, NOT modified by this feature)

The `widget_configs` table is owned by **Hiba/Amer review** per CONTRACT.md §8. Its schema is defined in CONTRACT.md §8.1 and is **re-used as-is** by this feature; no columns are added.

```text
id                    UUID PRIMARY KEY
tenant_id             UUID NOT NULL REFERENCES tenants(id)
widget_id             UUID NOT NULL UNIQUE
allowed_origins_json  JSONB NOT NULL          -- e.g. ["https://customer.example", "https://app.customer.example"]
theme_json            JSONB NOT NULL
greeting              TEXT NOT NULL
enabled               BOOLEAN NOT NULL
created_at            TIMESTAMP NOT NULL
updated_at            TIMESTAMP NOT NULL
```

**Indexes this feature needs in production** (Hiba's migration to add as part of her Phase 1 work):
- `UNIQUE INDEX widget_configs_widget_id_idx ON widget_configs (widget_id)` — already implied by the `UNIQUE` constraint above; this is the primary lookup key for the token endpoint.
- `INDEX widget_configs_tenant_id_idx ON widget_configs (tenant_id)` — for the admin UI in Phase 4.

**Row-Level Security**: Per Constitution Principle I, RLS is enforced in addition to repository-layer scoping. The repository function `get_widget_config_by_widget_id(widget_id)` does NOT take a `tenant_id` argument because the entire purpose of the lookup is to *discover* which tenant owns the widget. This is the one acceptable read path where the tenant_id flows OUT of the lookup rather than IN. After the lookup, the resolved `tenant_id` becomes the trusted context for any subsequent operation (FR-003).

**Tenant lifecycle gate**: The `widget_configs` row is only useful to this feature when its owning tenant's `status = 'active'` (per CONTRACT.md §2.4 + spec FR-001). The repository function returns the joined row including `tenants.status` so the service layer can apply the gate without a second round-trip.

### Validation rules (server-side, in the service layer)

| Field | Rule | Spec source |
|---|---|---|
| `widget_id` | Must exist; row must be returned by the lookup. | FR-001 |
| `enabled` | Must be `true` at issuance time. | FR-001 |
| `allowed_origins_json` | Must contain an entry whose canonicalized form matches the request's `Origin` exactly (scheme, port, lowercased host; path/query/fragment ignored; no subdomain rollup). | FR-002 |
| `tenants.status` (joined) | Must equal `'active'`. | FR-001, edge case "Tenant transitions to erasing or erased" |

### State transitions

This feature does not transition any row. It only reads. Writes to `widget_configs` (allowed-origin edits) happen in Phase 4 (Admin UI).

## 2. Widget Session Token (transient — JWT, not persisted)

A signed token returned to the visitor's browser. Not stored in any database. Lives in the browser's iframe memory for at most 15 minutes.

### Claim shape (HS256 JWT body)

| Claim | Type | Source | Notes |
|---|---|---|---|
| `tenant_id` | UUID (string) | Server-side, from `widget_configs.tenant_id` after lookup | FR-003 — never from request body |
| `widget_id` | UUID (string) | From the request body, but re-emitted from the verified row | Useful for downstream auditing |
| `origin` | String | From the request's `Origin` header (verified against allowlist) | FR-005 — origin-bound for replay detection |
| `session_id` | UUID (string) | Server-generated UUID4 at issuance time | FR-006 — one per issuance |
| `exp` | Unix timestamp (int) | `iat + WIDGET_TOKEN_TTL_SECONDS` (default 900 = 15 min) | FR-009 |
| `iat` | Unix timestamp (int) | Token issuance time | Standard JWT claim |

**Header**: `{"alg": "HS256", "typ": "JWT"}`. Signing key: `WIDGET_JWT_SECRET` (env var; Vault swap deferred to Ayoub).

### Response envelope (what the client receives)

```json
{
  "token": "<jwt>",
  "expires_in": 900,
  "session_id": "<uuid>"
}
```

The `session_id` is exposed in the response so the widget can use it as the chat session correlation key without needing to decode the JWT client-side. Per Constitution Principle IV, the widget does NOT verify or introspect the token; it just forwards it as a bearer credential to `/chat`.

### Token lifecycle (visitor side)

```
fetch /widgets/token  →  { token, session_id, expires_in: 900 }
                           ↓
                       Store token in module-scope `let` inside iframe
                       Store session_id likewise
                           ↓
                       Send Authorization: Bearer <token>  on every /chat call
                           ↓
                       On any /chat 401:  show "Session expired, please reload"
                       On page unload:    token gc'd with the iframe (no persistence)
                       On page reload:    re-run token exchange from scratch
```

## 3. Token Refusal Log Entry (transient — emitted to stdout/structlog, consumed by Ayoub's traces pipeline later)

Emitted once per refused token request. Never includes raw widget identifiers, raw IPs, or any secret material (FR-021, Constitution Principle V).

### Field shape

| Field | Type | Source | Notes |
|---|---|---|---|
| `event` | const string `"widget.token.refused"` | — | log routing key |
| `timestamp` | ISO-8601 UTC | server clock | — |
| `widget_id_hash` | hex string | `HMAC_SHA256(WIDGET_LOG_SALT, request.widget_id)` | FR-020 — salted, non-reversible |
| `ip_hash` | hex string | `HMAC_SHA256(WIDGET_LOG_SALT, request.client_ip)` | FR-021 — salted, non-reversible |
| `origin` | string | `request.headers.Origin` (raw) | FR-021 — origin is a published host, not PII |
| `reason` | enum string | one of: `unknown_widget`, `origin_not_allowlisted`, `widget_disabled`, `tenant_not_active`, `rate_limited_per_ip`, `rate_limited_per_widget` | FR-020 — internal bucket; never returned to client |
| `tenant_id` | UUID (string), conditional | server-side, from the resolved `widget_configs.tenant_id` | FR-014 — included for every reason where the widget was resolved (i.e., `origin_not_allowlisted`, `widget_disabled`, `tenant_not_active`, `rate_limited_per_widget`, and the post-lookup form of `rate_limited_per_ip`). Absent only for `unknown_widget`. Internal logs are not visible to attackers, so FR-007's indistinguishability is unaffected. |
| `latency_ms` | int | server-side wall time from request entry to response emit | optional, used for SC-008 monitoring |

**Successful issuance** emits a separate structured event `widget.token.issued` with the same hash fields plus the resolved `tenant_id`. The refusal log lives in a separate event name (`widget.token.refused`) so log routing can apply different access controls if needed in the future. Per FR-008a, every refusal — including unknown-widget — runs the widget lookup before returning, so `tenant_id` resolution is available for any reason except `unknown_widget`.

### Trace span shape (FR-022)

One span per request, emitted to whatever trace context the platform uses (TBD by Ayoub; this feature uses structlog binding + `trace_id` header propagation so it works against any backend).

| Attribute | Type | Notes |
|---|---|---|
| `span.name` | `"widget.token.exchange"` | |
| `request.origin` | string | client `Origin` header |
| `widget_id_hash` | hex | same as log |
| `outcome` | `"issued"` or `"refused"` | |
| `outcome.reason` | enum (refused only) | matches log `reason` enum |
| `tenant_id` | UUID (string), issued only | resolved server-side after lookup; omitted on refusals |
| `latency_ms` | int | |

## Cross-references

| Reference | Where |
|---|---|
| `widget_configs` schema | CONTRACT.md §8.1 |
| Canonical ID names | CONTRACT.md §6 (`tenant_id`, `widget_id`, `session_id` — never `business_id`, `chat_id`) |
| Tenant status enum | CONTRACT.md §2.4 |
| JWT claim shape | CONTRACT.md §2.9 |
| Audit-log function (used in Phase 4, not here) | CONTRACT.md §2.6 `add_audit_log` |
