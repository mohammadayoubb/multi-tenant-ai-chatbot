## Owner C — Classifier, Modelserver, Guardrails, Redaction, and Service Security

### 1. Classifier Evaluation

The classifier is used as the router before the agent. It predicts one of five Concierge routing labels:

- `spam`
- `faq`
- `sales_or_contact`
- `human_request`
- `ambiguous`

The final dataset is a combined public router dataset built from public customer-support, spam, and out-of-scope style data. This is stronger than the earlier curated-only dataset because it better matches the real Concierge routing problem.

#### Models Compared

| Model | Macro-F1 | Accuracy | Average Latency | Cost |
|---|---:|---:|---:|---:|
| Classical TF-IDF + Logistic Regression | 0.9680 | 0.9681 | 0.188 ms | $0 |
| Small DL exported to ONNX | **0.9752** | **0.9753** | **0.145 ms** | $0 |
| LLM zero-shot baseline | 0.5429 | 0.5700 | 752.6 ms | ~$0.0028 for 100 samples |

#### Classifier Decision

The chosen production classifier is:

```text
small_dl_onnx