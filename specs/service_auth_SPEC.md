# Service-to-Service Auth SPEC

Owner: Ayoub  
Component: Owner C — API, Modelserver, and Guardrails Service Authentication  
Status: Draft

---

## 1. Purpose

Service-to-service auth ensures that internal services do not trust each other only because they are on the Docker network.

The main API must authenticate when calling the modelserver and guardrails sidecar.

The modelserver and guardrails sidecar must reject unauthenticated internal requests.

---

## 2. Architecture Contract Rules

This component must follow the shared `CLAUDE.md` architecture contract.

Important rules:

- Service-to-service calls must use credentials from Vault.
- No secrets may be hardcoded.
- Do not commit `.env`.
- Do not add real API keys, tokens, passwords, or private keys.
- Internal network proximity is not authentication.
- Security-related file changes require Ayoub review.
- Protected files must not be edited without explicit confirmation.

---

## 3. Services Covered

This spec covers authentication for:

| Caller | Target | Purpose |
|---|---|---|
| API | Modelserver | Classifier prediction |
| API | Guardrails sidecar | Input/output safety checks and redaction |
| Guardrails sidecar | Modelserver, if needed later | Optional future safety/classification flow |

---

## 4. Credential Source

The service credential must be resolved from Vault.

Example logical secret names:

```text
secret/data/app/modelserver_service_token
secret/data/app/guardrails_service_token
```

The exact Vault path can be finalized during implementation, but it must be documented in `RUNBOOK.md` and `SECURITY.md`.

---

## 5. Request Authentication

Internal service calls should include a service credential header.

Example:

```http
Authorization: Bearer <service-token>
X-Request-ID: <request-id>
```

The service should verify the token before processing protected endpoints.

---

## 6. Endpoint Protection

Public health endpoints may be unauthenticated.

Protected endpoints must require service auth.

| Service | Endpoint | Auth Required? |
|---|---|---:|
| Modelserver | `GET /health` | No |
| Modelserver | `POST /predict` | Yes |
| Guardrails | `GET /health` | No |
| Guardrails | `POST /check/input` | Yes |
| Guardrails | `POST /check/output` | Yes |
| Guardrails | `POST /redact` | Yes |

---

## 7. Failure Behavior

Protected endpoints must reject:

- missing auth header
- malformed auth header
- invalid token
- empty token
- expired token, if expiry is used

Recommended status codes:

| Problem | Status |
|---|---:|
| Missing credential | 401 |
| Invalid credential | 403 |
| Malformed body | 422 |
| Internal Vault/config failure | 503 |

---

## 8. Logging Rules

Allowed logs:

- request ID
- caller service name if known
- auth failure reason code
- endpoint path
- latency

Forbidden logs:

- service token
- Vault response body
- secret value
- full Authorization header

---

## 9. Tests

Minimum tests:

- valid service credential is accepted
- missing credential is rejected
- invalid credential is rejected
- malformed Authorization header is rejected
- token is never printed in logs
- Vault missing secret causes safe startup failure or safe 503 behavior

---

## 10. Documentation Requirements

The final implementation must be documented in:

- `SECURITY.md`
- `RUNBOOK.md`
- `DECISIONS.md` if a non-trivial auth decision is made

Documentation should explain why Docker internal networking is not enough.

---

## 11. Acceptance Criteria

- API uses Vault-resolved service credentials.
- Modelserver protected endpoints require service auth.
- Guardrails protected endpoints require service auth.
- Tokens are never hardcoded.
- Tokens are never logged.
- Tests cover valid and invalid service auth.
