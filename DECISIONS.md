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

## Owner B — Router, Agent, RAG, Tools, and Memory

### Decision: hybrid router + bounded agent

We use a hybrid message handling design instead of sending every visitor message directly to an LLM agent.

The first step is a classifier-driven router. High-confidence, enumerable cases are handled by deterministic workflow paths:

- `spam` → blocked
- `faq` → `rag_search`
- `sales_or_contact` → `capture_lead`
- `human_request` → `escalate`
- `ambiguous` or low-confidence → bounded agent

This keeps common traffic cheaper, faster, and more predictable. The agent is reserved for ambiguous or multi-step turns where tool sequencing is useful.

### Why not agent-only?

An agent-only design would be more expensive and less predictable. It would spend LLM/tool-calling budget on simple cases such as FAQs, clear lead-capture requests, and explicit human handoff requests.

The hybrid design gives us a safer production pattern:

- simple cases stay on cheap workflow routes
- uncertain cases fail safe to the agent
- the agent remains bounded by tool allowlist, iteration count, and token budget

### Agent constraints

The bounded agent can use only three tools:

- `rag_search`
- `capture_lead`
- `escalate`

The agent has:

- max tool iterations: 5
- max token budget per turn: 4000
- strict tool allowlist
- tenant ID passed only from trusted backend context

The visitor and LLM never choose `tenant_id`.

### RAG isolation decision

RAG retrieval is tenant-filtered. Every CMS page or future vector chunk must carry `tenant_id`, and retrieval must filter by it.

Current retriever rule:

```python
CmsPage.tenant_id == tenant_id

Current RAG fallback

Until hosted embeddings and pgvector storage are fully wired, the retriever uses tenant-scoped CMS rows and deterministic lexical scoring.

This gives us a real, testable chat path without cross-tenant leakage. The fallback is not the final retrieval strategy, but it preserves the most important contract: tenant-scoped retrieval.

Memory decision

Short-term memory is stored in Redis with the key format:

session:{tenant_id}:{session_id}

The memory TTL is configurable through:

SESSION_MEMORY_TTL_SECONDS

Default TTL:

1800 seconds

This gives the concierge enough context for a browsing session while avoiding permanent storage of anonymous visitor conversations.

Messages are redacted before being stored in memory.

Section B evals

Owner B includes two committed golden sets:

agent/tool-selection golden set
RAG retrieval golden set

The tool-selection eval checks whether visitor messages route to the expected path: RAG, lead capture, escalation, blocking, or agent handoff.

The RAG eval checks expected source selection and includes a tenant-isolation case.

The report script is:

python evals\section_b_report.py

## After adding it

Run:

```cmd
python -m pytest -q

Then run:

python evals\section_b_report.py

Expected report:

Section B Eval Report
=====================
Agent/tool selection: 10/10 passed
RAG retrieval:        5/5 passed

Status: PASS
