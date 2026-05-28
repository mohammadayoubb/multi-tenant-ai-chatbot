# Redaction SPEC

Owner: Ayoub  
Component: Owner C — PII and Secret Redaction  
Status: Draft

---

## 1. Purpose

The redaction layer prevents sensitive information from leaking into logs, traces, memory, and evaluation artifacts.

Visitors may paste private data into the public chat widget. The system must treat this as expected behavior and redact sensitive values before storing or logging them.

---

## 2. Architecture Contract Rules

This component must follow the shared `CLAUDE.md` architecture contract.

Important rules:

- Do not log secrets, tokens, passwords, PII, or raw sensitive data.
- Redact before logs.
- Redact before traces.
- Redact before Redis memory when needed.
- Redact before any debug or eval artifact.
- Redaction tests must prove fake secrets do not appear unredacted.
- Platform redaction cannot be weakened by tenant configuration.

---

## 3. Sensitive Data Categories

The redaction layer should detect and redact:

| Type | Example | Replacement |
|---|---|---|
| Email | `user@example.com` | `[REDACTED_EMAIL]` |
| Phone number | `+961 70 123 456` | `[REDACTED_PHONE]` |
| API key / fake secret | `sk-test-123456` | `[REDACTED_SECRET]` |
| Bearer token | `Bearer abc.def.ghi` | `[REDACTED_TOKEN]` |
| Password-like text | `password: hunter2` | `[REDACTED_PASSWORD]` |
| Credit-card-like number | `4111 1111 1111 1111` | `[REDACTED_CARD]` |

The exact regexes can be improved during implementation, but the redaction behavior must be tested.

---

## 4. Redaction Boundaries

Redaction must happen before data reaches:

- application logs
- request traces
- Redis memory
- model/guardrails debug logs
- CI test artifacts
- admin-visible troubleshooting output

Raw data may still be stored in protected business tables if the product requires it, such as a lead email or phone number, but it must not leak into logs/traces.

---

## 5. Inputs

The redaction module accepts raw text.

```json
{
  "text": "My email is user@example.com and my API key is sk-test-abc123"
}
```

---

## 6. Outputs

The redaction module returns redacted text and metadata.

```json
{
  "redacted_text": "My email is [REDACTED_EMAIL] and my API key is [REDACTED_SECRET]",
  "redactions": [
    {
      "type": "email",
      "replacement": "[REDACTED_EMAIL]"
    },
    {
      "type": "secret",
      "replacement": "[REDACTED_SECRET]"
    }
  ]
}
```

---

## 7. Logging Rules

The redaction module itself must not log raw text.

Allowed logs:

- request ID
- count of redactions
- redaction types
- latency

Forbidden logs:

- original raw text
- exact detected secret
- exact detected phone number
- exact detected email
- full message content

---

## 8. Tenant Configuration Rules

Tenants may configure business guardrails, but they cannot disable platform redaction.

Forbidden tenant behavior:

- disabling PII redaction
- disabling fake secret redaction
- asking the system to store raw sensitive data in traces
- changing platform redaction replacements into revealing replacements

---

## 9. Tests

Minimum tests:

- email is redacted
- phone number is redacted
- fake API key is redacted
- bearer token is redacted
- password-like value is redacted
- multiple sensitive values are redacted in one message
- redaction metadata is returned
- raw fake secret does not appear in logs
- raw fake secret does not appear in traces
- non-sensitive text remains readable

---

## 10. Acceptance Criteria

- Redaction utility exists and is reusable.
- Guardrails sidecar can call redaction.
- Tracing/logging code uses redaction before writing sensitive text.
- Fake secret redaction test passes with 1.0 pass rate.
- Platform redaction cannot be weakened by tenant config.
