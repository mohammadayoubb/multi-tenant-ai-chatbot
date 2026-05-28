# Contract: `POST /widgets/token`

The public token-exchange endpoint. This contract is exactly what visitor browsers (via the widget iframe) call when they need a session credential, and exactly what downstream services (Nasser's `/chat`) expect a token to claim.

## Route

```
POST /widgets/token
Content-Type: application/json
Origin: <browser-supplied; required>
```

The `Origin` request header is the authoritative source of the visitor's origin. The endpoint MUST NOT read origin from the request body; that field exists only for the legacy / curl-debug use case and is ignored if present and mismatched with the `Origin` header (see Edge Cases below).

Owner: Amer (CONTRACT.md §2.9). Hiba review required (touches tenant resolution and widget_configs read).

## Success: `200 OK`

### Request body

```json
{
  "widget_id": "9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `widget_id` | UUID (string) | yes | The public widget identifier the host site embeds. |

### Response body

```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0ZW5hbnRfaWQiOiI...",
  "expires_in": 900,
  "session_id": "f1c8d4e2-5a3b-4c7d-8e9f-1a2b3c4d5e6f"
}
```

| Field | Type | Notes |
|---|---|---|
| `token` | JWT string (HS256) | Claims per [data-model.md §2](../data-model.md#2-widget-session-token-transient--jwt-not-persisted). |
| `expires_in` | integer (seconds) | Equal to `WIDGET_TOKEN_TTL_SECONDS` (default 900). |
| `session_id` | UUID (string) | Same value as the `session_id` claim inside the JWT, exposed for convenience. |

### Success preconditions (all MUST be true; see [spec.md FR-001 through FR-006](../spec.md))

1. The provided `widget_id` exists in `widget_configs`.
2. `widget_configs.enabled = true` for that row.
3. The owning tenant's `status = 'active'`.
4. The request's `Origin` header **exactly** matches one of the entries in `widget_configs.allowed_origins_json` (scheme exact, port exact, host case-insensitive; no subdomain rollup; no wildcard).
5. The request has NOT exceeded the per-IP rate baseline.
6. The request has NOT exceeded the per-widget rate baseline.

## Failure: `403 Forbidden`

ALL refusal causes return the same status, the same body, the same fields, and the same headers (except headers that legitimately vary like `Date`). See [spec.md FR-007, FR-017](../spec.md).

### Response body (every refusal cause)

```json
{
  "error": "widget_unavailable"
}
```

That is the ENTIRE response body. No `code`, no `detail`, no `message`, no `reason`. No nested error object. Two bytes of variability (`Date` header) at most. This is enforced by an automated comparison test (SC-002) that hashes responses from every refusal cause and asserts equality of the body bytes.

### Causes mapping (visible only in internal logs, never in the response)

| Internal reason | When |
|---|---|
| `unknown_widget` | `widget_id` does not exist in `widget_configs`. The widget-config lookup MUST still execute before this branch returns (FR-008a) so timing matches the other refusal paths. |
| `origin_not_allowlisted` | `widget_id` exists, but the `Origin` header does not match any entry in `allowed_origins_json`. |
| `widget_disabled` | `widget_id` exists, but `widget_configs.enabled = false`. |
| `tenant_not_active` | `widget_id` exists and is enabled, but the owning tenant's `status != 'active'`. |
| `rate_limited_per_ip` | Per-IP request-rate baseline exceeded for this source IP. |
| `rate_limited_per_widget` | Per-widget request-rate baseline exceeded for this `widget_id`. |

Each cause is logged to `widget.token.refused` (see [data-model.md §3](../data-model.md#3-token-refusal-log-entry-transient--emitted-to-stdoutstructlog-consumed-by-ayoubs-traces-pipeline-later)) and recorded on the request trace span (FR-022).

## Failure: `400 Bad Request`

Reserved exclusively for malformed-request cases that cannot be confused with a security check:

- Request body is not valid JSON.
- `widget_id` is missing.
- `widget_id` is present but not a valid UUID string.

These cases are *intentionally* distinguishable from the security refusals because they cannot be triggered by an enumeration probe (an attacker probing for valid widget IDs always sends valid-shape JSON). The response body is:

```json
{
  "error": "bad_request"
}
```

(Same minimalism as the 403 — the `error` value is the only field, but its value differs.)

## Headers and middleware

| Aspect | Setting |
|---|---|
| CORS | Standard FastAPI CORS middleware. **Reminder**: CORS is NOT authentication (Principle IV). The origin allowlist enforcement happens *before* the response; CORS headers are defense-in-depth so non-allowlisted origins can't read the response even if a bug let one slip through. |
| Rate-limit headers | NOT included on refusals (would distinguish rate-limit from validation refusals; violates FR-017). MAY be included on `200` responses as `X-RateLimit-Remaining-*` for legitimate clients. |
| Cache-Control | `no-store` on every response. Tokens are not cacheable. |
| Content-Type | `application/json` on every response. |

## Idempotency

Token issuance is **not** idempotent. Each successful request mints a new JWT with a new `session_id` and a new `iat`. The widget MUST NOT retry a failed token request without exponential backoff, since rapid retries will trip the per-widget rate baseline indistinguishably from an attack.

## Examples

### Successful exchange (curl)

```bash
curl -X POST http://localhost:8000/widgets/token \
  -H "Content-Type: application/json" \
  -H "Origin: https://customer-site.example" \
  -d '{"widget_id":"9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d"}'
```

→
```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"token":"eyJ...","expires_in":900,"session_id":"f1c8d4e2-5a3b-4c7d-8e9f-1a2b3c4d5e6f"}
```

### Refusal — origin mismatch (curl)

```bash
curl -X POST http://localhost:8000/widgets/token \
  -H "Content-Type: application/json" \
  -H "Origin: https://attacker.example" \
  -d '{"widget_id":"9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d"}'
```

→
```http
HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{"error":"widget_unavailable"}
```

### Refusal — unknown widget (curl)

```bash
curl -X POST http://localhost:8000/widgets/token \
  -H "Content-Type: application/json" \
  -H "Origin: https://customer-site.example" \
  -d '{"widget_id":"00000000-0000-0000-0000-000000000000"}'
```

→
```http
HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{"error":"widget_unavailable"}
```

**Note the response bodies of the two refusals above are byte-identical.** This is SC-002.

## Out of scope for this contract

- Token verification by downstream services. The `/chat` route owns its own JWT verification using `WIDGET_JWT_SECRET` (Hiba's `get_tenant_id_from_widget_token` dep in [app/api/deps.py](../../../app/api/deps.py) is the authoritative consumer).
- Token refresh / extension. An expired token is replaced by re-running this exchange from scratch.
- Vault-backed signing key rotation. Deferred to a separate feature (Ayoub).
- Token revocation. Deferred (spec clarification Q2 → A).
