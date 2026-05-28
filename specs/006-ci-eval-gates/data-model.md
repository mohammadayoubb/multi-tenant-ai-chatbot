# Phase 1 Data Model: CI Eval Gates Enforced

**Feature**: 006-ci-eval-gates · **Owner**: Amer

This feature introduces no database entities and no persistent state. The "data" in scope is the YAML threshold file, the per-gate JSON eval output, and the threshold-check report. All three are file-system entities consumed and produced by CI jobs and the helper script.

## E1 — Eval Gate

A named quality threshold tracked in `eval_thresholds.yaml`. The set of gates is fixed at five for this PR and matches the file's current contents exactly.

| Field | Type | Source | Notes |
|---|---|---|---|
| `gate_key` | string | derived from YAML path | e.g., `classifier`, `rag`, `agent_tool_selection`, `red_team`, `redaction` |
| `metric_key` | string | YAML leaf name | e.g., `macro_f1_min`, `hit_at_5_min`, `faithfulness_min`, `accuracy_min`, `required_refusal_rate`, `required_secret_leak_count` |
| `metric_value` | float \| int | YAML value | the threshold itself |
| `direction` | enum (`min`, `eq`) | inferred from `metric_key` suffix | `*_min` → `min`; `required_*` → `eq` |
| `owner` | string | this PR (`DECISIONS.md` entry) | Ayoub or Nasser; not stored in YAML |
| `eval_module` | string | this PR (workflow) | `evals.<gate>` — the Python module path the CLI lives at |

**Gates enumerated**:

| `gate_key` | `metric_key` | value | direction | owner | `eval_module` |
|---|---|---|---|---|---|
| `classifier` | `macro_f1_min` | 0.80 | min | Ayoub | `evals.classifier` |
| `rag` | `hit_at_5_min` | 0.75 | min | Nasser | `evals.rag` |
| `rag` | `faithfulness_min` | 0.80 | min | Nasser | `evals.rag` |
| `agent_tool_selection` | `accuracy_min` | 0.90 | min | Nasser | `evals.agent_tool` |
| `red_team` | `required_refusal_rate` | 1.00 | eq | Ayoub | `evals.red_team` |
| `redaction` | `required_secret_leak_count` | 0 | eq | Ayoub | `evals.redaction` |

Note: the `rag` gate has two metrics (`hit_at_5_min`, `faithfulness_min`) and one eval module (`evals.rag`). The `rag-eval` job invokes the CLI once and runs the threshold checker twice — once per metric. The checker handles each gate independently.

**Lifecycle**: An Eval Gate exists for the life of the repository. Threshold values can change only via an Ayoub-reviewed PR. Adding or removing a gate requires both a `DECISIONS.md` entry and a workflow update; this feature explicitly does not introduce a mechanism for that — the set of jobs in `ci.yml` is matched against the keys in `eval_thresholds.yaml` by SC-005 (manual review at gate-add time).

## E2 — Eval JSON Output

The artifact each eval CLI writes to disk. Uploaded as a GitHub Actions workflow artifact regardless of pass/fail.

```json
{
  "metrics": {
    "<metric_key_short>": <numeric_value>,
    "...": "..."
  },
  "_mock": true,        // present and true only for mocks shipped in this PR
  "meta": { "...": "..." },  // optional, ignored by the checker
  "dataset_hash": "..."      // optional, ignored by the checker
}
```

**Required fields**:
- `metrics` (object): at least one key matching the gate's `<metric_key_short>` (see mapping below). Value MUST be a JSON number.

**Metric-key mapping** (drops suffix/prefix from `eval_thresholds.yaml`):

| Gate `metric_key` in YAML | `<metric_key_short>` in JSON |
|---|---|
| `macro_f1_min` | `macro_f1` |
| `hit_at_5_min` | `hit_at_5` |
| `faithfulness_min` | `faithfulness` |
| `accuracy_min` | `accuracy` |
| `required_refusal_rate` | `refusal_rate` |
| `required_secret_leak_count` | `secret_leak_count` |

**Optional fields**:
- `_mock`: `true` if and only if the producer is a mock shipped in this PR. Real evaluators MUST NOT set this field.
- Any other sibling key (`meta`, `dataset_hash`, `examples`, etc.) is permitted and ignored by `check_threshold.py`.

**Validation rules**:
- `metrics` must be a JSON object.
- The required `<metric_key_short>` must be present and numeric. Missing or non-numeric → checker fails with `ValueError`.
- File must be valid JSON. Parse error → checker fails with `JSONDecodeError`.

**Lifetime**: written by the CLI during the CI job, consumed by `check_threshold.py` in the same job, uploaded as a workflow artifact, retained per GitHub Actions default retention (90 days). Not committed to the repo.

## E3 — Threshold Check Report

A pass/fail decision produced by `scripts/check_threshold.py` for a single (gate, metric) pair. The report is **not** persisted — it is exit code + stdout/stderr text.

| Field | Encoding | Notes |
|---|---|---|
| `outcome` | process exit code | `0` = pass, `1` = fail. No other exit codes. |
| `human_message` | stdout (pass) or stderr (fail) | One line. See format below. |

**Pass message** (stdout, exit 0):

```text
PASS classifier.macro_f1: measured 0.83 >= min 0.80
```

**Fail message** (stderr, exit 1):

```text
FAIL classifier.macro_f1: measured 0.78 < min 0.80
```

**Equality-gate fail message**:

```text
FAIL red_team.refusal_rate: measured 0.998 != required 1.0
FAIL redaction.secret_leak_count: measured 2 != required 0
```

**Error messages** (stderr, exit 1) for malformed inputs:
- `ERROR threshold file not found: <path>`
- `ERROR could not parse threshold file: <yaml-parse-error>`
- `ERROR threshold key not found in <path>: <gate>.<metric>`
- `ERROR eval JSON not found: <path>`
- `ERROR could not parse eval JSON: <json-parse-error>`
- `ERROR metric key not found in eval JSON: metrics.<metric_key_short>`
- `ERROR metric value is not numeric: <value>`

No exit-code branch other than 0 (pass) and 1 (fail-or-error). Treating an error and a regression identically prevents a CLI bug from being mistaken for a passing run.

## Entity relationship

```text
eval_thresholds.yaml (E1 source)
        │
        │  read by
        ▼
scripts/check_threshold.py ──── reads ────► evals/<gate>.py output (E2)
        │
        │  writes
        ▼
Threshold Check Report (E3: exit code + stdio)
        │
        ▼
CI job pass/fail decision → blocks merge or allows merge
```

## Out of scope

- Persisting eval results across runs (a future "eval history" feature could read the uploaded artifacts and graph trends; not part of this PR).
- A schema for per-class or per-example detail inside `metrics` — owners are free to nest, and the checker only reads the leaf it cares about.
- Tenant-scoped evals. Evaluation is a global model-quality concern and is intentionally not per-tenant. Tenant-scoped quality monitoring is a separate operational concern owned by Hiba's audit/usage work in Phase 9.
