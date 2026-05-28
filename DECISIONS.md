# Owner: Hiba
# DECISIONS.md

## Decision 1 — Use Hybrid Router + Agent

Context: Not every message needs expensive agent reasoning.

Decision: Use a classifier router for easy cases and a bounded tool-calling agent for ambiguous or multi-step turns.

Consequences: Lower cost, better control, and more predictable behavior.

## Decision 2 — Use RLS + Repository Scoping

Context: Tenant isolation is the highest-risk requirement.

Decision: Enforce isolation with Postgres RLS and still filter by tenant_id inside repositories.

Consequences: RLS protects against forgotten filters, while repository scoping keeps the code explicit.

## Decision 3 — Use Signed Widget Tokens

Context: CORS only protects browsers and is not authentication.

Decision: The loader exchanges widget_id + origin for a signed, short-lived token.

Consequences: Raw curl requests with copied widget_id cannot access tenant chat APIs without a valid token.

## Decision 4 — Use UUID Tenant IDs and Audited Tenant Management

Context: Tenant isolation is easier to reason about when tenant identifiers are globally unique and platform actions are traceable.

Decision: Tenant and tenant-owned records use UUID identifiers, and tenant provisioning/suspension actions require the tenant_manager role plus a tenant-scoped audit log.

Consequences: Repository scoping can consistently filter on UUID tenant_id, and platform lifecycle actions have an auditable trail.

## Decision 5 — Track Usage, Rate Limits, and Erasure in Tenant Scope

Context: Hiba's platform slice needs cost attribution, configurable action limits, and traceable tenant erasure without leaking cross-tenant data.

Decision: Record usage as tenant-scoped events, check rate limits from tenant-scoped windows, and return erasure results with scoped deleted-row counts plus audit events.

Consequences: Platform controls can block over-limit tenants, attribute cost by tenant_id, and prove erasure actions through audit logs and erasure job metadata.

## Decision 6 — Enforce Tenant Isolation With Postgres RLS Policies

Context: Repository filters are necessary but not enough for the highest-risk tenant-owned tables.

Decision: The initial Hiba migration enables and forces RLS on tenant-owned tables, using `app.tenant_id` as the trusted Postgres session setting.

Consequences: Tenant-owned reads and writes require the server to set tenant context before queries, giving the database a second isolation boundary.

## Decision 7 — Resolve Application Secrets From Vault

Context: `.env` files must not carry database passwords, signing keys, service credentials, or other application secrets.

Decision: Keep only Vault bootstrap settings in environment configuration, and load application connection strings and signing keys from Vault at runtime.

Consequences: Local and deployed environments must provision Vault before starting app components, and Ayoub must review Vault/security changes before merge.


## Owner C — Classifier, Modelserver, Guardrails, and Service Security

### Decision: Use small DL ONNX model as the production router classifier

**Decision:**  
We chose the small deep-learning model exported to ONNX as the production classifier for the Concierge router.

**Reason:**  
The classifier was trained on a combined public router dataset with five labels:

- `spam`
- `faq`
- `sales_or_contact`
- `human_request`
- `ambiguous`

We compared three approaches:

| Model | Purpose |
|---|---|
| Classical TF-IDF + Logistic Regression | Simple ML baseline |
| Small DL exported to ONNX | Lightweight deep-learning model for lean serving |
| LLM zero-shot baseline | API-based comparison baseline |

The small DL ONNX model achieved the best macro-F1 and accuracy while remaining compatible with the project serving rule: no `torch` or `transformers` in serving containers.

**Why not LLM zero-shot?**  
The LLM zero-shot baseline was slower, had API cost, and performed worse than the trained local models. This supports the architecture decision to use a cheap local classifier before sending difficult messages to the agent.

**Why ONNX?**  
ONNX allows us to train offline but serve lean. Training can use heavier tools in Colab, but the production modelserver only needs ONNX Runtime, vectorizer artifacts, and a label encoder.

**Impact:**  
The router can classify inbound visitor messages cheaply before deciding whether to drop spam, answer FAQ through RAG, capture a lead, escalate to a human, or send the message to the agent.

---

### Decision: Require service-to-service authentication for modelserver and guardrails

**Decision:**  
The modelserver and guardrails sidecar require Bearer-token service authentication.

**Reason:**  
Internal Docker networking is not authentication. A service should not trust another caller only because it is on the same network.

**Impact:**  
The modelserver `/predict` endpoint and guardrails `/check` endpoint reject missing or invalid credentials. A shared service-auth helper centralizes this validation.

---

### Decision: Use guardrails sidecar for platform safety checks

**Decision:**  
We implemented the guardrails layer as a sidecar service.

**Reason:**  
Guardrails are a trust boundary. Keeping them as a separate service makes the safety layer explicit and easier to test.

The first platform rails block:

- prompt-injection attempts
- system-prompt extraction attempts
- cross-tenant data extraction attempts

**Impact:**  
Unsafe messages can be blocked before they reach the agent or cause tool calls.

---

### Decision: Redact PII and secrets before logs, traces, or memory

**Decision:**  
We added a redaction utility to remove sensitive data before text is stored in logs, traces, or memory.

**Redacted examples include:**

- emails
- phone numbers
- OpenAI-style keys
- Bearer tokens
- password/token/secret key-value strings

**Impact:**  
Visitor-provided secrets and PII are less likely to leak through traces, debugging output, or memory.