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