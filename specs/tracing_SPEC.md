# Tracing SPEC

Owner: Ayoub  
Component: Owner C — Redaction-Safe Tracing and Request Correlation  
Status: Draft

---

## 1. Purpose

Tracing gives the team visibility into how a visitor request moves through Concierge without leaking sensitive data.

Each request should receive a request ID that follows it across:

- API
- modelserver
- guardrails sidecar
- router
- agent flow
- logs
- security checks

Tracing must be redaction-safe.

---

## 2. Architecture Contract Rules

This component must follow the shared `CLAUDE.md` architecture contract.

Important rules:

- Use logging, not print.
- Do not log secrets, tokens, passwords, PII, or raw sensitive data.
- Use centralized architecture boundaries.
- Keep security behavior visible but safe.
- Service-to-service calls should carry request correlation metadata.
- Protected files must not be edited without explicit confirmation.

---

## 3. Request ID

Every inbound request should have a request ID.

If the client sends a valid `X-Request-ID`, the API may reuse it.

If not, the API should generate a new one.

The request ID should be passed to downstream services using:

```http
X-Request-ID: <request-id>
```

---

## 4. Trace Events

Trace events may include:

| Event | Description |
|---|---|
| `request.received` | API received a request |
| `guardrails.input.checked` | Input safety check completed |
| `classifier.predicted` | Modelserver returned a route label |
| `router.decision` | Router selected workflow or agent |
| `guardrails.output.checked` | Output safety check completed |
| `request.completed` | Response completed |

---

## 5. Allowed Trace Fields

Traces may include:

- request ID
- tenant ID from trusted context
- route name
- service name
- model version
- classifier label
- classifier confidence
- guardrail decision reason
- latency
- status code
- redaction count

---

## 6. Forbidden Trace Fields

Traces must not include:

- raw visitor message
- raw model output before redaction
- emails
- phone numbers
- passwords
- tokens
- API keys
- service credentials
- system prompt
- full Authorization header
- another tenant’s private content

---

## 7. Tenant Context

If tenant ID is included in traces, it must come from trusted server context.

It must never come from:

- visitor request body
- tool argument
- browser-provided tenant ID
- unverified widget input

---

## 8. Redaction Requirement

Before writing trace data, sensitive text must pass through the redaction layer.

For safety, the preferred design is to avoid logging raw text entirely and only log structured metadata.

---

## 9. Service Propagation

The API should propagate tracing metadata to:

- modelserver
- guardrails sidecar

Recommended headers:

```http
X-Request-ID: <request-id>
X-Tenant-ID: <trusted-tenant-id-if-needed>
```

`X-Tenant-ID` must only be sent after the API has verified tenant context.

---

## 10. Logging Format

Logs should be structured where possible.

Example safe log:

```json
{
  "event": "classifier.predicted",
  "request_id": "req_123",
  "tenant_id": "trusted-tenant-id",
  "label": "faq",
  "confidence": 0.88,
  "latency_ms": 14
}
```

Unsafe log example:

```json
{
  "message": "My email is user@example.com and my token is sk-test-123"
}
```

The unsafe example must not be allowed.

---

## 11. Tests

Minimum tests:

- request without `X-Request-ID` receives generated ID
- request with `X-Request-ID` propagates it
- API passes request ID to modelserver client
- API passes request ID to guardrails client
- raw fake secret does not appear in traces
- raw email does not appear in traces
- raw visitor message is not logged by default

---

## 12. Acceptance Criteria

- Request correlation exists.
- Request ID is propagated to internal service calls.
- Tracing/logging avoids raw sensitive data.
- Redaction is applied before trace output when needed.
- Tests prove fake secrets do not appear unredacted.
