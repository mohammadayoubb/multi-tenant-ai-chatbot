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

## Owner B — Agent and RAG Evaluations

Owner B includes two lightweight golden-set evaluations. These are deterministic and run locally/CI without requiring a live hosted LLM or pgvector database.

### 1. Agent/tool-selection golden set

File:

```text
evals/agent_tool_selection_cases.json


Test:

tests/evals/test_agent_tool_selection.py

Purpose:

This eval checks whether common visitor messages choose the correct workflow route or agent tool plan.

Covered cases:

FAQ-style question → rag_search
explicit human request → escalate
sales/contact request → capture_lead
spam-like message → blocked
mixed/multi-step request → agent
ambiguous sales + knowledge request → rag_search + capture_lead

Run:

python -m pytest -q tests/evals/test_agent_tool_selection.py

Expected result:

10 passed
2. RAG retrieval golden set

File:

evals/rag_cases.json

Test:

tests/evals/test_rag_retrieval.py

Purpose:

This eval checks whether the RAG retriever selects the expected tenant-scoped CMS source for common business questions.

Covered cases:

services question
opening-hours question
pricing/membership question
location question
tenant-isolation cancellation-policy case

The tenant-isolation case ensures the retriever does not select another tenant's similar content.

Run:

python -m pytest -q tests/evals/test_rag_retrieval.py

Expected result:

5 passed
3. Section B report script

File:

evals/section_b_report.py

Purpose:

This script prints a concise report for demo/README use.

Run:

python evals\section_b_report.py

Expected output:

Section B Eval Report
=====================
Agent/tool selection: 10/10 passed
RAG retrieval:        5/5 passed

Status: PASS
4. Full test suite

Run:

python -m pytest -q

Expected result after Owner B evals:

51 passed
Notes and limitations

The current RAG retrieval eval uses deterministic lexical scoring because hosted embeddings and pgvector storage are not fully wired yet.

This is intentional for CI stability. The current eval proves:

chunking works
source selection works
tenant filtering logic is represented
retrieval behavior is testable

When pgvector is fully wired, this eval can be extended with database-backed vector retrieval metrics such as hit@k and MRR.


After adding it, run:

```cmd
python -m pytest -q

Then:

python evals\section_b_report.py

Expected:

51 passed

and:

Status: PASS
