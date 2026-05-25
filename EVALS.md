# Owner: Ayoub
# EVALS.md

## Required CI Gates

| Gate | Minimum Requirement |
|---|---|
| Classifier eval | Macro-F1 above threshold |
| Agent tool-selection | Correct tool on golden set |
| RAG eval | hit@k, MRR, faithfulness |
| Red-team eval | Cross-tenant and prompt-injection attacks refused |
| Redaction eval | Fake secrets never appear in logs/traces |
| Smoke test | Compose stack boots from fresh clone |

## eval_thresholds.yaml

Thresholds live in `eval_thresholds.yaml`.
