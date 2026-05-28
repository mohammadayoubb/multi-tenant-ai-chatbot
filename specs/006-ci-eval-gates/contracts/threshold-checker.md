# Contract: Threshold Checker (`scripts/check_threshold.py`)

**Feature**: 006-ci-eval-gates · **Owner**: Amer · **Consumed by**: `.github/workflows/ci.yml` (and developers running it locally)

This contract pins the CLI surface, exit codes, and message format of `scripts/check_threshold.py`. The helper has one job: assert that a measured metric in an eval JSON file satisfies the threshold declared in `eval_thresholds.yaml`.

---

## T1 — Invocation

```sh
python scripts/check_threshold.py \
    --gate <gate_key> \
    --metric <metric_key> \
    --json <path-to-eval-output> \
    [--thresholds <path-to-eval_thresholds.yaml>]
```

| Flag | Required | Default | Purpose |
|---|---|---|---|
| `--gate <gate_key>` | yes | — | Top-level key in `eval_thresholds.yaml` (e.g., `classifier`, `rag`, `red_team`) |
| `--metric <metric_key>` | yes | — | Leaf key under the gate in `eval_thresholds.yaml` (e.g., `macro_f1_min`, `required_refusal_rate`) |
| `--json <path>` | yes | — | Path to the eval CLI's JSON output |
| `--thresholds <path>` | no | `eval_thresholds.yaml` at the repo root | Path to the threshold file (overrideable for tests) |

The helper takes the gate and metric as explicit arguments rather than auto-discovering them. This keeps the workflow self-documenting (each step's args name the gate it checks) and makes the helper trivially unit-testable.

## T2 — Exit codes

| Exit code | Meaning | Output stream |
|---|---|---|
| `0` | Threshold satisfied | one-line PASS message to stdout |
| `1` | Threshold violated OR any error | one-line FAIL or ERROR message to stderr |

There are no other exit codes. Treating "regression" and "error" identically is intentional: a CLI bug must not be silently classified as a passing run.

## T3 — Direction inference

The helper derives the comparison rule from the metric key's prefix/suffix:

| Pattern | Rule | JSON key to read |
|---|---|---|
| `<name>_min` | measured MUST be ≥ threshold (numeric) | `metrics.<name>` (suffix stripped) |
| `required_<name>` | measured MUST equal threshold exactly (numeric or integer) | `metrics.<name>` (prefix stripped) |

A metric key that matches neither pattern is an error (`ERROR unrecognized threshold key shape: <metric>`). New comparison shapes require a helper change in a follow-up PR plus a `DECISIONS.md` note.

## T4 — Output messages

### Pass (stdout, exit 0)

```text
PASS <gate>.<metric_short>: measured <m> >= min <t>
PASS <gate>.<metric_short>: measured <m> == required <t>
```

Examples:
- `PASS classifier.macro_f1: measured 0.83 >= min 0.80`
- `PASS red_team.refusal_rate: measured 1.0 == required 1.0`

### Fail (stderr, exit 1)

```text
FAIL <gate>.<metric_short>: measured <m> < min <t>
FAIL <gate>.<metric_short>: measured <m> != required <t>
```

Examples:
- `FAIL classifier.macro_f1: measured 0.78 < min 0.80`
- `FAIL red_team.refusal_rate: measured 0.998 != required 1.0`
- `FAIL redaction.secret_leak_count: measured 2 != required 0`

### Error (stderr, exit 1)

```text
ERROR threshold file not found: <path>
ERROR could not parse threshold file: <yaml-error>
ERROR threshold key not found in <path>: <gate>.<metric>
ERROR unrecognized threshold key shape: <metric>
ERROR eval JSON not found: <path>
ERROR could not parse eval JSON: <json-error>
ERROR metric key not found in eval JSON: metrics.<metric_short>
ERROR metric value is not numeric: <value>
```

## T5 — Numeric formatting

- Float values are printed with their natural Python `repr` (e.g., `0.83`, not `0.8300000`).
- Integer values are printed without decimal point (e.g., `0`, not `0.0`).
- For mixed comparisons (`refusal_rate` is a float but `secret_leak_count` is an integer), the helper preserves the type of the value as read from the JSON, not the type of the threshold from YAML.

## T6 — No I/O beyond the documented surface

The helper MUST NOT:
- Read environment variables (besides what Python's runtime requires).
- Write any file (output is exclusively stdout / stderr).
- Make any network call.
- Spawn subprocesses.

This makes the helper trivially testable with `subprocess.run` plus a captured stdout/stderr.

## T7 — Repeated invocation

The workflow invokes the helper once per (gate, metric) pair. The `rag-eval` job thus invokes the helper twice (once for `hit_at_5_min`, once for `faithfulness_min`) against the same JSON file. The helper is stateless; two invocations are independent.

## T8 — Examples (full session)

### Passing classifier gate

```sh
$ cat /tmp/classifier.json
{"metrics": {"macro_f1": 0.83}}
$ python scripts/check_threshold.py --gate classifier --metric macro_f1_min --json /tmp/classifier.json
PASS classifier.macro_f1: measured 0.83 >= min 0.80
$ echo $?
0
```

### Failing classifier gate

```sh
$ cat /tmp/classifier.json
{"metrics": {"macro_f1": 0.78}}
$ python scripts/check_threshold.py --gate classifier --metric macro_f1_min --json /tmp/classifier.json
# (stderr) FAIL classifier.macro_f1: measured 0.78 < min 0.80
$ echo $?
1
```

### Failing redaction gate

```sh
$ cat /tmp/redaction.json
{"metrics": {"secret_leak_count": 2}}
$ python scripts/check_threshold.py --gate redaction --metric required_secret_leak_count --json /tmp/redaction.json
# (stderr) FAIL redaction.secret_leak_count: measured 2 != required 0
$ echo $?
1
```

### Malformed JSON

```sh
$ cat /tmp/x.json
{"metrics": "not-an-object"}
$ python scripts/check_threshold.py --gate classifier --metric macro_f1_min --json /tmp/x.json
# (stderr) ERROR metric key not found in eval JSON: metrics.macro_f1
$ echo $?
1
```
