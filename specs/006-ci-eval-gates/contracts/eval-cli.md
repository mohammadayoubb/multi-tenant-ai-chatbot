# Contract: Eval CLI

**Feature**: 006-ci-eval-gates · **Consumed by**: `.github/workflows/ci.yml` · **Produced by**: Ayoub (classifier, red-team, redaction) and Nasser (rag, agent-tool)

This contract pins the invocation pattern, exit-code semantics, and output-JSON shape every eval CLI must satisfy. Owners of the real evaluators MUST conform to this contract; this PR ships mocks at the same paths to bootstrap the wiring.

---

## C1 — Module path

Each gate's CLI lives at `evals/<module>.py` and is invoked as a runnable module:

```sh
python -m evals.<module> --output <path>
```

| Gate | Module | Owner |
|---|---|---|
| `classifier-eval` | `evals.classifier` | Ayoub |
| `rag-eval` | `evals.rag` | Nasser |
| `agent-tool-eval` | `evals.agent_tool` | Nasser |
| `red-team` | `evals.red_team` | Ayoub |
| `redaction-eval` | `evals.redaction` | Ayoub |

The module name is part of the contract. Renaming requires updating both `ci.yml` and `DECISIONS.md`.

## C2 — Required flag: `--output <path>`

Each CLI MUST accept exactly one required flag, `--output <path>`, that specifies the file path where the eval JSON output is written. The CLI MUST write a single JSON document to this path. The CLI MUST NOT write its primary output to stdout (stdout is reserved for human-readable progress; stderr for warnings/errors).

The CI workflow always passes a writable path under `$RUNNER_TEMP` or the workspace directory. CLIs MUST create parent directories of `<path>` if needed.

## C3 — Optional flags (informational, not part of the contract)

Owners MAY add additional CLI flags (`--dataset`, `--model-artifact`, `--seed`, etc.). These are owner-defined and not consumed by Amer's CI wiring. The wiring only ever passes `--output <path>`.

## C4 — Exit code semantics

| Exit code | Meaning |
|---|---|
| `0` | The CLI ran to completion and produced a well-formed JSON output at `--output`. The measured value MAY be below threshold; that decision is made by `scripts/check_threshold.py`, not the CLI. |
| non-zero | The CLI itself failed (dataset missing, model artifact corrupted, dependency error, etc.). No threshold check is attempted. The CI job fails. |

**Critical invariant**: a successful CLI run with a below-threshold metric MUST exit `0`. The CLI does not decide pass/fail against the threshold; the threshold checker does. This separation lets `check_threshold.py` be the single source of truth for gate enforcement.

## C5 — Output JSON shape

The file written to `--output <path>` MUST be a single valid JSON document with at minimum:

```json
{
  "metrics": {
    "<metric_key>": <numeric_value>
  }
}
```

`<metric_key>` is the unqualified leaf name from `eval_thresholds.yaml`:

| Threshold key in YAML | `<metric_key>` in JSON | Direction (computed by checker) |
|---|---|---|
| `classifier.macro_f1_min` | `macro_f1` | `>=` (min) |
| `rag.hit_at_5_min` | `hit_at_5` | `>=` (min) |
| `rag.faithfulness_min` | `faithfulness` | `>=` (min) |
| `agent_tool_selection.accuracy_min` | `accuracy` | `>=` (min) |
| `red_team.required_refusal_rate` | `refusal_rate` | `==` (eq) |
| `redaction.required_secret_leak_count` | `secret_leak_count` | `==` (eq) |

For the `rag` gate, the CLI's single JSON document MUST contain BOTH `hit_at_5` and `faithfulness` under `metrics`. The `rag-eval` job invokes the CLI once and runs the threshold checker twice (one invocation per metric).

## C6 — Permitted optional fields

The following sibling fields at the top level are permitted and ignored by the checker:

| Field | Type | Purpose |
|---|---|---|
| `_mock` | boolean | `true` only on mocks shipped in this PR; real evaluators MUST NOT set it |
| `meta` | object | free-form provenance (CLI version, run id) |
| `dataset_hash` | string | the SHA-256 of the dataset evaluated (recommended for real evals; informational) |
| `examples` | array | per-example diagnostics (recommended for failing runs) |

Additional fields are permitted without contract amendment as long as they do not conflict with `metrics`.

## C7 — Stderr conventions

CLIs MAY write progress lines to stderr. Mocks MUST write exactly one stderr line of the form:

```text
MOCK EVALUATOR: <gate> is not yet implemented — owner: <name>
```

This line is grepped by reviewers from the workflow log to enumerate un-fulfilled gates. Real evaluators MUST NOT emit this string.

## C8 — Determinism (advisory, not enforced in this PR)

Real evaluators SHOULD be deterministic (fixed seed, fixed dataset hash). Non-deterministic flake handling is out of scope for this PR. If a real evaluator is flaky, the owner is responsible for stabilizing it or proposing a retry mechanism in a follow-up PR.

## C9 — Runtime budget (advisory)

The mocks shipped here complete in well under one second. Real evaluators have no contractually-fixed budget but SHOULD aim to complete inside the GitHub Actions default job timeout (6 hours). Anything longer requires a follow-up workflow change owned by Amer.

## C10 — Examples

### Classifier (passing mock)

```sh
$ python -m evals.classifier --output /tmp/classifier.json
# stderr: MOCK EVALUATOR: classifier is not yet implemented — owner: Ayoub
$ cat /tmp/classifier.json
{"metrics": {"macro_f1": 0.80}, "_mock": true}
$ echo $?
0
```

### Red-team (passing real evaluator, illustrative)

```sh
$ python -m evals.red_team --output /tmp/red_team.json --suite full
$ cat /tmp/red_team.json
{"metrics": {"refusal_rate": 1.0}, "meta": {"version": "0.3.1", "total_prompts": 247, "refused": 247}, "dataset_hash": "sha256:abc..."}
$ echo $?
0
```

### Redaction (failing real evaluator, illustrative)

```sh
$ python -m evals.redaction --output /tmp/redaction.json
$ cat /tmp/redaction.json
{"metrics": {"secret_leak_count": 2}, "examples": [{"prompt_id": "p47", "leaked": "AKIA..."}, {"prompt_id": "p82", "leaked": "ghp_..."}]}
$ echo $?
0
# threshold checker then fails the gate:
$ python scripts/check_threshold.py --gate redaction --metric secret_leak_count --json /tmp/redaction.json
# stderr: FAIL redaction.secret_leak_count: measured 2 != required 0
$ echo $?
1
```
