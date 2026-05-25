# Owner: Ayoub
# SECURITY.md

## Security Rules

- Never trust `tenant_id` from a request body.
- Tenant context comes from authenticated user or signed widget token.
- CORS is not authentication.
- Platform guardrails cannot be edited by tenants.
- Logs, traces, memory, and prompts must be redacted.
- Tenant manager cannot read tenant private data.
- Erasure must delete rows, vectors, blobs, sessions, and traces where applicable.
