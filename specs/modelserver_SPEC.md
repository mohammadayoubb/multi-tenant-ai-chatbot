# Modelserver SPEC

Owner: Ayoub  
Component: Owner C — Classifier and Lean Modelserver  
Status: Draft

---

## 1. Purpose

The modelserver is a lean HTTP service responsible for serving the trained classifier used by the Concierge router.

The classifier receives an inbound visitor message and returns a route label. The main API uses that label to decide whether the message should be dropped, answered through RAG, converted into a lead, escalated to a human, or handed off to the agent.

The classifier is a service, not a direct import inside the main API.

---

## 2. Architecture Contract Rules

This component must follow the shared `CLAUDE.md` architecture contract.

Important rules:

- Training happens offline only.
- Serving must be lean.
- Do not add `torch` to the modelserver serving image.
- Do not add `transformers` to the modelserver serving image.
- The modelserver must refuse to boot if the artifact SHA-256 does not match the model card.
- Service-to-service calls must require authentication.
- Service credentials must come from Vault.
- No secrets may be hardcoded.
- No raw sensitive data should be logged.

---

## 3. Inputs

The modelserver accepts a JSON request containing a visitor message.

```json
{
  "message": "I want to book an appointment"
}
```

The modelserver must not accept `tenant_id` from the request body as trusted identity.

If tenant context is needed for logging or tracing, it must come from the trusted API context, not from the visitor payload.

---

## 4. Outputs

The modelserver returns a structured prediction.

```json
{
  "label": "sales_or_contact",
  "confidence": 0.91,
  "model_version": "v1",
  "latency_ms": 12.4
}
```

---

## 5. Initial Labels

| Label | Meaning | Router Behavior |
|---|---|---|
| `spam` | Message is spam, abusive, or irrelevant | Drop or refuse |
| `faq` | Clear question answerable from tenant CMS/RAG | RAG answer |
| `sales_or_contact` | Visitor wants pricing, booking, callback, or contact | Capture lead |
| `human_request` | Visitor explicitly asks for human support | Escalate |
| `ambiguous` | Unclear or multi-step message | Hand off to agent |

---

## 6. Required Model Comparison

The project requires comparing three approaches:

| Approach | Example | Serving Rule |
|---|---|---|
| Classical ML baseline | TF-IDF + Logistic Regression | Serve with `scikit-learn` / `joblib` |
| Small DL model | Small neural network exported to ONNX | Serve with `onnxruntime` only |
| LLM zero-shot baseline | Hosted LLM classification prompt | Used for comparison; not required to ship |

The final choice must be documented in `DECISIONS.md`.

---

## 7. Evaluation Metrics

The comparison must include:

- macro-F1
- per-class F1
- latency
- cost

The classifier CI gate should check macro-F1 against the committed threshold in `eval_thresholds.yaml`.

---

## 8. Model Card Requirement

Every shipped classifier artifact must have a `model_card.json` containing:

- task
- dataset source
- dataset hash
- label list
- training/test split description
- metrics for all three approaches
- chosen model
- artifact file name
- artifact SHA-256
- decision summary

---

## 9. Boot Safety

On startup, the modelserver must:

1. Load `model_card.json`.
2. Read the expected artifact SHA-256.
3. Compute the actual SHA-256 of the artifact.
4. Refuse to boot if the hashes do not match.
5. Load the artifact only after the hash check passes.

This prevents accidental or unsafe model drift.

---

## 10. API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Check service health |
| `POST` | `/predict` | Classify a visitor message |

---

## 11. Security

The `/predict` endpoint must require a service credential.

The main API must call the modelserver using a credential resolved from Vault.

The modelserver must reject requests with:

- missing service credential
- invalid service credential
- malformed request body
- empty message

---

## 12. Logging

Logs may include:

- request ID
- model version
- predicted label
- confidence
- latency

Logs must not include:

- raw visitor message text
- secrets
- tokens
- passwords
- emails
- phone numbers
- unredacted PII

---

## 13. Tests

Minimum tests:

- valid prediction returns label and confidence
- missing auth is rejected
- invalid auth is rejected
- malformed payload is rejected
- empty message is rejected
- artifact hash mismatch prevents startup
- no raw message is written to logs

---

## 14. Acceptance Criteria

- Modelserver exposes `/health`.
- Modelserver exposes `/predict`.
- `/predict` requires service authentication.
- Model artifact hash is checked at boot.
- Service refuses to start on artifact hash mismatch.
- No `torch` or `transformers` are included in the modelserver serving image.
- Prediction response includes label, confidence, model version, and latency.
- Tests cover valid prediction, invalid auth, bad payload, and artifact hash mismatch.
